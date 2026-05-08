"""Quick Telegram connection test."""
import os
import requests
from dotenv import load_dotenv
load_dotenv()

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print(f"TOKEN  : {'SET ✓' if TOKEN else 'MISSING ✗'}")
print(f"CHAT_ID: {'SET ✓' if CHAT_ID else 'MISSING ✗'}")

if not TOKEN or not CHAT_ID:
    print("❌ Configure .env first")
    exit(1)

r = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    json={"chat_id": CHAT_ID, "text": "✅ JARVIS connected and operational!"},
    timeout=15
)
print(f"Status : {r.status_code}")
print("✅ Working!" if r.status_code == 200 else f"❌ Error: {r.text}")
