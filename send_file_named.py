#!/usr/bin/env python3
"""One-off: send the enhanced audio to the owner via Bale with a custom file name, no caption."""
import sys
import requests

sys.path.insert(0, ".")
from bale_relay import read_token, API_BASE

CHAT_ID = YOUR_BALE_CHAT_ID
PATH = "."
NAME = "کاربر.m4a"

token = read_token()
with open(PATH, "rb") as fh:
    r = requests.post(
        API_BASE.format(token) + "sendDocument",
        data={"chat_id": str(CHAT_ID)},
        files={"document": (NAME, fh, "audio/mp4")},
        timeout=120,
    )
print("sendDocument:", r.status_code, r.text[:400])
