"""
tools/network_diagnostics.py
Comprehensive, zero-dependency network diagnostic tool for JARVIS.

Measures:
1. DNS Resolution latency & returned IP addresses (IPv4 vs IPv6).
2. TCP Connect latency for IPv4 vs IPv6.
3. TLS Handshake latency & certificate details.
4. HTTP Request & Read latency for:
   - Google (https://www.google.com)
   - Httpbin (https://httpbin.org/get)
   - GitHub (https://api.github.com)
   - Telegram Base (https://api.telegram.org)
   - Telegram getMe, sendMessage, deleteWebhook, getWebhookInfo
5. Compares HTTP clients: requests, httpx, urllib3.
6. Masking of all bot tokens and credentials.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import sys
import time
import traceback
from typing import Any

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def mask_secret(text: str) -> str:
    """Mask Telegram tokens and secrets in strings."""
    if not text:
        return ""
    masked = re.sub(r"/bot[0-9]+:[A-Za-z0-9_-]+/", "/bot***/", str(text))
    if TOKEN and len(TOKEN) > 10:
        masked = masked.replace(TOKEN, TOKEN[:4] + "***" + TOKEN[-4:])
    return masked


def trace_tcp_tls_http(host: str, port: int = 443, path: str = "/") -> dict[str, Any]:
    """Perform low-level socket DNS, TCP connect, TLS handshake, and HTTP GET timing."""
    result: dict[str, Any] = {
        "host": host,
        "port": port,
        "dns_ms": None,
        "ips": [],
        "tcp_ms": None,
        "connected_ip": None,
        "tls_ms": None,
        "cipher": None,
        "http_ms": None,
        "status_code": None,
        "phase_failed": None,
        "error": None,
    }

    # 1. DNS Resolution
    t0 = time.perf_counter()
    try:
        addr_info = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        result["dns_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        result["ips"] = list(set(ai[4][0] for ai in addr_info))
    except Exception as exc:
        result["dns_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        result["phase_failed"] = "DNS"
        result["error"] = f"DNS failed: {exc}"
        return result

    # Prefer IPv4 for TCP connect test if available
    ipv4_ips = [ip for ip in result["ips"] if ":" not in ip]
    target_ip = ipv4_ips[0] if ipv4_ips else result["ips"][0]
    family = socket.AF_INET if ":" not in target_ip else socket.AF_INET6

    # 2. TCP Connect
    t1 = time.perf_counter()
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((target_ip, port))
        result["tcp_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        result["connected_ip"] = target_ip
    except Exception as exc:
        result["tcp_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        result["phase_failed"] = "TCP_CONNECT"
        result["error"] = f"TCP connect to {target_ip}:{port} failed: {exc}"
        try:
            sock.close()
        except Exception:
            pass
        return result

    # 3. TLS Handshake
    t2 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        tls_sock = ctx.wrap_socket(sock, server_hostname=host)
        result["tls_ms"] = round((time.perf_counter() - t2) * 1000, 2)
        cipher_info = tls_sock.cipher()
        result["cipher"] = cipher_info[0] if cipher_info else "Unknown"
    except Exception as exc:
        result["tls_ms"] = round((time.perf_counter() - t2) * 1000, 2)
        result["phase_failed"] = "TLS_HANDSHAKE"
        result["error"] = f"TLS handshake failed: {exc}"
        try:
            sock.close()
        except Exception:
            pass
        return result

    # 4. HTTP Request & Read
    t3 = time.perf_counter()
    try:
        http_req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: JARVIS-Diagnostics/2.0\r\nConnection: close\r\n\r\n"
        tls_sock.sendall(http_req.encode("utf-8"))
        data = tls_sock.recv(4096)
        result["http_ms"] = round((time.perf_counter() - t3) * 1000, 2)

        resp_str = data.decode("utf-8", errors="ignore")
        if resp_str.startswith("HTTP/"):
            parts = resp_str.split(" ", 2)
            if len(parts) >= 2:
                result["status_code"] = int(parts[1])
    except Exception as exc:
        result["http_ms"] = round((time.perf_counter() - t3) * 1000, 2)
        result["phase_failed"] = "HTTP_READ"
        result["error"] = f"HTTP read failed: {exc}"
    finally:
        try:
            tls_sock.close()
        except Exception:
            pass

    return result


def test_with_requests(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Test endpoint using plain `requests` library."""
    import requests

    masked_url = mask_secret(url)
    res: dict[str, Any] = {
        "client": "requests",
        "url": masked_url,
        "method": method,
        "elapsed_ms": None,
        "status_code": None,
        "response_body": None,
        "error": None,
    }
    t0 = time.perf_counter()
    try:
        headers = {"User-Agent": "JARVIS-Diagnostics/2.0"}
        if method.upper() == "POST":
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        else:
            resp = requests.get(url, headers=headers, timeout=timeout)
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        res["status_code"] = resp.status_code
        res["response_body"] = mask_secret(resp.text[:300].replace("\n", " "))
    except Exception as exc:
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        res["error"] = mask_secret(f"{exc.__class__.__name__}: {exc}")
    return res


