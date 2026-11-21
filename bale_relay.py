#!/usr/bin/env python3
"""Always-on dumb relay for the Bale <-> Nova bridge (standby mode).

Long-polls Bale getUpdates, filters through bridge_core (pairing, owner
filter, dedup), appends inbound owner messages to hidden_files/pending.jsonl
and to the transcript, and refreshes hidden_files/heartbeat.txt each loop.

This process contains NO AI and consumes no model tokens. Its only job is
to notice messages. A hook watches pending.jsonl and wakes Nova only when
a message is actually waiting.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_core as core

PENDING_PATH = os.path.join(core.STATE_DIR, "pending.jsonl")
HEARTBEAT_PATH = os.path.join(core.STATE_DIR, "heartbeat.txt")
TOKEN_PATH = os.path.join(core.STATE_DIR, "token.txt")
API_BASE = "https://tapi.bale.ai/bot{}/"
LONG_POLL_TIMEOUT = 25  # seconds, held server-side by getUpdates


def read_token() -> str:
    with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def call(token: str, method: str, params: dict, timeout: float) -> dict:
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        API_BASE.format(token) + method,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def beat() -> None:
    os.makedirs(core.STATE_DIR, exist_ok=True)
    tmp = HEARTBEAT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(str(time.time()))
    os.replace(tmp, HEARTBEAT_PATH)


def append_pending(entry: dict) -> None:
    os.makedirs(core.STATE_DIR, exist_ok=True)
    with open(PENDING_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    token = read_token()
    state = core.load_state()
    print(f"relay started; paired={state['owner_chat_id'] is not None}", flush=True)
    while True:
        try:
            params = {"timeout": LONG_POLL_TIMEOUT}
            if state["last_update_id"]:
                params["offset"] = state["last_update_id"] + 1
            resp = call(token, "getUpdates", params, LONG_POLL_TIMEOUT + 15)
            if resp.get("ok"):
                events = core.process_updates(state, resp.get("result") or [])
                if events:
                    core.save_state(state)
                for ev in events:
                    if ev["type"] == "message":
                        append_pending(
                            {"chat_id": ev["chat_id"], "text": ev["text"],
                             "update_id": ev["update_id"], "ts": time.time()}
                        )
                        core.append_transcript(
                            {"dir": "in", "chat_id": ev["chat_id"], "text": ev["text"]}
                        )
                        print(f"pending message queued (update {ev['update_id']})", flush=True)
                    elif ev["type"] == "paired":
                        core.append_transcript(
                            {"dir": "sys", "event": "paired", "chat_id": ev["chat_id"]}
                        )
            else:
                print(f"getUpdates not ok: {resp.get('description')}", flush=True)
                time.sleep(5)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            print(f"network error: {exc}; retry in 5s", flush=True)
            time.sleep(5)
        except Exception as exc:  # keep the relay alive on surprises
            print(f"unexpected error: {exc!r}; retry in 10s", flush=True)
            time.sleep(10)
        beat()


if __name__ == "__main__":
    main()
