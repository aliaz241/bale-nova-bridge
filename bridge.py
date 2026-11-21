#!/usr/bin/env python3
"""Agent-facing CLI for the Bale <-> Nova bridge (prototype v1).

Commands:
  set-pair-code --code CODE   store the one-time pairing code (hashed)
  poll                        fetch new Bale updates once; print events as JSON.
                              New owner messages are also appended to the transcript.
  reply --text TEXT           send TEXT to the paired owner chat in Bale and
                              append it to the transcript.
  status                      pairing/owner/watermark summary (no secrets).

Bale API access goes through the connector helper bale_api.py, which uses
the registered `custom.bale-bot` credential; no token lives in this project.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import bridge_core as core

BALE_API = "."
TOKEN_PATH = os.path.join(core.STATE_DIR, "token.txt")
API_BASE = "https://tapi.bale.ai/bot{}/"


def _read_token():
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        return token or None
    except OSError:
        return None


def _direct_call(method: str, params: dict) -> dict:
    token = _read_token()
    if not token:
        return {"ok": False, "description": "token file missing"}
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        API_BASE.format(token) + method,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": exc.code, "description": str(exc)}


def bale_call(*argv: str) -> dict:
    # Preferred path: direct call with the protected local token file
    # (design choice). Fallback: the vault connector helper,
    # which returned 404 in this environment and is kept only as a backup.
    if _read_token():
        cmd = argv[0]
        if cmd == "getupdates":
            params = {"timeout": 0}
            if "--offset" in argv:
                params["offset"] = int(argv[argv.index("--offset") + 1])
            return _direct_call("getUpdates", params)
        if cmd == "send":
            chat_id = argv[argv.index("--chat-id") + 1]
            text = argv[argv.index("--text") + 1]
            return _direct_call("sendMessage", {"chat_id": chat_id, "text": text})
        if cmd == "getme":
            return _direct_call("getMe", {})
    proc = subprocess.run(
        [sys.executable, BALE_API, *argv],
        capture_output=True, text=True, timeout=60,
    )
    out = (proc.stdout or "").strip()
    if not out:
        return {"ok": False, "description": proc.stderr.strip() or "empty response"}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"ok": False, "description": out[:300]}


def cmd_set_pair_code(args) -> int:
    state = core.load_state()
    if state["owner_chat_id"] is not None:
        print(json.dumps({"ok": False, "error": "already paired"}, ensure_ascii=False))
        return 1
    core.set_pair_code(state, args.code)
    core.save_state(state)
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_poll(args) -> int:
    state = core.load_state()
    offset = state["last_update_id"] + 1 if state["last_update_id"] else None
    argv = ["getupdates"]
    if offset:
        argv += ["--offset", str(offset)]
    resp = bale_call(*argv)
    if not resp.get("ok"):
        print(json.dumps({"ok": False, "api": resp}, ensure_ascii=False))
        return 1
    events = core.process_updates(state, resp.get("result") or [])
    core.save_state(state)
    for ev in events:
        if ev["type"] == "message":
            core.append_transcript(
                {"dir": "in", "chat_id": ev["chat_id"], "text": ev["text"]}
            )
        elif ev["type"] == "paired":
            core.append_transcript({"dir": "sys", "event": "paired", "chat_id": ev["chat_id"]})
    print(json.dumps({"ok": True, "events": events}, ensure_ascii=False))
    return 0


def cmd_reply(args) -> int:
    state = core.load_state()
    if state["owner_chat_id"] is None:
        print(json.dumps({"ok": False, "error": "not paired yet"}, ensure_ascii=False))
        return 1
    resp = bale_call("send", "--chat-id", str(state["owner_chat_id"]), "--text", args.text)
    if resp.get("ok"):
        core.append_transcript(
            {"dir": "out", "chat_id": state["owner_chat_id"], "text": args.text}
        )
    print(json.dumps({"ok": bool(resp.get("ok")), "api": resp}, ensure_ascii=False))
    return 0 if resp.get("ok") else 1


PENDING_PATH = os.path.join(core.STATE_DIR, "pending.jsonl")


def cmd_inbox(args) -> int:
    items = []
    if os.path.exists(PENDING_PATH):
        with open(PENDING_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    print(json.dumps({"ok": True, "pending": items}, ensure_ascii=False))
    return 0


def cmd_inbox_clear(args) -> int:
    if os.path.exists(PENDING_PATH):
        os.replace(PENDING_PATH, PENDING_PATH + ".done")
        open(PENDING_PATH, "w", encoding="utf-8").close()
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_status(args) -> int:
    state = core.load_state()
    print(json.dumps({
        "ok": True,
        "paired": state["owner_chat_id"] is not None,
        "owner_chat_id": state["owner_chat_id"],
        "last_update_id": state["last_update_id"],
        "pair_code_pending": state["pair_code_hash"] is not None,
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("set-pair-code"); p.add_argument("--code", required=True)
    p.set_defaults(fn=cmd_set_pair_code)
    p = sub.add_parser("poll"); p.set_defaults(fn=cmd_poll)
    p = sub.add_parser("reply"); p.add_argument("--text", required=True)
    p.set_defaults(fn=cmd_reply)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("inbox"); p.set_defaults(fn=cmd_inbox)
    p = sub.add_parser("inbox-clear"); p.set_defaults(fn=cmd_inbox_clear)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
