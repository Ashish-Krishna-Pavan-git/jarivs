"""
subscriber_store.py
Shared subscriber persistence for Telegram chat IDs.
Uses SUBSCRIBERS_FILE from config (now correctly defined).
Syncs to HF Dataset on every change via storage_backend.
"""

import json
import os
from typing import Iterable

from config import SUBSCRIBERS_FILE, TELEGRAM_CHAT_ID


def _default_subscribers() -> set:
    return {str(TELEGRAM_CHAT_ID)} if TELEGRAM_CHAT_ID else set()


def load_subscribers() -> set:
    os.makedirs(os.path.dirname(os.path.abspath(SUBSCRIBERS_FILE)), exist_ok=True)

    if not os.path.exists(SUBSCRIBERS_FILE):
        subs = _default_subscribers()
        save_subscribers(subs)
        return subs

    try:
        with open(SUBSCRIBERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            subs = {str(item).strip() for item in data if str(item).strip()}
            try:
                from jarvis_db import list_notification_channels
                for channel in list_notification_channels():
                    if channel.get("kind") == "telegram" and channel.get("enabled") and channel.get("target"):
                        subs.add(str(channel["target"]))
            except Exception:
                pass
            return subs
    except Exception:
        pass

    subs = _default_subscribers()
    save_subscribers(subs)
    return subs


def save_subscribers(subscribers: Iterable) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(SUBSCRIBERS_FILE)), exist_ok=True)
    clean = sorted({str(item).strip() for item in subscribers if str(item).strip()})
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)

    # Sync to HF Dataset so subscribers persist across Space restarts
    try:
        from storage_backend import is_configured, push_state
        if is_configured():
            push_state(new_articles=[])
    except Exception:
        pass


def subscribe(chat_id: str) -> set:
    subscribers = load_subscribers()
    subscribers.add(str(chat_id))
    save_subscribers(subscribers)
    try:
        from jarvis_db import upsert_notification_channel
        upsert_notification_channel({
            "kind": "telegram",
            "label": f"Telegram {chat_id}",
            "target": str(chat_id),
            "secret": {"chat_id": str(chat_id)},
            "enabled": True,
        })
    except Exception:
        pass
    return subscribers


def unsubscribe(chat_id: str) -> set:
    subscribers = load_subscribers()
    subscribers.discard(str(chat_id))
    save_subscribers(subscribers)
    try:
        from jarvis_db import disable_notification_channel, list_notification_channels
        for channel in list_notification_channels(include_disabled=True):
            if channel.get("kind") == "telegram" and str(channel.get("target")) == str(chat_id):
                disable_notification_channel(int(channel["id"]))
    except Exception:
        pass
    return subscribers
