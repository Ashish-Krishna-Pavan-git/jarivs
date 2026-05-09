"""
subscriber_store.py
Shared subscriber persistence for Telegram chat IDs.
"""

import json
import os
from typing import Iterable

from config import SUBSCRIBERS_FILE, TELEGRAM_CHAT_ID


def _default_subscribers() -> set[str]:
    return {str(TELEGRAM_CHAT_ID)} if TELEGRAM_CHAT_ID else set()


def load_subscribers() -> set[str]:
    os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)

    if not os.path.exists(SUBSCRIBERS_FILE):
        subs = _default_subscribers()
        save_subscribers(subs)
        return subs

    try:
        with open(SUBSCRIBERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(item).strip() for item in data if str(item).strip()}
    except Exception:
        pass

    subs = _default_subscribers()
    save_subscribers(subs)
    return subs


def save_subscribers(subscribers: Iterable[str]) -> None:
    os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)
    clean = sorted({str(item).strip() for item in subscribers if str(item).strip()})
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)

    try:
        from storage_backend import is_configured, push_state

        if is_configured():
            push_state(new_articles=[])
    except Exception:
        pass


def subscribe(chat_id: str) -> set[str]:
    subscribers = load_subscribers()
    subscribers.add(str(chat_id))
    save_subscribers(subscribers)
    return subscribers


def unsubscribe(chat_id: str) -> set[str]:
    subscribers = load_subscribers()
    subscribers.discard(str(chat_id))
    save_subscribers(subscribers)
    return subscribers
