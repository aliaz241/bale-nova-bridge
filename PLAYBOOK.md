# Build guide: "Bale messenger ↔ AI agent" bridge

Hand this document to any other AI agent; by following it step by step it will build the same system that lets a user talk to their agent from inside the Bale messenger (even when international internet is cut and only the domestic network is up).

Audience: the executing agent itself. The tone is imperative.

---

## 1. Goal and architecture

Three components:

1. **The Bale bot** — the user's point of contact inside Bale. Its API resembles the Telegram Bot API: `https://tapi.bale.ai/bot<TOKEN>/<METHOD>` with JSON bodies and POST.
2. **The relay** — a light, "dumb" process that runs 24/7 in the background, long-polls the bot's messages, applies the security filter, and puts the owner's messages into a queue file (`pending.jsonl`). The relay consumes no AI tokens/models.
3. **The agent (you)** — whenever a message is in the queue you are woken (by a periodic watcher), read the message, produce the reply, and send it back to the same chat with `sendMessage`.

Flow: user messages in Bale → relay queues it → watcher wakes the agent → agent replies to the owner's chat via the CLI.

## 2. Prerequisites

- A Bale bot and its token (the user gets it from Bale's official bot-creation bot).
- An always-on machine for the relay (a server, or your own work environment).
- Python 3 (standard library only; no pip installs needed).

## 3. The golden rule of the token

- **Never** write the token in code, chat, logs, or memory.
- The token is kept in a protected file: `hidden_files/token.txt` with `chmod 600`. Only the relay and the CLI read it.
- Validate the token only by calling `getMe`: `POST https://tapi.bale.ai/bot<TOKEN>/getMe` with body `{}`. If it returns `"ok": true` and the bot's username, the token is valid.
- Warning from real experience: Bale tokens and Telegram tokens look alike; each is valid only on its own platform and returns `Unauthorized`/404 on the other. Before concluding "the token is broken", make sure you tested the right method on the right platform, and that an empty token did not reach the test function (a common heredoc bug: scripts that swallow stdin end up testing an empty token).

## 4. Security model (implement exactly like this)

- The bridge connects to exactly **one** owner chat.
- Pairing uses a one-time code:
  - The agent generates a random 10-character code (uppercase letters + digits).
  - Only the **SHA-256 hash** of the code is stored in the state file; the code itself is shown to the user once.
  - The user sends `/pair <CODE>` to the bot in Bale.
  - If the hash matches: `owner_chat_id` becomes that chat, the code is burned (`pair_code_hash = null`), and pairing is complete.
- Before pairing, every message except a correct `/pair` is ignored.
- After pairing, messages from any chat other than the owner's are **silently ignored**.
- To avoid processing updates twice, `last_update_id` (a watermark) is kept in state and each update is processed at most once.

The `state.json` file:

```json
{
  "pair_code_hash": "<sha256 hex or null>",
  "owner_chat_id": 123456789,
  "last_update_id": 0,
  "paired_at": 0
}
```

## 5. Code components

Build three Python files:

### a) `bridge_core.py` — pure logic (no network)
- `load_state()` / `save_state()` — atomic state read/write (write to a temp file + rename).
- `hash_code(code)` — SHA-256.
- `set_pair_code(state, code)` — store the code's hash.
- `append_transcript(entry)` — JSONL log of all incoming/outgoing messages with direction (`dir: in|out`) and timestamp, in `hidden_files/transcript.jsonl`.
- `process_updates(state, updates)` — the heart of the system: applies the watermark and the security rules above and returns events: `{"type": "paired", "chat_id": ...}` or `{"type": "message", "chat_id": ..., "text": ..., "update_id": ...}`.

### b) `bridge.py` — CLI for the agent
Reads the token from `hidden_files/token.txt` and calls the Bale API directly.

| Command | What it does |
|---|---|
| `python3 bridge.py status` | Pairing state, owner id, watermark, whether a code is pending (no secrets) |
| `python3 bridge.py set-pair-code --code CODE` | Store the pairing code's hash; errors if already paired |
| `python3 bridge.py poll` | One `getUpdates` round, prints events as JSON |
| `python3 bridge.py reply --text "TEXT"` | Send a message to the owner's chat + log it in the transcript |
| `python3 bridge.py inbox` | Read the queue of waiting messages |
| `python3 bridge.py inbox-clear` | Archive the read queue (rename to `.done`) and create an empty queue |

Bale API methods you need: `getMe`, `getUpdates` (with `offset` and `timeout`), `sendMessage` (with `chat_id` and `text`).

### c) `bale_relay.py` — the always-on relay
- On start: reads the token and the state.
- Infinite loop: `getUpdates` with long polling (server timeout 25 s, offset = watermark+1) → `process_updates` → save state on events.
- `message` event: append to `hidden_files/pending.jsonl` + transcript.
- `paired` event: log a system entry in the transcript.
- Every loop round: update `hidden_files/heartbeat.txt` with the current time (the watchdog infers the relay's liveness from this file's freshness).
- On network error: wait 5 s and retry; on unknown error: 10 s. The relay must never die.
- Run detached: `nohup python3 bale_relay.py >> hidden_files/relay.log 2>&1 &`

**Critical warning:** the relay reads state only once at startup and keeps the in-memory copy. Any manual change to `state.json` (e.g. resetting pairing) takes effect only after a **relay restart**; otherwise, on the next event the relay overwrites the file with its old state.

## 6. How the agent wakes up

- A light watcher (hook/cron) checks two things every 30 seconds:
  1. Is `pending.jsonl` non-empty? → wake the agent with the queue's contents.
  2. Is `heartbeat.txt` fresh? → if the relay died, start it again (watchdog).
- The woken agent: reads `inbox` → replies (`reply`) → runs `inbox-clear`.
- When the queue is empty the agent stays fully asleep (zero consumption).

## 7. Flows

### Initial setup
1. Build the three files above + offline unit tests for `process_updates` (correct/incorrect pairing, non-owner filter, dedup).
2. Get the token from the user through a secure form; store it in `token.txt` (600).
3. Validate with `getMe`.
4. Generate a pairing code, `set-pair-code`, show the code to the user.
5. Start the relay.
6. The user sends `/pair <CODE>` in Bale.
7. Confirm with `status`: it must show `paired: true` and `pair_code_pending: false`.
8. Round-trip test: the user asks a known question (e.g. "what's my name?"); the agent reads it from the queue and replies in Bale.

### Reset and re-pairing (e.g. the user arrives from another account/chat)
1. Kill the relay (`pkill -f bale_relay.py`).
2. In state: set `owner_chat_id = null`, `paired_at = null`, and store the new code's hash. **Keep the watermark** so old updates are not reprocessed.
3. Start the relay again and check the log: `relay started; paired=False`.
4. Give the code to the user → `/pair <CODE>` → confirm with `status`.

## 8. Delivery checklist

- [ ] `getMe` answers ok with the token and the bot's name is correct
- [ ] `status` before pairing: `paired: false` and `pair_code_pending: true`
- [ ] After `/pair`: `paired: true`, the owner id is correct, the code is burned
- [ ] The user's test message lands in `pending.jsonl` and the agent wakes up
- [ ] The agent's reply reaches the user in Bale and is logged in the transcript
- [ ] The heartbeat is fresh and the watchdog keeps the relay alive
- [ ] The token appears in plain text in no code/log/memory file (except `hidden_files/token.txt` with permissions 600)

---

Final note for the executing agent: this bridge is deliberately kept simple — no database, no framework, just JSON/JSONL files and the Python standard library. That simplicity is what makes it reliable on any machine and under international-internet outages. If you want to add a feature (multiple users, a priority queue, end-to-end encryption of the transcript), coordinate with the user first; do not change the single-owner security model or the one-time code without their permission.
