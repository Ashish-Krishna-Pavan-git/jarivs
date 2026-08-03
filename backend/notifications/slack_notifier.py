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


def send_slack_audio(filepath: str, caption: str = "🎙️ Today's Intelligence Podcast", max_retries: int = 2) -> dict:
    """
    Upload an audio file (or audio report notice) to Slack.
    
    1. Detects SLACK_BOT_TOKEN and SLACK_CHANNEL_ID.
    2. If only Incoming Webhooks are configured:
       - Posts text notice to Slack webhook: audio file generated locally.
       - Logs clear explanation that Incoming Webhooks cannot process file uploads.
       - Returns {"ok": False, "reason": "webhook_only", "message": "Incoming Webhooks cannot upload files. Configure SLACK_BOT_TOKEN and SLACK_CHANNEL_ID."}
    3. If SLACK_BOT_TOKEN and SLACK_CHANNEL_ID exist:
       - Uploads file using Slack API (files.upload) with progress logging and retries.
       - Returns {"ok": True, "message": "Audio podcast uploaded to Slack successfully"}
    """
    if not os.path.exists(filepath):
        _log("WARN", f"Slack audio skipped: File not found ({filepath})")
        return {"ok": False, "error": f"Audio file not found: {filepath}"}

    bot_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    channel_id = os.getenv("SLACK_CHANNEL_ID", "").strip()

    # Search integrations/channels DB for configured bot_token / channel_id if not in env
    if not (bot_token and channel_id):
        try:
            from jarvis_db import list_integrations, list_notification_channels
            for item in list_integrations():
                if item.get("kind") == "slack" and item.get("enabled"):
                    cfg = item.get("config") or {}
                    if cfg.get("bot_token") and cfg.get("channel_id"):
                        bot_token = str(cfg["bot_token"]).strip()
                        channel_id = str(cfg["channel_id"]).strip()
            for channel in list_notification_channels():
                if channel.get("kind") == "slack" and channel.get("enabled"):
                    sec = channel.get("secret") or {}
                    if sec.get("bot_token") and (sec.get("channel_id") or channel.get("target")):
                        bot_token = str(sec["bot_token"]).strip()
                        channel_id = str(sec.get("channel_id") or channel.get("target")).strip()
        except Exception:
            pass

    filename = os.path.basename(filepath)
    file_size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)

    # 1. Graceful degradation when only Incoming Webhooks are available
    if not (bot_token and channel_id):
        webhook_urls = _webhook_urls()
        print(f"[SLACK] ⚠️ Audio upload unavailable via Webhook for {filename} ({file_size_mb} MB). Incoming Webhooks cannot upload files.")
        _log("WARN", f"Audio upload unavailable: Incoming Webhooks cannot upload files. Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID.")
        
        if webhook_urls:
            notice_text = (
                f"🎙️ *{caption}*\n"
                f"🔊 Audio podcast generated: `{filename}` ({file_size_mb} MB).\n"
                f"_Note: Configure SLACK_BOT_TOKEN & SLACK_CHANNEL_ID to upload mp3 files directly to Slack._"
            )
            send_slack_message(notice_text)
            return {
                "ok": False,
                "reason": "webhook_only",
                "message": "Daily report posted to Slack. Audio upload unavailable because Incoming Webhooks cannot upload files. Configure SLACK_BOT_TOKEN and SLACK_CHANNEL_ID for file uploads."
            }
        return {
            "ok": False,
            "reason": "not_configured",
            "message": "Slack is not configured with a Bot Token or Webhook URL."
        }

    # 2. Upload file using Slack Bot Token (Slack Upload V2 API: getUploadURLExternal -> POST upload_url -> completeUploadExternal)
    headers_auth = {"Authorization": f"Bearer {bot_token}"}
    file_size_bytes = os.path.getsize(filepath)
    last_error = None

    for attempt in range(1, max_retries + 1):
        t0 = time.time()
        print(f"[SLACK] [{attempt}/{max_retries}] Starting Slack Upload V2 for {filename} ({file_size_mb} MB) to channel {channel_id}...")
        try:
            # Step 1: Request upload URL from Slack API
            step1_resp = requests.post(
                "https://slack.com/api/files.getUploadURLExternal",
                headers=headers_auth,
                data={
                    "filename": filename,
                    "length": file_size_bytes,
                },
                timeout=(10.0, 30.0)
            )
            
            if step1_resp.status_code != 200:
                last_error = f"Step 1 HTTP {step1_resp.status_code}: {step1_resp.text[:200]}"
                print(f"[SLACK] ✗ Attempt {attempt} Step 1 failed: {last_error}")
                _log("WARN", f"Slack Upload V2 Step 1 HTTP {step1_resp.status_code}", error=last_error)
                if attempt < max_retries:
                    time.sleep(attempt * 2)
                continue

            step1_json = step1_resp.json()
            if not step1_json.get("ok"):
                err_detail = step1_json.get("error", "getUploadURLExternal failed")
                last_error = f"Slack API error (Step 1): {err_detail}"
                print(f"[SLACK] ✗ Attempt {attempt} Step 1 API error: {err_detail}")
                _log("WARN", f"Slack Upload V2 Step 1 API error", error=err_detail)
                if attempt < max_retries:
                    time.sleep(attempt * 2)
                continue

            upload_url = step1_json.get("upload_url")
            file_id = step1_json.get("file_id")

            if not (upload_url and file_id):
                last_error = "Step 1 returned missing upload_url or file_id"
                print(f"[SLACK] ✗ Attempt {attempt} Step 1 payload error")
                if attempt < max_retries:
                    time.sleep(attempt * 2)
                continue

            # Step 2: Upload file binary to upload_url
            print(f"[SLACK] [{attempt}/{max_retries}] Uploading {file_size_mb} MB binary to Slack external storage...")
            with open(filepath, "rb") as file_bytes:
                step2_resp = requests.post(
                    upload_url,
                    data=file_bytes.read(),
                    timeout=(15.0, 120.0)
                )

            if step2_resp.status_code not in (200, 201):
                last_error = f"Step 2 binary upload failed (HTTP {step2_resp.status_code})"
                print(f"[SLACK] ✗ Attempt {attempt} Step 2 failed: {last_error}")
                _log("WARN", f"Slack Upload V2 Step 2 HTTP {step2_resp.status_code}", error=last_error)
                if attempt < max_retries:
                    time.sleep(attempt * 2)
                continue

            # Step 3: Complete upload and share to Slack channel
            print(f"[SLACK] [{attempt}/{max_retries}] Completing Slack upload for file {file_id}...")
            complete_payload = {
                "files": [
                    {
                        "id": file_id,
                        "title": f"JARVIS Podcast - {filename}",
                    }
                ],
                "channel_id": channel_id,
                "initial_comment": caption,
            }
            
            step3_resp = requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=complete_payload,
                timeout=(10.0, 30.0)
            )

            elapsed = time.time() - t0
            if step3_resp.status_code == 200:
                step3_json = step3_resp.json()
                if step3_json.get("ok"):
                    print(f"[SLACK] ✓ Audio podcast {filename} uploaded via Upload V2 to channel {channel_id} in {elapsed:.2f}s")
                    _log("INFO", f"Slack audio Upload V2 succeeded ({elapsed:.2f}s)", channel=channel_id, filename=filename, file_id=file_id)
                    return {"ok": True, "message": f"Audio podcast uploaded successfully via Slack Upload V2 to channel {channel_id}"}
                else:
                    err_detail = step3_json.get("error", "completeUploadExternal failed")
                    last_error = f"Slack API error (Step 3): {err_detail}"
                    print(f"[SLACK] ✗ Attempt {attempt} Step 3 API error: {err_detail}")
                    _log("WARN", f"Slack Upload V2 Step 3 API error", error=err_detail)
            else:
                last_error = f"Step 3 HTTP {step3_resp.status_code}: {step3_resp.text[:200]}"
                print(f"[SLACK] ✗ Attempt {attempt} Step 3 HTTP {step3_resp.status_code}")
                _log("WARN", f"Slack Upload V2 Step 3 HTTP {step3_resp.status_code}", status=step3_resp.status_code)

        except Exception as exc:
            elapsed = time.time() - t0
            last_error = str(exc)
            print(f"[SLACK] ✗ Attempt {attempt} exception after {elapsed:.2f}s: {exc}")
            _log("WARN", f"Slack Upload V2 exception attempt {attempt}", error=str(exc))

        if attempt < max_retries:
            time.sleep(attempt * 2)

    return {"ok": False, "error": last_error or "Slack audio Upload V2 failed after retries"}
