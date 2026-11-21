#!/usr/bin/env python3
"""One-off: send one file to the owner via the Bale bot (@YourBaleBot)."""
import sys
import requests

sys.path.insert(0, ".")
from bale_relay import read_token, API_BASE

CHAT_ID = YOUR_BALE_CHAT_ID
PATH = "."

token = read_token()
me = requests.post(API_BASE.format(token) + "getMe", json={}, timeout=30).json()
print("getMe ok:", me.get("ok"), (me.get("result") or {}).get("username"))

with open(PATH, "rb") as fh:
    r = requests.post(
        API_BASE.format(token) + "sendDocument",
        data={"chat_id": str(CHAT_ID), "caption": "صدای تمیزشده — نویز حذف و کیفیت تقویت شد"},
        files={"document": ("voice_enhanced.m4a", fh, "audio/mp4")},
        timeout=120,
    )
print("sendDocument:", r.status_code, r.text[:300])
