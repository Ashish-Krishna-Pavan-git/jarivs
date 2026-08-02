"""
slack_notifier.py — Slack delivery engine for JARVIS.

Supports:
1. Webhook URL resolution from .env (SLACK_WEBHOOK_URL), DB integrations, and DB notification channels.
2. Sanitized logging (masks Slack webhook tokens in logs).
3. Connect vs Read timeouts with retry logic.
4. Detailed event logging to jarvis_db event_logs.
"""

from __future__ import annotations

import os
import re
import time
import traceback

import requests


def mask_slack_url(url: str) -> str:
    """Mask Slack webhook tokens in URLs for safe logging."""
    if not url:
        return ""
    return re.sub(r"services/B[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+", "services/B***/B***/***", str(url))


def _log(level: str, message: str, **details) -> None:
    try:
        from jarvis_db import log_event
        clean_details = {}
        for k, v in (details or {}).items():
            clean_details[k] = mask_slack_url(str(v)) if isinstance(v, str) else v
        log_event(level, "slack", message, clean_details)
    except Exception:
        pass


def _webhook_urls() -> list[str]:
    urls = []
    env_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if env_url:
        urls.append(env_url)
    try:
        from jarvis_db import list_integrations, list_notification_channels
        for item in list_integrations():
            if item.get("kind") == "slack" and item.get("enabled"):
                config = item.get("config") or {}
                url = str(config.get("webhook_url") or "").strip()
                if url:
                    urls.append(url)
        for channel in list_notification_channels():
            if channel.get("kind") == "slack" and channel.get("enabled"):
                secret = channel.get("secret") or {}
                target = str(channel.get("target") or "").strip()
                url = str(secret.get("webhook_url") or target).strip()
                if url and url.startswith("http"):
                    urls.append(url)
    except Exception:
        pass
    return sorted(set(urls))


def send_slack_message(text: str, max_retries: int = 3) -> bool:
    urls = _webhook_urls()
    if not urls:
        _log("WARN", "Slack notification skipped: No Slack webhooks configured")
        return False

    success_count = 0
    text_content = str(text or "")[:35000]

    for url in urls:
        masked_url = mask_slack_url(url)
        delivered = False
        for attempt in range(1, max_retries + 1):
            t0 = time.time()
            print(f"[SLACK] [{attempt}/{max_retries}] Sending message to {masked_url}...")
            try:
                payload = {"text": text_content}
                res = requests.post(url, json=payload, timeout=(3.0, 15.0))
                elapsed = time.time() - t0
                body_snippet = res.text[:200].replace("\n", " ")

                print(f"[SLACK] [{attempt}/{max_retries}] Finished {masked_url} -> HTTP {res.status_code} in {elapsed:.2f}s | Response: {body_snippet}")

                if 200 <= res.status_code < 300:
                    delivered = True
                    _log("INFO", f"Slack message delivered ({elapsed:.2f}s)", url=masked_url, status=res.status_code)
                    break
                else:
                    _log("WARN", f"Slack HTTP {res.status_code}", url=masked_url, status=res.status_code, body=body_snippet)
            except Exception as exc:
                elapsed = time.time() - t0
                print(f"[SLACK] ✗ Attempt {attempt} error after {elapsed:.2f}s: {exc}")
                _log("WARN", f"Slack request error attempt {attempt}", url=masked_url, elapsed=round(elapsed, 2), error=str(exc))

            if attempt < max_retries:
                time.sleep(attempt * 2)

        if delivered:
            success_count += 1

    return success_count > 0
