"""
intelligence.py
Pattern analysis utilities for digest and daily summary building.
"""

import re
from collections import defaultdict

CVE_REGEX    = r"CVE-\d{4}-\d+"
APT_KEYWORDS = ["APT", "Lazarus", "Sandworm", "Cozy Bear",
                "Fancy Bear", "ScarCruft", "UAT", "China-linked",
                "Russia-linked", "Iran-linked", "North Korea"]


def extract_cves(text):
    return list(set(re.findall(CVE_REGEX, text, re.IGNORECASE)))


def extract_actors(text):
    found = []
    for actor in APT_KEYWORDS:
        if actor.lower() in text.lower():
            found.append(actor)
    return found


def trend_analysis(items):
    """Count keyword trends across a batch of items."""
    trends = defaultdict(int)

    for item in items:
        text = (
            item.get("title", "") + " " +
            " ".join(item.get("summary", []) if isinstance(item.get("summary"), list)
                     else [item.get("summary", "")])
        ).lower()

        patterns = {
            "RCE Activity":         ["rce", "remote code execution"],
            "APT Campaigns":        ["apt", "lazarus", "sandworm"],
            "Ransomware":           ["ransomware", "encryption"],
            "Zero-days":            ["zero-day", "0-day", "zeroday"],
            "Android Threats":      ["android"],
            "AI Security":          ["ai", "llm", "chatgpt", "deepfake"],
            "Supply Chain":         ["supply chain"],
            "Phishing":             ["phishing"],
            "Data Breach":          ["breach", "data leak", "exposed"],
            "Hardware/Chips":       ["chip", "cpu", "gpu", "snapdragon"],
            "Mobile/Phones":        ["iphone", "samsung", "pixel", "smartphone"],
        }

        for trend_name, keywords in patterns.items():
            if any(k in text for k in keywords):
                trends[trend_name] += 1

    return dict(sorted(trends.items(), key=lambda x: x[1], reverse=True))


def severity_breakdown(items):
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "MINIMAL": 0}
    for item in items:
        sev = item.get("severity", "LOW")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def top_by_severity(items, severity, limit=10):
    return [i for i in items if i.get("severity") == severity][:limit]


def source_breakdown(items):
    sources = defaultdict(int)
    for item in items:
        sources[item.get("source", "unknown")] += 1
    return dict(sorted(sources.items(), key=lambda x: x[1], reverse=True))
