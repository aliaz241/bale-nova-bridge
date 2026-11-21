"""Core state/logic for the Bale <-> Nova bridge (prototype v1).

Pure logic only: no network, no secrets. The agent-facing CLI in
bridge.py feeds Bale getUpdates payloads in here and sends replies out.

Security model:
- The bot pairs with exactly ONE owner chat. Pairing happens when a chat
  sends `/pair <code>` with the one-time code (stored here as SHA-256).
- Before pairing, everything except a correct /pair is ignored.
- After pairing, messages from any other chat are ignored.
- update_id watermark gives dedup: an update is processed at most once.
"""
import hashlib
import json
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "hidden_files")
STATE_PATH = os.path.join(STATE_DIR, "state.json")
TRANSCRIPT_PATH = os.path.join(STATE_DIR, "transcript.jsonl")


def _default_state() -> dict:
    return {
        "pair_code_hash": None,   # sha256 hex of the one-time pairing code
        "owner_chat_id": None,    # set once pairing succeeds
        "last_update_id": 0,      # dedup watermark
        "paired_at": None,
    }


def load_state(path: str = STATE_PATH) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            state = _default_state()
            state.update(json.load(fh))
            return state
    return _default_state()


def save_state(state: dict, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def set_pair_code(state: dict, code: str) -> None:
    state["pair_code_hash"] = hash_code(code)


def append_transcript(entry: dict, path: str = TRANSCRIPT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = dict(entry)
    entry.setdefault("ts", time.time())
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _message_of(update: dict):
    msg = update.get("message")
    if not isinstance(msg, dict):
        return None
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = msg.get("text")
    if chat_id is None or not isinstance(text, str):
        return None
    return chat_id, text


def process_updates(state: dict, updates: list) -> list:
    """Consume raw getUpdates results.

    Returns a list of events:
      {"type": "paired", "chat_id": ...}
      {"type": "message", "chat_id": ..., "text": ..., "update_id": ...}
    Mutates state (watermark, owner). Caller persists with save_state().
    """
    events = []
    for update in updates or []:
        if not isinstance(update, dict):
            continue
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            if update_id <= state["last_update_id"]:
                continue  # already seen
            state["last_update_id"] = update_id
        parsed = _message_of(update)
        if parsed is None:
            continue
        chat_id, text = parsed

        if state["owner_chat_id"] is None:
            # Pairing mode: only a correct /pair <code> has any effect.
            parts = text.strip().split(maxsplit=1)
            if (
                len(parts) == 2
                and parts[0] == "/pair"
                and state["pair_code_hash"]
                and hash_code(parts[1]) == state["pair_code_hash"]
            ):
                state["owner_chat_id"] = chat_id
                state["paired_at"] = time.time()
                state["pair_code_hash"] = None  # one-time: burn after use
                events.append({"type": "paired", "chat_id": chat_id})
            continue

        if chat_id != state["owner_chat_id"]:
            continue  # not the owner: ignore silently
        events.append(
            {
                "type": "message",
                "chat_id": chat_id,
                "text": text,
                "update_id": update_id,
            }
        )
    return events
