"""Read-only bridge for old production data in jarvis-data/."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCKER_LEGACY = Path("/legacy/jarvis-data")
LEGACY_DIR = Path(os.getenv("JARVIS_LEGACY_DATA_DIR", DOCKER_LEGACY if DOCKER_LEGACY.exists() else ROOT / "jarvis-data"))


def exists() -> bool:
    return LEGACY_DIR.exists() and LEGACY_DIR.is_dir()


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def summary() -> dict[str, Any]:
    if not exists():
        return {"exists": False, "path": str(LEGACY_DIR), "articles_bundle": 0, "digest_files": 0}
    digest_count = len(list((LEGACY_DIR / "digests").glob("**/*.json"))) if (LEGACY_DIR / "digests").exists() else 0
    bundle = _load_json(LEGACY_DIR / "articles_bundle.json", [])
    return {
        "exists": True,
        "path": str(LEGACY_DIR),
        "articles_bundle": len(bundle) if isinstance(bundle, list) else 0,
        "digest_files": digest_count,
        "has_seen": (LEGACY_DIR / "seen.json").exists(),
        "has_telemetry": (LEGACY_DIR / "telemetry.json").exists(),
        "has_runtime_state": (LEGACY_DIR / "runtime_state.json").exists(),
        "has_subscribers": (LEGACY_DIR / "data" / "subscribers.json").exists(),
    }


def load_bundle(hours: int | None = None) -> list[dict[str, Any]]:
    data = _load_json(LEGACY_DIR / "articles_bundle.json", [])
    if not isinstance(data, list):
        return []
    if not hours:
        return data
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    out = []
    for item in data:
        ts = item.get("saved_at") or item.get("generated_at")
        try:
            if ts and datetime.fromisoformat(str(ts)) >= cutoff:
                out.append(item)
        except Exception:
            pass
    return out


def load_digests(days: int = 30) -> list[dict[str, Any]]:
    if not exists():
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    out = []
    root = LEGACY_DIR / "digests"
    if not root.exists():
        return out
    for path in sorted(root.glob("**/digest_cycle_*.json"), reverse=True):
        try:
            day = datetime.fromisoformat(path.parent.name)
            if day < cutoff:
                continue
        except Exception:
            pass
        data = _load_json(path, None)
        if isinstance(data, dict):
            data["_legacy_path"] = str(path)
            out.append(data)
    return out


def load_subscribers() -> list[str]:
    data = _load_json(LEGACY_DIR / "data" / "subscribers.json", [])
    return [str(item) for item in data] if isinstance(data, list) else []


def load_telemetry() -> dict[str, Any]:
    data = _load_json(LEGACY_DIR / "telemetry.json", {})
    return data if isinstance(data, dict) else {}
