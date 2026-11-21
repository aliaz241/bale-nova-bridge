# Bale – AI Agent Bridge (prototype v1)

Goal: the user messages a bot inside Bale (the Iranian messenger); an AI agent (Muse) reads the message and replies through the same bot. A fallback channel for times when international internet access is cut and only the domestic network is up.

## Architecture
- A Bale bot (created via Bale's bot father) + its token, kept in `hidden_files/token.txt`.
- Bridge logic: `bridge_core.py` — one-time pairing code, owner filter, `update_id` deduplication.
- Agent interface: `bridge.py` — commands: `set-pair-code`, `poll`, `reply`, `status`. It calls the Bale Bot API directly (`https://tapi.bale.ai/bot<token>/...`, methods `getMe`, `getUpdates`, `sendMessage`).
- State and transcript: `hidden_files/state.json` and `hidden_files/transcript.jsonl`.
- Always-on relay: `bale_relay.py` — a detached long-polling process that queues owner messages in `hidden_files/pending.jsonl` and writes a heartbeat; a periodic watcher wakes the agent only when a message is waiting.

## Security
- The bot pairs with exactly one chat (the owner): the first chat that sends a correct `/pair <code>`. The code is single-use and only its SHA-256 hash is stored.
- Messages from any other chat are silently ignored.

## Status
- Offline logic tested (`test_bridge.py` — all tests pass).
- Live round-trip verified: `getMe`, one-time-code pairing, and a real two-way conversation in Bale.
- The token lives only in `hidden_files/token.txt` (permissions `600`).

## v1 limitations
- Text only. Photos/files/voice come later.
- Reply latency depends on the poll interval; it is not real-time like WhatsApp.

---

## Setup (public release)

This release ships **with no token or personal identifiers** — bring your own:

1. Create a bot in Bale and get its token.
2. Create the `hidden_files` folder and put the token in `hidden_files/token.txt` (the token only, one line).
3. Run: `python3 bale_relay.py` — on first run a pairing code is issued; whoever sends `/pair <code>` to the bot becomes its owner, and from then on only the owner can message it.

See `PLAYBOOK.md` for a complete step-by-step build guide you can hand to any AI agent.
