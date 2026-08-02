"""
tools/raw_hf_diagnostics.py
Raw, unadulterated diagnostic tool to execute exact network tests on Hugging Face Space.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()


def mask_secret(text: str) -> str:
    if not text:
        return ""
    masked = re.sub(r"/bot[0-9]+:[A-Za-z0-9_-]+/", "/bot***/", str(text))
    if TOKEN and len(TOKEN) > 10:
        masked = masked.replace(TOKEN, TOKEN[:4] + "***" + TOKEN[-4:])
    return masked


def run_cmd(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = (res.stdout or "") + ("\nSTDERR:\n" + res.stderr if res.stderr else "")
        return mask_secret(out.strip())
    except Exception as exc:
        return f"ERROR executing {' '.join(cmd)}: {exc}"


def execute_raw_diagnostics() -> dict[str, Any]:
    output: dict[str, Any] = {}

    # 1. socket.getaddrinfo
    print("--- 1. socket.getaddrinfo('api.telegram.org', 443) ---")
    try:
        addrs = socket.getaddrinfo("api.telegram.org", 443)
        output["1_getaddrinfo"] = [str(a) for a in addrs]
    except Exception as exc:
        addrs = []
        output["1_getaddrinfo"] = f"ERROR: {exc}"
    print(json.dumps(output["1_getaddrinfo"], indent=2))

    # 2. Raw AF_INET6 socket connect
    print("\n--- 2. AF_INET6 Socket Connect ---")
    v6_ips = [a[4][0] for a in addrs if a[0] == socket.AF_INET6] if isinstance(addrs, list) else []
    if v6_ips:
        ip6 = v6_ips[0]
        t0 = time.time()
        try:
            s6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            s6.settimeout(10.0)
            s6.connect((ip6, 443))
            s6.close()
            output["2_ipv6_connect"] = f"SUCCESS: Connected to [{ip6}]:443 in {round(time.time() - t0, 3)}s"
        except Exception as exc:
            output["2_ipv6_connect"] = f"EXCEPTION after {round(time.time() - t0, 3)}s: {exc.__class__.__name__}: {exc}"
    else:
        output["2_ipv6_connect"] = "SKIPPED: No IPv6 address in getaddrinfo"
    print(output["2_ipv6_connect"])

    # 3. Raw AF_INET socket connect
    print("\n--- 3. AF_INET Socket Connect ---")
    v4_ips = [a[4][0] for a in addrs if a[0] == socket.AF_INET] if isinstance(addrs, list) else []
    if v4_ips:
        ip4 = v4_ips[0]
        t0 = time.time()
        try:
            s4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s4.settimeout(10.0)
            s4.connect((ip4, 443))
            s4.close()
            output["3_ipv4_connect"] = f"SUCCESS: Connected to {ip4}:443 in {round(time.time() - t0, 3)}s"
        except Exception as exc:
            output["3_ipv4_connect"] = f"EXCEPTION after {round(time.time() - t0, 3)}s: {exc.__class__.__name__}: {exc}"
    else:
        output["3_ipv4_connect"] = "SKIPPED: No IPv4 address in getaddrinfo"
    print(output["3_ipv4_connect"])

    # 4. curl -4 getMe
    print("\n--- 4. curl -4 getMe ---")
    if TOKEN:
        output["4_curl_ipv4"] = run_cmd(["curl", "-4", "-v", "-s", f"https://api.telegram.org/bot{TOKEN}/getMe"])
    else:
        output["4_curl_ipv4"] = "SKIPPED: TELEGRAM_TOKEN missing"
    print(output["4_curl_ipv4"])

    # 5. curl -6 getMe
    print("\n--- 5. curl -6 getMe ---")
    if TOKEN:
        output["5_curl_ipv6"] = run_cmd(["curl", "-6", "-v", "-s", f"https://api.telegram.org/bot{TOKEN}/getMe"])
    else:
        output["5_curl_ipv6"] = "SKIPPED: TELEGRAM_TOKEN missing"
    print(output["5_curl_ipv6"])

    # 6. System Network Info
    print("\n--- 6. System Interface & Route Info ---")
    output["6_network_info"] = {
        "ip_addr": run_cmd(["ip", "addr"]),
        "ip_route": run_cmd(["ip", "route"]),
        "ip6_route": run_cmd(["ip", "-6", "route"]),
        "resolv_conf": run_cmd(["cat", "/etc/resolv.conf"]),
    }
    print(json.dumps(output["6_network_info"], indent=2))

    return output


if __name__ == "__main__":
    execute_raw_diagnostics()
