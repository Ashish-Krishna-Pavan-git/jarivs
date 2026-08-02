from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, g, jsonify, make_response, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
# Keep local runs aligned with Docker: process environment wins over .env values.
load_dotenv(ROOT / ".env", override=False)

from jarvis_db import (
    DB_PATH,
    change_password,
    create_user,
    delete_source,
    disable_notification_channel,
    ensure_admin_user,
    get_setting,
    get_user,
    get_user_by_id,
    init_db,
    list_integrations,
    list_logs,
    list_mcp_servers,
    list_migration_records,
    list_model_providers,
    list_notification_channels,
    list_sources,
    list_users,
    log_event,
    schema_status,
    set_setting,
    upsert_integration,
    upsert_mcp_server,
    upsert_model_provider,
    upsert_notification_channel,
    upsert_source,
    update_user,
)
from security_utils import (
    apply_security_headers,
    hash_password,
    is_safe_external_url,
    issue_jwt,
    make_csrf_token,
    verify_jwt,
    verify_password,
)
from storage_backend import is_configured, pull_state

FRONTEND_DIST = ROOT / "frontend" / "dist"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.getenv("JWT_SECRET", "jarvis-dev-secret"))

init_db()
ensure_admin_user(hash_password)


@app.after_request
def _headers(response):
    return apply_security_headers(response, request)


@app.before_request
def _options():
    if request.method == "OPTIONS":
        return make_response("", 204)


def _json_body() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def _token() -> str:
    auth = request.headers.get("Authorization", "")
    return auth.split(None, 1)[1].strip() if auth.startswith("Bearer ") else request.cookies.get("jarvis_token", "")


def _current_user() -> dict[str, Any] | None:
    payload = verify_jwt(_token())
    if not payload:
        return None
    user = get_user_by_id(int(payload.get("user_id") or 0)) or get_user(str(payload.get("sub", "")))
    if not user or not user.get("active"):
        return None
    payload.update({"role": user["role"], "user_id": user["id"], "must_change_password": bool(user.get("must_change_password"))})
    g.user = payload
    return payload