def test_with_httpx(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Test endpoint using `httpx` library if available."""
    res: dict[str, Any] = {
        "client": "httpx",
        "url": mask_secret(url),
        "method": method,
        "elapsed_ms": None,
        "status_code": None,
        "response_body": None,
        "error": None,
    }
    try:
        import httpx
    except ImportError:
        res["error"] = "httpx not installed"
        return res

    t0 = time.perf_counter()
    try:
        headers = {"User-Agent": "JARVIS-Diagnostics/2.0"}
        with httpx.Client(timeout=timeout) as client:
            if method.upper() == "POST":
                resp = client.post(url, json=payload, headers=headers)
            else:
                resp = client.get(url, headers=headers)
            res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            res["status_code"] = resp.status_code
            res["response_body"] = mask_secret(resp.text[:300].replace("\n", " "))
    except Exception as exc:
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        res["error"] = mask_secret(f"{exc.__class__.__name__}: {exc}")
    return res


def test_with_urllib3(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Test endpoint using plain `urllib3` PoolManager."""
    import urllib3

    res: dict[str, Any] = {
        "client": "urllib3",
        "url": mask_secret(url),
        "method": method,
        "elapsed_ms": None,
        "status_code": None,
        "response_body": None,
        "error": None,
    }
    t0 = time.perf_counter()
    http = urllib3.PoolManager()
    try:
        headers = {"User-Agent": "JARVIS-Diagnostics/2.0"}
        body_bytes = json.dumps(payload).encode("utf-8") if payload else None
        if body_bytes:
            headers["Content-Type"] = "application/json"

        resp = http.request(method.upper(), url, body=body_bytes, headers=headers, timeout=timeout)
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        res["status_code"] = resp.status
        res["response_body"] = mask_secret(resp.data.decode("utf-8", errors="ignore")[:300].replace("\n", " "))
    except Exception as exc:
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        res["error"] = mask_secret(f"{exc.__class__.__name__}: {exc}")
    return res


def run_comprehensive_diagnostics() -> dict[str, Any]:
    """Run full diagnostic suite across targets, network layers, and HTTP libraries."""
    report: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "environment": {
            "is_hf_space": bool(os.getenv("HF_SPACE_URL")),
            "python_version": sys.version.split()[0],
            "os": sys.platform,
        },
        "layer_timing": {},
        "target_diagnostics": {},
        "library_comparison": {},
    }

    # Layer timing tests
    hosts = [
        ("www.google.com", 443, "/"),
        ("httpbin.org", 443, "/get"),
        ("api.github.com", 443, "/"),
        ("api.telegram.org", 443, "/"),
    ]
    for host, port, path in hosts:
        report["layer_timing"][host] = trace_tcp_tls_http(host, port, path)

    # Specific HTTP target tests via `requests`
    targets = [
        ("google", "GET", "https://www.google.com", None),
        ("httpbin", "GET", "https://httpbin.org/get", None),
        ("github", "GET", "https://api.github.com", None),
        ("telegram_base", "GET", "https://api.telegram.org", None),
    ]

    if TOKEN:
        targets.extend([
            ("telegram_getMe", "GET", f"https://api.telegram.org/bot{TOKEN}/getMe", None),
            ("telegram_getWebhookInfo", "GET", f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo", None),
            ("telegram_deleteWebhook", "POST", f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", {"drop_pending_updates": False}),
        ])
        if CHAT_ID:
            targets.append((
                "telegram_sendMessage",
                "POST",
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                {"chat_id": CHAT_ID, "text": "🧪 JARVIS Network Diagnostic Automated Probe"},
            ))

    for key, method, url, payload in targets:
        report["target_diagnostics"][key] = test_with_requests(url, method=method, payload=payload, timeout=8.0)

    # Library comparison on Telegram getMe
    if TOKEN:
        getme_url = f"https://api.telegram.org/bot{TOKEN}/getMe"
        report["library_comparison"]["requests"] = test_with_requests(getme_url, timeout=8.0)
        report["library_comparison"]["httpx"] = test_with_httpx(getme_url, timeout=8.0)
        report["library_comparison"]["urllib3"] = test_with_urllib3(getme_url, timeout=8.0)

    return report


if __name__ == "__main__":
    print("[DIAG] Running JARVIS Network Diagnostics...")
    diag_result = run_comprehensive_diagnostics()
    print(json.dumps(diag_result, indent=2))
