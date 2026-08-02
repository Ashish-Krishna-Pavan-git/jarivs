"""
internet_monitor.py
Waits for internet before starting a cycle.
"""

import requests
import socket
import time

try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

TEST_URLS = [
    "https://www.google.com",
    "https://api.telegram.org",
    "https://www.cloudflare.com",
]


def internet_available():
    for url in TEST_URLS:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 500:
                return True
        except:
            continue
    return False


def wait_for_internet(retry_mins=10):
    print("[NET] Checking internet...")
    while True:
        if internet_available():
            print("[NET] Connected ✓")
            return True
        print(f"[NET] No internet — retrying in {retry_mins} min")
        time.sleep(retry_mins * 60)
