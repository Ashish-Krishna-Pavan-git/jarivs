"""
backend/utils/telegram_client.py
Centralized, production-grade Telegram API client for JARVIS.

Key Features:
1. IPv4 Enforcement: Overrides urllib3 socket family selection to prefer IPv4 (AF_INET).
   Eliminates IPv6 routing hangs and read timeouts on cloud environments like HF Spaces.
2. Sanitized Logging: Automatically masks bot tokens as bot*** in logs.
3. Detailed Instrumentation: Logs request start, completion, elapsed time (ms), HTTP status,
   response snippet, and full traceback on failure.
4. Granular Timeouts: Uses separate connect timeout (3.0s) and read timeout (20.0s).
5. Retry Logic: Automatic exponential backoff for transient network issues.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import traceback
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Force urllib3 to use IPv4 socket family to prevent IPv6 DNS hanging on cloud containers
try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

# Custom session with browser-like user agent and connection pooling
_session = requests.Session()
_session.trust_env = False  # Ignore HF Spaces proxy environment variables to force direct IPv4 connection
_session.headers.update({
    "User-Agent": "JARVIS-Intelligence-Bot/2.0 (+https://huggingface.co/spaces)",
    "Accept": "application/json",
})

# Configure retry adapter
_adapter = HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    ),
)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def mask_telegram_token(url_or_text: str) -> str:
    """Replace bot<TOKEN> in URLs or text with bot*** to prevent secret leaks in logs."""
    if not url_or_text:
        return ""
    return re.sub(r"/bot[0-9]+:[A-Za-z0-9_-]+/", "/bot***/", str(url_or_text))


def _log(level: str, message: str, **details: Any) -> None:
    """Log to jarvis_db event_logs table if available."""
    try:
        from jarvis_db import log_event
        # Sanitize any details strings
        clean_details = {}
        for k, v in (details or {}).items():
            clean_details[k] = mask_telegram_token(str(v)) if isinstance(v, str) else v
        log_event(level, "telegram_client", message, clean_details)
    except Exception:
        pass


def telegram_post(
    endpoint: str,
    token: str,
    payload: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    max_retries: int = 3,
    retry_on_read_timeout: bool = False,
) -> dict[str, Any]:
    """
    Execute a POST request to Telegram API with IPv4 enforcement, timing, and detailed logging.
    Returns response JSON dict if successful.
    Raises RuntimeError or requests Exception on failure.
    """
    try:
        from backend.config.config import IS_TELEGRAM_ENABLED
        if not IS_TELEGRAM_ENABLED:
            print(f"[TELEGRAM] Skipped POST {endpoint}: Telegram disabled by configuration.")
            return {"ok": False, "error": "Telegram is disabled by configuration"}
    except Exception:
        pass

    if not token:
        print("[TELEGRAM] ⚠️ Token not provided — skipping request.")
        return {"ok": False, "error": "No TELEGRAM_TOKEN provided"}

    url = f"https://api.telegram.org/bot{token}/{endpoint.lstrip('/')}"
    masked_url = mask_telegram_token(url)

    last_error: str | None = None
    last_status: int | None = None

    for attempt in range(1, max_retries + 1):
        import threading
        tid = threading.get_ident()
        chat_id = payload.get("chat_id") if payload else "N/A"
        psize = len(json.dumps(payload)) if payload else 0
        
        t0 = time.time()
        print(f"[TELEGRAM][Thread-{tid}] [{attempt}/{max_retries}] POST {masked_url} | chat_id={chat_id} | payload={psize}B | conn={connect_timeout}s, read={read_timeout}s")
        try:
            if files:
                resp = _session.post(url, data=payload, files=files, timeout=(connect_timeout, read_timeout))
            else:
                resp = _session.post(url, json=payload, timeout=(connect_timeout, read_timeout))

            elapsed = time.time() - t0
            last_status = resp.status_code
            snippet = resp.text[:200].replace("\n", " ")

            print(
                f"[TELEGRAM][Thread-{tid}] [{attempt}/{max_retries}] Finished POST {endpoint} "
                f"-> HTTP {resp.status_code} in {elapsed:.2f}s | Response: {snippet}"
            )
            if resp.status_code != 200:
                print(f"[TELEGRAM] Failure Response Body: {snippet}")

            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data
                last_error = f"Telegram API returned ok=False: {data.get('description', '')}"
                print(f"[TELEGRAM] ⚠️ {last_error}")
                _log("WARN", f"Telegram API returned error for {endpoint}", status=resp.status_code, response=data)

            elif resp.status_code == 429:
                retry_after = 5
                try:
                    retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                except Exception:
                    pass
                last_error = f"Rate limited (HTTP 429) — retry after {retry_after}s"
                print(f"[TELEGRAM] ⚠️ {last_error}")
                if attempt < max_retries:
                    time.sleep(retry_after)
                    continue

            elif resp.status_code in (400, 403):
                # Permanent user error (e.g. bot blocked by user or invalid chat ID)
                last_error = f"Permanent HTTP {resp.status_code}: {snippet}"
                print(f"[TELEGRAM] ✗ {last_error}")
                _log("ERROR", f"Telegram permanent failure for {endpoint}", status=resp.status_code, error=snippet)
                return {"ok": False, "status": resp.status_code, "error": last_error}

            else:
                last_error = f"HTTP {resp.status_code}: {snippet}"
                print(f"[TELEGRAM] ⚠️ Attempt {attempt} failed: {last_error}")

        except requests.exceptions.ReadTimeout as exc:
            elapsed = time.time() - t0
            last_error = f"ReadTimeout (read={read_timeout}s) after {elapsed:.2f}s: {exc}"
            print(f"[TELEGRAM] ✗ Attempt {attempt} read timeout after {elapsed:.2f}s: {exc}")
            _log("WARN", f"Telegram read timeout on {endpoint}", attempt=attempt, elapsed=round(elapsed, 2), error=str(exc))
            if not retry_on_read_timeout:
                print(f"[TELEGRAM] ⚠️ Not retrying {endpoint} to avoid duplicate notifications.")
                break

        except requests.exceptions.Timeout as exc:
            elapsed = time.time() - t0
            last_error = f"Timeout (conn={connect_timeout}s, read={read_timeout}s) after {elapsed:.2f}s: {exc}"
            print(f"[TELEGRAM] ✗ Attempt {attempt} timeout after {elapsed:.2f}s: {exc}")
            _log("WARN", f"Telegram timeout on {endpoint}", attempt=attempt, elapsed=round(elapsed, 2), error=str(exc))

        except requests.exceptions.ConnectionError as exc:
            elapsed = time.time() - t0
            last_error = f"Connection error after {elapsed:.2f}s: {exc}"
            print(f"[TELEGRAM] ✗ Attempt {attempt} connection error after {elapsed:.2f}s: {exc}")
            _log("WARN", f"Telegram connection error on {endpoint}", attempt=attempt, elapsed=round(elapsed, 2), error=str(exc))

        except Exception as exc:
            elapsed = time.time() - t0
            last_error = f"Unexpected error after {elapsed:.2f}s: {exc}"
            print(f"[TELEGRAM] ✗ Attempt {attempt} error: {exc}\n{traceback.format_exc()}")
            _log("ERROR", f"Telegram request exception on {endpoint}", attempt=attempt, error=str(exc))

        if attempt < max_retries:
            backoff = attempt * 2
            print(f"[TELEGRAM] Waiting {backoff}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(backoff)

    print(f"[TELEGRAM] ✗ All {max_retries} attempts failed for {endpoint}: {last_error}")
    return {"ok": False, "status": last_status, "error": last_error or "Unknown Telegram error"}


def telegram_get(
    endpoint: str,
    token: str,
    params: dict[str, Any] | None = None,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Execute a GET request to Telegram API with IPv4 enforcement and timing."""
    try:
        from backend.config.config import IS_TELEGRAM_ENABLED
        if not IS_TELEGRAM_ENABLED:
            print(f"[TELEGRAM] Skipped GET {endpoint}: Telegram disabled by configuration.")
            return {"ok": False, "error": "Telegram is disabled by configuration"}
    except Exception:
        pass

    if not token:
        return {"ok": False, "error": "No TELEGRAM_TOKEN provided"}

    url = f"https://api.telegram.org/bot{token}/{endpoint.lstrip('/')}"
    masked_url = mask_telegram_token(url)

    for attempt in range(1, max_retries + 1):
        import threading
        tid = threading.get_ident()
        t0 = time.time()
        print(f"[TELEGRAM][Thread-{tid}] [{attempt}/{max_retries}] GET {masked_url} (conn={connect_timeout}s, read={read_timeout}s)...")
        try:
            resp = _session.get(url, params=params, timeout=(connect_timeout, read_timeout))
            elapsed = time.time() - t0
            snippet = resp.text[:200].replace("\n", " ")
            print(
                f"[TELEGRAM][Thread-{tid}] [{attempt}/{max_retries}] Finished GET {endpoint} "
                f"-> HTTP {resp.status_code} in {elapsed:.2f}s | Response: {snippet}"
            )
            if resp.status_code != 200:
                print(f"[TELEGRAM] Failure Response Body: {snippet}")

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 409:
                # 409 Conflict: webhook active or duplicate poll instance
                return {"ok": False, "status": 409, "error": "409 Conflict: webhook active or duplicate polling"}
            else:
                print(f"[TELEGRAM] ⚠️ GET HTTP {resp.status_code}: {snippet}")
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"[TELEGRAM] ✗ GET {endpoint} error after {elapsed:.2f}s: {exc}")

        if attempt < max_retries:
            time.sleep(attempt * 2)

    return {"ok": False, "error": "GET request failed"}
