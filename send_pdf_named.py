#!/usr/bin/env python3
"""One-off: send the article PDF to the owner via Bale with a custom file name, no caption."""
import sys
import requests

sys.path.insert(0, ".")
from bale_relay import read_token, API_BASE

CHAT_ID = YOUR_BALE_CHAT_ID
PATH = "."
NAME = "اصل مقاله : حق دسترسی به منطق تصمیم گیری الگوریتمی از پردازش خودکار تا فناوری های هوشمند — کاربر.pdf"

token = read_token()
with open(PATH, "rb") as fh:
    r = requests.post(
        API_BASE.format(token) + "sendDocument",
        data={"chat_id": str(CHAT_ID)},
        files={"document": (NAME, fh, "application/pdf")},
        timeout=180,
    )
print("sendDocument:", r.status_code, r.text[:400])