def require_user(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        if user.get("must_change_password") and request.path != "/api/auth/change-password":
            return jsonify({"error": "password_change_required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        if user.get("role") != "admin":
            return jsonify({"error": "forbidden"}), 403
        if user.get("must_change_password") and request.path != "/api/auth/change-password":
            return jsonify({"error": "password_change_required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def require_csrf(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("X-CSRF-Token", "") != request.cookies.get("csrf_token", ""):
                return jsonify({"error": "csrf_failed"}), 403
        return fn(*args, **kwargs)
    return wrapper


def _safe_user(user: dict[str, Any]) -> dict[str, Any]:
    return {k: user.get(k) for k in ["id", "username", "role", "display_name", "must_change_password", "active"]}


def _login_response(user: dict[str, Any]):
    token = issue_jwt(user["username"], user["role"], int(user["id"]), bool(user.get("must_change_password")))
    csrf = make_csrf_token()
    res = jsonify({"token": token, "csrf": csrf, "user": _safe_user(user)})
    secure = request.scheme == "https"
    res.set_cookie("jarvis_token", token, httponly=True, secure=secure, samesite="Strict", max_age=43200)
    res.set_cookie("csrf_token", csrf, httponly=False, secure=secure, samesite="Strict", max_age=43200)
    return res


def _legacy_summary():
    from storage.legacy_data import summary
    return summary()


def _recent_items(hours: int) -> list[dict[str, Any]]:
    from storage import load_last_n_hours
    items = load_last_n_hours(hours)
    try:
        from storage.legacy_data import load_bundle
        seen = {item.get("fp") or item.get("title") for item in items}
        for item in load_bundle(hours):
            key = item.get("fp") or item.get("title")
            if key not in seen:
                item["_legacy"] = True
                items.append(item)
                seen.add(key)
    except Exception:
        pass
    return items


def _docs_context() -> str:
    parts = []
    for name in ["USER_GUIDE.md", "ADMIN_GUIDE.md", "TROUBLESHOOTING.md", "MCP.md", "INTEGRATIONS.md"]:
        path = ROOT / "docs" / name
        if path.exists():
            parts.append(f"# {name}\n{path.read_text(encoding='utf-8', errors='ignore')[:1600]}")
    return "\n\n".join(parts)[:7000]


def _path_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "files": 0, "bytes": 0}
    if path.is_file():
        return {"exists": True, "files": 1, "bytes": path.stat().st_size}
    files = [p for p in path.rglob("*") if p.is_file()]
    return {"exists": True, "files": len(files), "bytes": sum(p.stat().st_size for p in files)}


@app.route("/")
@app.route("/user")
@app.route("/admin")
@app.route("/admin/<path:_path>")
def spa(_path: str | None = None):
    if FRONTEND_DIST.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return "JARVIS backend online. Build frontend with `cd frontend && npm install && npm run build`."


@app.route("/assets/<path:path>")
def assets(path):
    return send_from_directory(FRONTEND_DIST / "assets", path)


@app.route("/ping")
def ping():
    return "pong"


@app.route("/health")
def health():
    return jsonify({"status": "ok", "db": True, "frontend": FRONTEND_DIST.exists(), "legacy_data": _legacy_summary().get("exists", False)})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = _json_body()
    user = get_user(str(data.get("username", "")))
    if not user or not verify_password(str(data.get("password", "")), user["password_hash"]):
        log_event("WARN", "auth", "Failed login", {"username": data.get("username", "")})
        return jsonify({"error": "invalid_credentials"}), 401
    log_event("INFO", "auth", "Login", {"username": user["username"]})
    return _login_response(user)


@app.route("/api/auth/me")
@require_user
def me():
    return jsonify({"user": _safe_user(get_user_by_id(int(g.user["user_id"])))})


@app.route("/api/auth/change-password", methods=["POST"])
@require_user
@require_csrf
def password_change():
    data = _json_body()
    new_password = str(data.get("new_password", ""))
    if len(new_password) < 12:
        return jsonify({"error": "password_too_short"}), 400
    user = get_user_by_id(int(g.user["user_id"]))
    if not verify_password(str(data.get("current_password", "")), user["password_hash"]):
        return jsonify({"error": "invalid_current_password"}), 400
    change_password(int(user["id"]), hash_password(new_password))
    return _login_response(get_user_by_id(int(user["id"])))


@app.route("/api/admin/overview")
@require_admin
def overview():
    from queue_manager import stats as queue_stats
    from runtime_state import load_runtime_state
    from telemetry import get_stats
    return jsonify({"runtime": load_runtime_state(), "telemetry": get_stats(), "queue": queue_stats(), "sources": len(list_sources()), "models": len(list_model_providers()), "users": len(list_users()), "legacy": _legacy_summary()})


@app.route("/api/admin/system/health")
@require_admin
def system_health():
    from queue_manager import stats as queue_stats
    from runtime_state import load_runtime_state
    from telemetry import get_stats
    return jsonify({"health": "ok", "runtime": load_runtime_state(), "telemetry": get_stats(), "queue": queue_stats(), "hf_storage_configured": is_configured(), "telegram_configured": bool(os.getenv("TELEGRAM_TOKEN"))})


@app.route("/api/admin/system/storage")
@require_admin
def system_storage():
    from config import ARCHIVE_DIR, DAILY_DIR, DATA_DIR, PROCESSED_DIR, RAW_DIR
    paths = {"data": DATA_DIR, "database": DB_PATH, "processed": PROCESSED_DIR, "daily": DAILY_DIR, "archive": ARCHIVE_DIR, "raw_articles": RAW_DIR, "legacy": os.getenv("JARVIS_LEGACY_DATA_DIR", str(ROOT / "jarvis-data"))}
    return jsonify({"paths": paths, "sizes": {k: _path_info(Path(v)) for k, v in paths.items()}, "legacy": _legacy_summary()})


@app.route("/api/admin/logs")
@require_admin
def logs():
    rows = list_logs(int(request.args.get("limit", 500)))
    level, component, q = request.args.get("level", "").upper(), request.args.get("component", "").lower(), request.args.get("q", "").lower()
    if level:
        rows = [r for r in rows if r.get("level") == level]
    if component:
        rows = [r for r in rows if component in str(r.get("component", "")).lower()]
    if q:
        rows = [r for r in rows if q in json.dumps(r, default=str).lower()]
    return jsonify({"logs": rows})


@app.route("/api/admin/sources", methods=["GET", "POST"])
@require_admin
@require_csrf
def sources():
    if request.method == "GET":
        return jsonify({"sources": list_sources()})
    data = _json_body()
    ok, reason = is_safe_external_url(str(data.get("url", "")))
    if not ok:
        return jsonify({"error": reason}), 400
    return jsonify({"source": upsert_source(data)})


@app.route("/api/admin/sources/<int:source_id>", methods=["DELETE"])
@require_admin
@require_csrf
def source_delete(source_id):
    delete_source(source_id)
    return jsonify({"ok": True})


@app.route("/api/admin/models", methods=["GET", "POST"])
@require_admin
@require_csrf
def models():
    if request.method == "GET":
        return jsonify({"providers": list_model_providers()})
    data = _json_body()
    base_url = str(data.get("base_url", "")).strip()
    if base_url and data.get("provider_type") != "ollama":
        ok, reason = is_safe_external_url(base_url)
        if not ok:
            return jsonify({"error": reason}), 400
    return jsonify({"provider": upsert_model_provider(data)})


@app.route("/api/admin/users", methods=["GET", "POST"])
@require_admin
@require_csrf
def users():
    if request.method == "GET":
        return jsonify({"users": list_users()})
    return jsonify({"user": create_user(_json_body(), hash_password)})


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@require_admin
@require_csrf
def user_update(user_id):
    try:
        return jsonify({"user": update_user(user_id, _json_body(), hash_password)})
    except ValueError:
        return jsonify({"error": "not_found"}), 404


@app.route("/api/admin/integrations", methods=["GET", "POST"])
@require_admin
@require_csrf
def integrations():
    if request.method == "GET":
        return jsonify({"integrations": list_integrations()})
    return jsonify({"integration": upsert_integration(_json_body())})


@app.route("/api/admin/notification-channels", methods=["GET", "POST"])
@require_admin
@require_csrf
def admin_channels():
    if request.method == "GET":
        return jsonify({"channels": list_notification_channels(include_disabled=True)})
    return jsonify({"channel": upsert_notification_channel(_json_body())})


@app.route("/api/admin/notification-channels/<int:channel_id>", methods=["DELETE"])
@require_admin
@require_csrf
def admin_channel_disable(channel_id):
    disable_notification_channel(channel_id)
    return jsonify({"ok": True})


@app.route("/api/admin/mcp", methods=["GET", "POST"])
@require_admin
@require_csrf
def mcp():
    if request.method == "GET":
        return jsonify({"servers": list_mcp_servers()})
    data = _json_body()
    if str(data.get("transport", "http")).lower() == "http":
        ok, reason = is_safe_external_url(str(data.get("endpoint", "")), bool((data.get("config") or {}).get("allow_private_network")))
        if not ok:
            return jsonify({"error": reason}), 400
    return jsonify({"server": upsert_mcp_server(data)})


@app.route("/api/admin/mcp/<int:server_id>/test", methods=["POST"])
@require_admin
@require_csrf
def mcp_test(server_id):
    from mcp_client import test_mcp_server
    server = next((s for s in list_mcp_servers() if int(s["id"]) == int(server_id)), None)
    return jsonify(test_mcp_server(server) if server else {"ok": False, "error": "not_found"})


@app.route("/api/mcp/http", methods=["POST"])
@require_user
@require_csrf
def mcp_http():
    from mcp_client import call_mcp
    data = _json_body()
    server = next((s for s in list_mcp_servers() if int(s["id"]) == int(data.get("server_id", 0)) and s.get("enabled")), None)
    if not server:
        return jsonify({"error": "not_found"}), 404
    try:
        return jsonify({"ok": True, "result": call_mcp(server, str(data.get("method", "initialize")), data.get("params") or {})})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/admin/migrations")
@require_admin
def migrations():
    return jsonify({"legacy": _legacy_summary(), "records": list_migration_records(500), "schema": schema_status()})


@app.route("/api/admin/run/<job>", methods=["POST"])
@require_admin
@require_csrf
def run_job(job):
    if job == "daily":
        from scheduler import run_daily
        threading.Thread(target=run_daily, daemon=True).start()
    elif job == "cycle":
        from scheduler import run_cycle
        threading.Thread(target=run_cycle, args=("Manual",), kwargs={"boot_cycle": False}, daemon=True).start()
    else:
        return jsonify({"error": "unknown_job"}), 400
    return jsonify({"ok": True})


@app.route("/api/user/status")
def user_status():
    from runtime_state import load_runtime_state
    from telemetry import get_stats
    return jsonify({"runtime": load_runtime_state(), "telemetry": get_stats(), "legacy": _legacy_summary()})


@app.route("/api/user/feed")
@require_user
def user_feed():
    hours = min(max(int(request.args.get("hours", 72) or 72), 1), 720)
    q, severity = request.args.get("q", "").lower(), request.args.get("severity", "").upper()
    items = _recent_items(hours)
    if severity:
        items = [i for i in items if str(i.get("severity", "")).upper() == severity]
    if q:
        items = [i for i in items if q in json.dumps(i, default=str).lower()]
    return jsonify({"items": sorted(items, key=lambda x: str(x.get("saved_at", "")), reverse=True)[:500], "hours": hours})


@app.route("/api/user/reports")
@require_user
def user_reports():
    from storage import load_digests as load_runtime_digests
    from storage.legacy_data import load_digests as load_legacy_digests

    days = min(max(int(request.args.get("days", 30) or 30), 1), 90)
    reports = load_runtime_digests(days) + load_legacy_digests(days)
    reports.sort(key=lambda item: str(item.get("report_date") or item.get("generated_at") or item.get("_legacy_path", "")), reverse=True)
    return jsonify({"reports": reports, "days": days})


@app.route("/api/user/assistant", methods=["POST"])
@require_user
@require_csrf
def assistant():
    data = _json_body()
    query = str(data.get("query") or "Explain how to use JARVIS")
    hours = min(max(int(data.get("hours", 48) or 48), 1), 168)
    context = "\n".join(f"[{i.get('severity')}] {i.get('title')}: {(i.get('summary_text') or '')[:300]}" for i in _recent_items(hours)[:60])
    prompt = f"You are the built-in JARVIS assistant. Help with usage, settings, errors, and recent intelligence.\n\nDocs:\n{_docs_context()}\n\nRecent intelligence:\n{context}\n\nQuestion: {query}\n\nAnswer clearly in plain text."
    try:
        from ai_router import local_call_text
        answer = local_call_text(prompt)
    except Exception:
        answer = None
    return jsonify({"answer": answer or "JARVIS helps collect, analyze, report, and notify. Use Feed for intelligence, Reports for digests, Notifications for Telegram/Slack, and Admin for sources, models, users, MCP, logs, storage, and health.", "items_considered": len(context)})


@app.route("/api/user/report", methods=["POST"])
def user_report_compat():
    return assistant()


@app.route("/api/user/preferences", methods=["GET", "POST"])
@require_user
@require_csrf
def preferences():
    key = f"user:{g.user['user_id']}:preferences"
    if request.method == "GET":
        try:
            prefs = json.loads(get_setting(key, "{}"))
        except Exception:
            prefs = {}
        return jsonify({"preferences": prefs})
    set_setting(key, json.dumps(_json_body()))
    return jsonify({"preferences": _json_body()})


@app.route("/api/user/notification-channels", methods=["GET", "POST"])
@require_user
@require_csrf
def user_channels():
    if request.method == "GET":
        return jsonify({"channels": list_notification_channels(user_id=int(g.user["user_id"]), include_disabled=True)})
    return jsonify({"channel": upsert_notification_channel(_json_body(), user_id=int(g.user["user_id"]))})


@app.route("/api/user/notification-channels/<int:channel_id>", methods=["DELETE"])
@require_user
@require_csrf
def user_channel_disable(channel_id):
    disable_notification_channel(channel_id, user_id=int(g.user["user_id"]))
    return jsonify({"ok": True})


@app.route(f"/telegram/<token>", methods=["POST"])
def telegram_webhook(token):
    if token != TELEGRAM_TOKEN:
        return "Unauthorized", 403
    try:
        update = request.get_json(force=True)
        if update:
            from bot_listener import handle_update
            threading.Thread(target=handle_update, args=(update,), daemon=True).start()
    except Exception as exc:
        log_event("ERROR", "telegram", "Webhook processing failed", {"error": str(exc)})
    return "ok", 200


def register_webhook() -> bool:
    if not TELEGRAM_TOKEN or not HF_SPACE_URL:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook", json={"url": f"{HF_SPACE_URL}/telegram/{TELEGRAM_TOKEN}", "drop_pending_updates": False}, timeout=25)
        return bool(r.json().get("ok"))
    except Exception:
        return False


def delete_webhook():
    if TELEGRAM_TOKEN:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", json={"drop_pending_updates": False}, timeout=15)
        except Exception:
            pass


def send_startup_message():
    if TELEGRAM_TOKEN and os.getenv("TELEGRAM_CHAT_ID"):
        time.sleep(8)
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": "JARVIS Online - intelligence system restarted."}, timeout=20)
        except Exception:
            pass


def main():
    print("[CLOUD] Starting JARVIS backend...")
    if is_configured():
        pull_state()
    webhook_ok = register_webhook()
    if not webhook_ok:
        delete_webhook()
        os.environ["HF_SPACE_URL"] = ""
    proc = subprocess.Popen([sys.executable, "scheduler.py"], env=os.environ.copy())
    print(f"[CLOUD] Scheduler started (pid={proc.pid})")
    threading.Thread(target=send_startup_message, daemon=True).start()
    app.run(host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
