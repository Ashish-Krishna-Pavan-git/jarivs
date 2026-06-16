"""
storage_backend.py — HuggingFace Dataset persistence.

FIX: Now syncs today's cycle digest files (digest_cycle_N.json) to HF Dataset.
Previously these lived only in /tmp/ and were lost on Space restart, causing
the daily summary to have no AI content (ai_summary=None blank report).

Files synced:
  Critical : seen.json, digest_state.json, telemetry.json,
             runtime_state.json, data/subscribers.json
  Digests  : digests/YYYY-MM-DD/digest_cycle_N.json (today's + yesterday's)
  Optional : provider_state.json
  Bundle   : articles_bundle.json (rolling 72h article store)
"""

import os, json, shutil
from pathlib import Path
from datetime import datetime, timedelta

try:
    from huggingface_hub import HfApi, hf_hub_download
    HF_HUB_OK = True
except ImportError:
    HF_HUB_OK = False
    print("[HF_STORAGE] huggingface_hub not available — ephemeral mode")

REPO_ID  = os.getenv("HF_STORAGE_REPO","")
HF_TOKEN = os.getenv("HF_TOKEN","")
TMP_DIR  = Path("/tmp/jarvis_hf")

CRITICAL_FILES = [
    "seen.json",
    "digest_state.json",
    "telemetry.json",
    "runtime_state.json",
    "data/subscribers.json",
]
OPTIONAL_FILES = ["provider_state.json"]
BUNDLE_FILE    = "articles_bundle.json"


def _enabled():
    return HF_HUB_OK and bool(HF_TOKEN) and bool(REPO_ID)

def _api():
    return HfApi(token=HF_TOKEN) if _enabled() else None

def _ensure_repo():
    api = _api()
    if not api: return False
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
    try:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        downloaded = hf_hub_download(
            repo_id=REPO_ID, filename=remote_name, repo_type="dataset",
            token=HF_TOKEN, local_dir=str(TMP_DIR), force_download=True)
        shutil.copy2(downloaded, dest_path)
        return True
    except Exception as e:
        if not any(x in str(e) for x in ["404","not found","Entry Not Found"]):
            print(f"[HF_STORAGE] Pull {remote_name}: {e}")
        return False

def _upload(local_path, remote_name, commit_msg=None):
    api = _api()
    if not api or not os.path.exists(local_path): return False
    try:
        api.upload_file(
            path_or_fileobj=str(local_path), path_in_repo=remote_name,
            repo_id=REPO_ID, repo_type="dataset", token=HF_TOKEN,
            commit_message=commit_msg or f"Update {remote_name}")
        return True
    except Exception as e:
        print(f"[HF_STORAGE] Upload {remote_name}: {e}")
        return False


# ─── Digest Sync ──────────────────────────────────────────────────────────────
def _push_digests(days_back=1):
    """Push today's (and optionally yesterday's) digest files to HF."""
    try:
        from config import DAILY_DIR
    except ImportError:
        return 0
    pushed = 0
    for d in range(days_back+1):
        day = (datetime.utcnow()-timedelta(days=d)).strftime("%Y-%m-%d")
        digest_dir = os.path.join(DAILY_DIR, day)
        if not os.path.exists(digest_dir): continue
        for fname in os.listdir(digest_dir):
            if not (fname.startswith("digest_cycle_") and fname.endswith(".json")): continue
            local  = os.path.join(digest_dir, fname)
            remote = f"digests/{day}/{fname}"
            if _upload(local, remote): pushed += 1
    return pushed


def _pull_digests():
    """Restore today's digest files from HF on startup."""
    try:
        from config import DAILY_DIR
    except ImportError:
        return 0
    pulled = 0
    for d in range(2):  # today + yesterday
        day = (datetime.utcnow()-timedelta(days=d)).strftime("%Y-%m-%d")
        for i in range(1, 5):
            remote = f"digests/{day}/digest_cycle_{i}.json"
            dest   = os.path.join(DAILY_DIR, day, f"digest_cycle_{i}.json")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if _download(remote, dest): pulled += 1
    if pulled: print(f"[HF_STORAGE] ✓ Restored {pulled} digest file(s)")
    return pulled


# ─── Public API ───────────────────────────────────────────────────────────────
def pull_state(working_dir="."):
    if not _enabled():
        print("[HF_STORAGE] Not configured — ephemeral mode")
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
    for fname in OPTIONAL_FILES:
        dest = os.path.join(working_dir, fname)
        if _download(fname, dest):
            print(f"[HF_STORAGE] ✓ Pulled {fname} (optional)")
    _pull_digests()   # Restore digest files so daily summary has content
    print(f"[HF_STORAGE] Pull done: {pulled}/{len(CRITICAL_FILES)} files restored")
    return True


def push_state(working_dir=".", new_articles=None, cycle_num=None):
    if not _enabled(): return False
    pushed = 0
    for fname in CRITICAL_FILES:
        src = os.path.join(working_dir, fname)
        if os.path.exists(src) and _upload(src, fname): pushed += 1
    for fname in OPTIONAL_FILES:
        src = os.path.join(working_dir, fname)
        if os.path.exists(src): _upload(src, fname)

    # Push today's digest files
    digest_pushed = _push_digests(days_back=0)
    if digest_pushed:
        print(f"[HF_STORAGE] ✓ Synced {digest_pushed} digest file(s)")
        pushed += digest_pushed

    # Rolling article bundle
    if new_articles:
        bundle_local = TMP_DIR/BUNDLE_FILE
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        existing = []
        if bundle_local.exists():
            try:
                with open(bundle_local) as f: existing = json.load(f)
            except: existing = []
        cutoff = (datetime.utcnow()-timedelta(hours=72)).isoformat()
        existing = [a for a in existing if a.get("saved_at","0")>cutoff]
        seen_fps = {a.get("fp",a.get("title","")) for a in existing}
        for a in new_articles:
            fp = a.get("fp",a.get("title",""))
            if fp and fp not in seen_fps:
                existing.append(a); seen_fps.add(fp)
        existing = existing[-3000:]
        with open(bundle_local,"w") as f: json.dump(existing,f)
        if _upload(str(bundle_local), BUNDLE_FILE, "Update article bundle"):
            pushed += 1
            print(f"[HF_STORAGE] ✓ Bundle: {len(existing)} articles pushed")

    print(f"[HF_STORAGE] Push done: {pushed} items saved to HF Dataset")
    return True


def load_bundle(working_dir="."):
    bundle_local = TMP_DIR/BUNDLE_FILE
    if bundle_local.exists():
        try:
            with open(bundle_local) as f: return json.load(f)
        except: pass
    if _enabled():
        dest = TMP_DIR/BUNDLE_FILE
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        if _download(BUNDLE_FILE, str(dest)):
            try:
                with open(dest) as f: return json.load(f)
            except: pass
    return []


def is_configured():
    return _enabled()
