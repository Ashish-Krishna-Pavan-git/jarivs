"""
storage_backend.py
Persistent storage via HuggingFace Dataset repo.
Syncs critical state files + article bundle to HF at cycle boundaries.
Solves the ephemeral filesystem problem on HF Spaces.

SETUP (one-time):
  1. Create a PRIVATE dataset repo on HF: e.g., "AKP-07/jarvis-data"
  2. Set env vars in HF Space secrets:
       HF_TOKEN       = your HuggingFace write token (Settings → Access Tokens)
       HF_STORAGE_REPO = AKP-07/jarvis-data
"""

import os
import json
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta

try:
    from huggingface_hub import HfApi, hf_hub_download, CommitOperationAdd
    HF_HUB_OK = True
except ImportError:
    HF_HUB_OK = False
    print("[HF_STORAGE] huggingface_hub not available — running ephemeral mode")

from config import (
    SEEN_FILE,
    DIGEST_STATE_FILE,
    TELEMETRY_FILE,
    PROVIDER_STATE_FILE,
    RUNTIME_STATE_FILE,
    SUBSCRIBERS_FILE,
)

REPO_ID   = os.getenv("HF_STORAGE_REPO", "")   # e.g. "AKP-07/jarvis-data"
HF_TOKEN  = os.getenv("HF_TOKEN", "")
TMP_DIR   = Path("/tmp/jarvis_hf")

# Files that MUST persist across restarts
CRITICAL_FILES = [
    SEEN_FILE,
    DIGEST_STATE_FILE,
    TELEMETRY_FILE,
    PROVIDER_STATE_FILE,
    RUNTIME_STATE_FILE,
    SUBSCRIBERS_FILE,
]

BUNDLE_FILE = "articles_bundle.json"   # Rolling 72-hour article bundle


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _enabled():
    return HF_HUB_OK and bool(HF_TOKEN) and bool(REPO_ID)


def _api():
    if not _enabled():
        return None
    return HfApi(token=HF_TOKEN)


def _ensure_repo():
    api = _api()
    if not api:
        return False
    try:
        api.repo_info(repo_id=REPO_ID, repo_type="dataset")
        return True
    except Exception:
        try:
            api.create_repo(repo_id=REPO_ID, repo_type="dataset", private=True)
            print(f"[HF_STORAGE] ✓ Created private dataset repo: {REPO_ID}")
            return True
        except Exception as e:
            print(f"[HF_STORAGE] ✗ Could not create repo: {e}")
            return False


def _download(remote_name, dest_path):
    """Download one file from HF Dataset repo → dest_path."""
    try:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        downloaded = hf_hub_download(
            repo_id=REPO_ID,
            filename=remote_name,
            repo_type="dataset",
            token=HF_TOKEN,
            local_dir=str(TMP_DIR),
            force_download=True,
        )
        shutil.copy2(downloaded, dest_path)
        return True
    except Exception as e:
        if "404" not in str(e) and "not found" not in str(e).lower():
            print(f"[HF_STORAGE] Pull {remote_name}: {e}")
        return False


def _upload(local_path, remote_name, commit_msg=None):
    """Upload one file from local_path → HF Dataset repo."""
    api = _api()
    if not api or not os.path.exists(local_path):
        return False
    for attempt in range(1, 4):
        try:
            api.upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=remote_name,
                repo_id=REPO_ID,
                repo_type="dataset",
                token=HF_TOKEN,
                commit_message=commit_msg or f"Update {remote_name}",
            )
            return True
        except Exception as e:
            if attempt == 3:
                print(f"[HF_STORAGE] Upload {remote_name}: {e}")
                return False
            time.sleep(attempt * 2)
    return False


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def pull_state(working_dir="."):
    """
    Pull all critical state files from HF at cycle start.
    Call this ONCE when the scheduler boots up.
    """
    if not _enabled():
        print("[HF_STORAGE] Not configured — running without persistence")
        return False

    _ensure_repo()
    pulled = 0
    for fname in CRITICAL_FILES:
        dest = os.path.join(working_dir, fname)
        if _download(fname, dest):
            print(f"[HF_STORAGE] ✓ Pulled {fname}")
            pulled += 1
        else:
            print(f"[HF_STORAGE] — {fname} not on HF yet (first run?)")

    print(f"[HF_STORAGE] Pull done: {pulled}/{len(CRITICAL_FILES)} files restored")
    return True


def push_state(working_dir=".", new_articles=None):
    """
    Push critical state files + new articles to HF at cycle end.
    Call this AFTER each cycle completes.
    new_articles: list of processed article dicts from this cycle
    """
    if not _enabled():
        return False

    pushed = 0

    # 1. Push state files
    for fname in CRITICAL_FILES:
        src = os.path.join(working_dir, fname)
        if _upload(src, fname):
            pushed += 1

    # 2. Build rolling article bundle (last 72h, max 3000 items)
    if new_articles:
        bundle_local = TMP_DIR / BUNDLE_FILE
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        # Restore the remote bundle first when this runtime starts fresh.
        if not bundle_local.exists():
            _download(BUNDLE_FILE, str(bundle_local))

        # Load existing bundle
        existing = []
        if bundle_local.exists():
            try:
                with open(bundle_local, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        # Prune to 72 hours
        cutoff = (datetime.utcnow() - timedelta(hours=72)).isoformat()
        existing = [a for a in existing if a.get("saved_at", "0") > cutoff]

        # Merge + deduplicate by fp
        seen_fps = {a.get("fp", a.get("title", "")) for a in existing}
        for a in new_articles:
            fp = a.get("fp", a.get("title", ""))
            if fp and fp not in seen_fps:
                existing.append(a)
                seen_fps.add(fp)

        # Keep newest 3000
        existing = existing[-3000:]

        with open(bundle_local, "w", encoding="utf-8") as f:
            json.dump(existing, f)

        if _upload(str(bundle_local), BUNDLE_FILE, "Update article bundle"):
            pushed += 1
            print(f"[HF_STORAGE] ✓ Bundle: {len(existing)} articles pushed")

    print(f"[HF_STORAGE] Push done: {pushed} files saved to HF Dataset")
    return True


def load_bundle(working_dir="."):
    """
    Load the article bundle for daily/weekly summaries.
    Used by storage.py's load_last_n_hours() to recover data after restart.
    Returns list of article dicts.
    """
    # Try local tmp copy first (fastest)
    bundle_local = TMP_DIR / BUNDLE_FILE
    if bundle_local.exists():
        try:
            with open(bundle_local) as f:
                return json.load(f)
        except Exception:
            pass

    # Try downloading from HF
    if _enabled():
        dest = TMP_DIR / BUNDLE_FILE
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        if _download(BUNDLE_FILE, str(dest)):
            try:
                with open(dest) as f:
                    return json.load(f)
            except Exception:
                pass

    return []


def is_configured():
    return _enabled()
