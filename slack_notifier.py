"""Slack delivery channel using encrypted admin/user notification channels."""

from __future__ import annotations

import os

import requests

from jarvis_db import list_integrations, list_notification_channels, log_event


def _webhook_urls() -> list[str]:
    urls = []
    env_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if env_url:
        urls.append(env_url)
    try:
        for item in list_integrations():
            if item.get("kind") == "slack" and item.get("enabled"):
                url = str((item.get("config") or {}).get("webhook_url", "")).strip()
                if url:
                    urls.append(url)
        for channel in list_notification_channels():
            if channel.get("kind") == "slack" and channel.get("enabled"):
                secret = channel.get("secret") or {}
                url = str(secret.get("webhook_url") or channel.get("target") or "").strip()
                if url:
                    urls.append(url)
    except Exception:
        pass
    return sorted(set(urls))


def send_slack_message(text: str) -> bool:
    ok = False
    for url in _webhook_urls():
        try:
            response = requests.post(url, json={"text": str(text)[:35000]}, timeout=20)
            if 200 <= response.status_code < 300:
                log_event("INFO", "slack", "Slack message sent")
                ok = True
            else:
                log_event("WARN", "slack", f"Slack send failed: HTTP {response.status_code}", {"body": response.text[:300]})
        except Exception as exc:
            log_event("ERROR", "slack", f"Slack send error: {exc}")
    return ok
