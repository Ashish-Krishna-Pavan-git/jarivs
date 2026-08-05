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
    clear_logs,
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


import hmac

def _is_secure_request() -> bool:
    return request.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https"


def require_csrf(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            header_csrf = request.headers.get("X-CSRF-Token", "")
            cookie_csrf = request.cookies.get("csrf_token", "")
            user_payload = getattr(g, "user", None) or verify_jwt(_token()) or {}
            jwt_csrf = user_payload.get("csrf", "")

            if not header_csrf:
                return jsonify({"error": "csrf_failed"}), 403

            if cookie_csrf and hmac.compare_digest(header_csrf, cookie_csrf):
                pass
            elif jwt_csrf and hmac.compare_digest(header_csrf, jwt_csrf):
                pass
            else:
                return jsonify({"error": "csrf_failed"}), 403
        return fn(*args, **kwargs)
    return wrapper


def _safe_user(user: dict[str, Any]) -> dict[str, Any]:
    return {k: user.get(k) for k in ["id", "username", "role", "display_name", "must_change_password", "active"]}


def _login_response(user: dict[str, Any]):
    csrf = make_csrf_token()
    token = issue_jwt(user["username"], user["role"], int(user["id"]), bool(user.get("must_change_password")), csrf=csrf)
    res = jsonify({"token": token, "csrf": csrf, "user": _safe_user(user)})
    secure = _is_secure_request()
    samesite = "None" if secure else "Lax"
    res.set_cookie("jarvis_token", token, httponly=True, secure=secure, samesite=samesite, max_age=43200)
    res.set_cookie("csrf_token", csrf, httponly=False, secure=secure, samesite=samesite, max_age=43200)
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
@app.route("/login")
@app.route("/user")
@app.route("/user/<path:_path>")
@app.route("/admin")
@app.route("/admin/<path:_path>")
def spa(_path: str | None = None):
    if FRONTEND_DIST.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return "JARVIS backend online. Build frontend with `cd frontend && npm install && npm run build`."


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/") or request.path.startswith("/assets/"):
        return jsonify({"error": "Not Found", "path": request.path}), 404
    if FRONTEND_DIST.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify({"error": "Not Found", "path": request.path}), 404


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


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    res = jsonify({"ok": True})
    res.delete_cookie("jarvis_token")
    res.delete_cookie("csrf_token")
    return res


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
    from ai_router import get_ai_status
    return jsonify({"runtime": load_runtime_state(), "telemetry": get_stats(), "queue": queue_stats(), "sources": len(list_sources()), "models": len(list_model_providers()), "users": len(list_users()), "legacy": _legacy_summary(), "ai_status": get_ai_status()})


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


@app.route("/api/admin/notification-channels/test", methods=["POST"])
@require_admin
@require_csrf
def admin_channel_test():
    """Test a notification channel (Telegram/Slack) and return a visible result."""
    from notifier import test_channel
    data = _json_body()
    return jsonify(test_channel(str(data.get("kind", "")), str(data.get("target", "")), data.get("secret") or {}))


@app.route("/api/admin/notification-provider", methods=["GET", "POST"])
@require_admin
def admin_notification_provider():
    from backend.config.config import get_notification_provider_info, set_notification_provider
    if request.method == "GET":
        return jsonify(get_notification_provider_info())
    data = request.json or {}
    res = set_notification_provider(data.get("provider"))
    return jsonify(res)


@app.route("/api/admin/wordpress/test", methods=["POST"])
@require_admin
def admin_wordpress_test():
    """Diagnostic endpoint to test WordPress REST API authentication, roles, capabilities, and draft operations."""
    from newsletter_publisher import test_wordpress_connection
    res = test_wordpress_connection()
    return jsonify(res)


@app.route("/api/admin/ai-status")
@require_admin
def ai_status():
    """Return current AI routing status for UI visibility."""
    from ai_router import get_ai_status
    return jsonify(get_ai_status())


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


@app.route("/api/admin/testing/live-state")
@require_admin
def testing_live_state():
    from queue_manager import stats as queue_stats
    from runtime_state import load_runtime_state
    from telemetry import get_stats
    from ai_router import get_ai_status
    from config import ARCHIVE_DIR, DAILY_DIR, DATA_DIR, PROCESSED_DIR, RAW_DIR
    
    paths = {"data": DATA_DIR, "database": DB_PATH, "processed": PROCESSED_DIR, "daily": DAILY_DIR, "archive": ARCHIVE_DIR, "raw_articles": RAW_DIR}
    storage_sizes = {k: _path_info(Path(v)) for k, v in paths.items()}
    
    paused = get_setting("pipeline:paused", "0") == "1"
    err_logs = list_logs(50)
    recent_errors = [l for l in err_logs if l.get("level") == "ERROR"][:15]
    
    return jsonify({
        "runtime": load_runtime_state(),
        "pipeline_paused": paused,
        "queue": queue_stats(),
        "ai_status": get_ai_status(),
        "telemetry": get_stats(),
        "storage": storage_sizes,
        "recent_errors": recent_errors,
        "counts": {
            "sources": len(list_sources()),
            "sources_enabled": len([s for s in list_sources() if s.get("enabled")]),
            "providers": len(list_model_providers()),
            "providers_enabled": len([p for p in list_model_providers() if p.get("enabled")]),
            "mcp_servers": len(list_mcp_servers()),
            "channels": len(list_notification_channels(include_disabled=True)),
        }
    })


@app.route("/api/admin/testing/pipeline-toggle", methods=["POST"])
@require_admin
@require_csrf
def testing_pipeline_toggle():
    from runtime_state import update_runtime_state
    current = get_setting("pipeline:paused", "0") == "1"
    next_val = "0" if current else "1"
    set_setting("pipeline:paused", next_val)
    is_paused = next_val == "1"
    update_runtime_state(phase="paused" if is_paused else "idle")
    log_event("INFO", "testing", f"Pipeline {'paused' if is_paused else 'resumed'} by admin")
    return jsonify({"ok": True, "paused": is_paused})


@app.route("/api/admin/testing/run-collection", methods=["POST"])
@require_admin
@require_csrf
def testing_run_collection():
    from collector import collect_all
    from dedupe import get_new_articles
    from queue_manager import add_batch
    raw = collect_all(limit_per_source=15)
    new_articles = get_new_articles(raw)
    if new_articles:
        add_batch(new_articles)
    log_event("INFO", "testing", "Manual collection test completed", {"collected": len(raw), "new": len(new_articles)})
    return jsonify({"ok": True, "collected": len(raw), "new": len(new_articles)})


@app.route("/api/admin/testing/run-ai-analysis", methods=["POST"])
@require_admin
@require_csrf
def testing_run_ai_analysis():
    from ai_router import ai_analyze, get_ai_status
    data = _json_body()
    title = str(data.get("title") or "Test Security Vulnerability Advisory")
    content = str(data.get("content") or "Critical remote code execution vulnerability discovered in widespread open-source library. Active exploitation observed in the wild. CVE-2026-8888.")
    result = ai_analyze(title, content)
    return jsonify({"ok": True, "analysis": result, "ai_status": get_ai_status()})


@app.route("/api/admin/testing/run-notification", methods=["POST"])
@require_admin
@require_csrf
def testing_run_notification():
    from notifier import test_channel
    results = []
    channels = list_notification_channels(include_disabled=False)
    if not channels:
        if TELEGRAM_TOKEN and os.getenv("TELEGRAM_CHAT_ID"):
            results.append({"kind": "telegram", "target": os.getenv("TELEGRAM_CHAT_ID"), **test_channel("telegram", os.getenv("TELEGRAM_CHAT_ID"))})
        if os.getenv("SLACK_WEBHOOK_URL"):
            results.append({"kind": "slack", "target": "SLACK_WEBHOOK_URL", **test_channel("slack", os.getenv("SLACK_WEBHOOK_URL"))})
    else:
        for ch in channels:
            res = test_channel(ch.get("kind"), ch.get("target"), ch.get("secret") or {})
            results.append({"id": ch.get("id"), "label": ch.get("label"), "kind": ch.get("kind"), "target": ch.get("target"), **res})
    return jsonify({"ok": True, "results": results})


@app.route("/api/admin/testing/run-report", methods=["POST"])
@require_admin
@require_csrf
def testing_run_report():
    from scheduler import run_cycle
    threading.Thread(target=run_cycle, args=("Test Run",), kwargs={"boot_cycle": False}, daemon=True).start()
    return jsonify({"ok": True, "message": "Report generation cycle started in background"})


@app.route("/api/admin/testing/trigger-test-alert", methods=["POST"])
@require_admin
@require_csrf
def testing_trigger_test_alert():
    from notifier import notify_immediate
    test_item = {
        "title": "🚨 TEST CRITICAL THREAT: Zero-Day Vulnerability Simulation",
        "link": "https://example.com/cve-2026-99999",
        "source": "JARVIS Diagnostics",
        "severity": "CRITICAL",
        "category": "cybersec",
        "cves": ["CVE-2026-99999"],
        "actors": ["APT-TEST"],
        "summary": ["This is a simulated critical threat alert generated from Command Center to verify Telegram and Slack end-to-end notification delivery."],
        "confidence": 9,
    }
    delivered = notify_immediate(test_item)
    return jsonify({"ok": True, "delivered": delivered, "message": "Test critical alert processed by notification pipeline"})


@app.route("/api/admin/notification-diagnostics", methods=["GET"])
@require_admin
def admin_notification_diagnostics():
    from jarvis_db import get_notification_diagnostics
    return jsonify({"ok": True, "diagnostics": get_notification_diagnostics()})


@app.route("/api/admin/network/diagnostics", methods=["GET"])
@require_admin
def admin_network_diagnostics():
    from tools.network_diagnostics import run_comprehensive_diagnostics
    results = run_comprehensive_diagnostics()
    return jsonify({"ok": True, "diagnostics": results})


@app.route("/api/admin/testing/test-providers", methods=["POST"])
@require_admin
@require_csrf
def testing_test_providers():
    providers = list_model_providers()
    results = []
    for p in providers:
        if not p.get("enabled"):
            results.append({"id": p.get("id"), "name": p.get("name"), "provider_type": p.get("provider_type"), "model": p.get("model"), "ok": False, "skipped": True, "error": "Provider disabled"})
            continue
        t0 = time.time()
        kind = str(p.get("provider_type", "")).lower()
        pname = p.get("name")
        pmodel = p.get("model")
        test_prompt = "Return JSON: {\"status\": \"ok\"}"
        ok = False
        err = None
        try:
            if kind == "gemini":
                from ai_router import gemini_call
                res = gemini_call(test_prompt, retries=1, model=pmodel)
                ok = bool(res)
            elif kind == "groq":
                from ai_router import groq_call
                res = groq_call(test_prompt, model=pmodel, retries=1)
                ok = bool(res)
            elif kind == "ollama":
                from ai_router import _ollama_call
                res = _ollama_call(p, test_prompt, json_mode=True)
                ok = bool(res)
            elif kind in {"openai", "openai_compatible", "custom"}:
                from ai_router import _openai_compatible_call
                res = _openai_compatible_call(p, test_prompt, json_mode=True)
                ok = bool(res)
            else:
                err = f"Unknown provider type: {kind}"
        except Exception as exc:
            err = str(exc)
        latency = round((time.time() - t0) * 1000, 1)
        results.append({
            "id": p.get("id"),
            "name": pname,
            "provider_type": kind,
            "model": pmodel,
            "ok": ok and not err,
            "latency_ms": latency,
            "error": err if not ok else None
        })
    return jsonify({"ok": True, "providers": results})


@app.route("/api/admin/testing/test-collectors", methods=["POST"])
@require_admin
@require_csrf
def testing_test_collectors():
    import feedparser
    sources = list_sources()
    results = []
    for s in sources:
        if not s.get("enabled"):
            results.append({"id": s.get("id"), "name": s.get("name"), "url": s.get("url"), "ok": False, "skipped": True, "error": "Source disabled"})
            continue
        t0 = time.time()
        ok = False
        count = 0
        err = None
        try:
            feed = feedparser.parse(s["url"])
            if feed.entries or feed.get("status") in (200, 301, 302):
                ok = True
                count = len(feed.entries)
            else:
                err = f"Feed parse returned status {feed.get('status', 'unknown')}"
        except Exception as exc:
            err = str(exc)
        latency = round((time.time() - t0) * 1000, 1)
        results.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "url": s.get("url"),
            "category": s.get("category"),
            "ok": ok,
            "articles_found": count,
            "latency_ms": latency,
            "error": err
        })
    return jsonify({"ok": True, "sources": results})


@app.route("/api/admin/testing/test-mcp", methods=["POST"])
@require_admin
@require_csrf
def testing_test_mcp():
    from mcp_client import test_mcp_server
    servers = list_mcp_servers()
    results = []
    for s in servers:
        res = test_mcp_server(s)
        results.append({"id": s.get("id"), "name": s.get("name"), "transport": s.get("transport"), **res})
    return jsonify({"ok": True, "servers": results})


@app.route("/api/admin/testing/clear", methods=["POST"])
@require_admin
@require_csrf
def testing_clear():
    data = _json_body()
    target = str(data.get("target", "")).lower()
    from config import ARCHIVE_DIR, DAILY_DIR, DATA_DIR, PROCESSED_DIR, RAW_DIR, SEEN_FILE
    from queue_manager import clear_all as clear_queue_all, stats as queue_stats
    from dedupe import reset_cache, seen_count
    from runtime_state import update_runtime_state
    
    cleared = []
    uncleared = []

    if target in ("reports", "all", "clear_all_test_data"):
        for d in [DAILY_DIR, ARCHIVE_DIR]:
            p = Path(d)
            if p.exists():
                for item in list(p.rglob("*")):
                    if item.is_file():
                        try:
                            item.unlink()
                        except Exception as exc:
                            uncleared.append(f"Report file {item.name}: {exc}")
                for sub in list(p.rglob("*"))[::-1]:
                    if sub.is_dir():
                        try:
                            sub.rmdir()
                        except Exception:
                            pass
        cleared.append("reports")

    if target in ("logs", "alerts", "all", "clear_all_test_data"):
        try:
            clear_logs()
            cleared.append("logs")
            cleared.append("alerts")
        except Exception as exc:
            uncleared.append(f"Event logs table: {exc}")

    if target in ("articles", "all", "clear_all_test_data"):
        for d in [PROCESSED_DIR, RAW_DIR, Path(DATA_DIR) / "audio"]:
            p = Path(d)
            if p.exists():
                for item in list(p.rglob("*")):
                    if item.is_file():
                        try:
                            item.unlink()
                        except Exception as exc:
                            uncleared.append(f"Article/audio file {item.name}: {exc}")
                for sub in list(p.rglob("*"))[::-1]:
                    if sub.is_dir():
                        try:
                            sub.rmdir()
                        except Exception:
                            pass
        clear_queue_all()
        cleared.append("articles")
        cleared.append("queue")

    if target in ("cache", "all", "clear_all_test_data"):
        p = Path(SEEN_FILE)
        if p.exists():
            try:
                p.unlink()
            except Exception as exc:
                uncleared.append(f"Fingerprint cache file: {exc}")
        reset_cache()
        cleared.append("cache")

    update_runtime_state(phase="idle", queue_total=0, queue_done=0, queue_failed=0, current_item_title="")
    log_event("INFO", "testing", f"Maintenance cleanup executed for targets: {', '.join(cleared)}", {"uncleared": uncleared})

    def _count_files(dir_path: str) -> int:
        p = Path(dir_path)
        return len([f for f in p.rglob("*") if f.is_file()]) if p.exists() else 0

    verification = {
        "daily_reports_count": _count_files(DAILY_DIR),
        "archive_reports_count": _count_files(ARCHIVE_DIR),
        "processed_articles_count": _count_files(PROCESSED_DIR),
        "raw_articles_count": _count_files(RAW_DIR),
        "queue_total": queue_stats().get("total", 0),
        "dedupe_fingerprints_count": seen_count(),
        "event_logs_count": len(list_logs(100)),
        "remaining_uncleared": uncleared,
    }

    verified_clean = (
        verification["daily_reports_count"] == 0 and
        verification["archive_reports_count"] == 0 and
        verification["processed_articles_count"] == 0 and
        verification["raw_articles_count"] == 0 and
        verification["queue_total"] == 0 and
        verification["dedupe_fingerprints_count"] == 0 and
        len(uncleared) == 0
    )

    return jsonify({
        "ok": True,
        "cleared": cleared,
        "verified_clean": verified_clean,
        "verification": verification,
    })


@app.route("/api/admin/testing/reset-scheduler", methods=["POST"])
@require_admin
@require_csrf
def testing_reset_scheduler():
    from queue_manager import clear_all, reset_stuck
    from runtime_state import update_runtime_state
    reset_stuck()
    clear_all()
    update_runtime_state(phase="idle", queue_total=0, queue_done=0, queue_failed=0, current_item_title="")
    log_event("INFO", "testing", "Scheduler queue and runtime state reset by admin")
    return jsonify({"ok": True})


@app.route("/api/admin/config/reload", methods=["POST"])
@app.route("/api/admin/testing/reload-config", methods=["POST"])
@require_admin
@require_csrf
def testing_reload_config():
    from backend.config.config import reload_config
    res = reload_config()
    init_db()
    log_event("INFO", "config", "Configuration reloaded at runtime", res)
    return jsonify({"ok": True, "config": res})


@app.route("/api/admin/models/summary", methods=["GET"])
@require_admin
def admin_models_summary():
    from ai_router import get_models_summary
    return jsonify(get_models_summary())


@app.route("/api/admin/mcp/source-audit", methods=["POST"])
@require_admin
@require_csrf
def admin_mcp_source_audit():
    from backend.mcp.source_auditor import mcp_audit_sources
    res = mcp_audit_sources()
    log_event("INFO", "mcp", "Executed MCP Source Audit", res.get("summary", {}))
    return jsonify(res)


@app.route("/api/admin/channels/<int:channel_id>", methods=["DELETE"])
@app.route("/api/admin/notification-channels/<int:channel_id>", methods=["DELETE"])
@require_admin
@require_csrf
def admin_channel_delete(channel_id):
    from jarvis_db import delete_notification_channel
    delete_notification_channel(channel_id)
    if is_configured():
        try:
            from backend.storage.storage_backend import push_state
            push_state()
        except Exception:
            pass
    log_event("INFO", "notifier", f"Deleted notification channel {channel_id}")
    return jsonify({"ok": True})


_scheduler_proc = None


def restart_scheduler():
    global _scheduler_proc
    if _scheduler_proc and _scheduler_proc.poll() is None:
        try:
            _scheduler_proc.terminate()
            _scheduler_proc.wait(timeout=3)
        except Exception:
            try:
                _scheduler_proc.kill()
            except Exception:
                pass
    _scheduler_proc = subprocess.Popen([sys.executable, "scheduler.py"], env=os.environ.copy())
    print(f"[CLOUD] Scheduler process started (pid={_scheduler_proc.pid})")
    return _scheduler_proc.pid


@app.route("/api/admin/factory-reset", methods=["POST"])
@require_admin
@require_csrf
def admin_factory_reset():
    """Perform a TRUE Factory Reset:
    - Resets JARVIS to the exact state of a brand-new deployment
    - Wipes all runtime data: scraped/processed articles, seen cache, digest state, telemetry,
      runtime state, queue, daily/archive reports, audio briefings, podcasts, images, drafts,
      wordpress post logs, AI router cache, and event logs.
    - Preserves admin account, passwords, database schema, sources, AI model providers, notification channels, and .env.
    - Restarts the scheduler subprocess cleanly.
    """
    from config import ARCHIVE_DIR, DAILY_DIR, DATA_DIR, DIGEST_STATE_FILE, PROCESSED_DIR, RAW_DIR, SEEN_FILE
    from dedupe import reset_cache
    from jarvis_db import clear_logs, list_model_providers, list_notification_channels, list_sources, list_users, log_event
    from queue_manager import clear_all as clear_queue_all
    from runtime_state import reset_runtime_state
    from telemetry import reset_telemetry
    from ai_router import reset_ai_status

    uncleared = []

    # 1. Reset Telemetry & Runtime State & AI Router State
    try:
        reset_telemetry()
    except Exception as exc:
        uncleared.append(f"Telemetry reset: {exc}")

    try:
        reset_runtime_state()
    except Exception as exc:
        uncleared.append(f"Runtime state reset: {exc}")

    try:
        reset_ai_status()
    except Exception as exc:
        pass

    # 2. Clear Queue
    try:
        clear_queue_all()
    except Exception as exc:
        uncleared.append(f"Queue clear: {exc}")

    # 3. Clear Dedupe Cache & Seen File
    p_seen = Path(SEEN_FILE)
    if p_seen.exists():
        try:
            p_seen.unlink()
        except Exception as exc:
            uncleared.append(f"Seen file: {exc}")
    try:
        reset_cache()
    except Exception as exc:
        uncleared.append(f"Dedupe cache: {exc}")

    # 4. Clear Digest State & WP Post Log Files
    for state_file in [DIGEST_STATE_FILE, Path(DATA_DIR) / "wordpress_posts.jsonl", Path("/tmp/jarvis/data/wordpress_posts.jsonl")]:
        p = Path(state_file)
        if p.exists():
            try:
                p.unlink()
            except Exception as exc:
                uncleared.append(f"File {p.name}: {exc}")

    # 5. Clear ALL Runtime Data Directories & Generated Assets (Articles, Audio, Images, Reports, Drafts, PDFs)
    target_dirs = [
        Path(RAW_DIR),
        Path(PROCESSED_DIR),
        Path(DAILY_DIR),
        Path(ARCHIVE_DIR),
        Path(DATA_DIR) / "audio",
        Path(DATA_DIR) / "images",
        Path(DATA_DIR) / "podcasts",
        Path(DATA_DIR) / "drafts",
        Path(DATA_DIR) / "reports",
        Path(DATA_DIR) / "cache",
        Path("/tmp/jarvis/data/audio"),
        Path("/tmp/jarvis/processed"),
        Path("/tmp/jarvis/raw_articles"),
    ]
    for d in target_dirs:
        if d.exists():
            for item in list(d.rglob("*")):
                if item.is_file():
                    try:
                        item.unlink()
                    except Exception as exc:
                        uncleared.append(f"File {item.name}: {exc}")
            for sub in list(d.rglob("*"))[::-1]:
                if sub.is_dir():
                    try:
                        sub.rmdir()
                    except Exception:
                        pass

    # 6. Clear Event Logs Table in Database
    try:
        clear_logs()
    except Exception as exc:
        uncleared.append(f"Event logs: {exc}")

    # 6b. Sync Clean Reset State to Hugging Face Dataset if storage is enabled
    if is_configured():
        try:
            from backend.storage.storage_backend import push_state
            push_state()
            print("[HF_STORAGE] ✓ Synced clean reset state to HF Dataset")
        except Exception as exc:
            uncleared.append(f"HF storage sync: {exc}")

    # 7. Restart Scheduler Subprocess
    new_pid = None
    try:
        new_pid = restart_scheduler()
    except Exception as exc:
        uncleared.append(f"Scheduler restart: {exc}")

    log_event("INFO", "factory_reset", "True Factory Reset executed by admin", {"scheduler_pid": new_pid, "uncleared": uncleared})

    return jsonify({
        "ok": True,
        "message": "True Factory Reset completed successfully.",
        "scheduler_pid": new_pid,
        "preserved": {
            "users_count": len(list_users()),
            "sources_count": len(list_sources()),
            "models_count": len(list_model_providers()),
            "channels_count": len(list_notification_channels(include_disabled=True)),
        },
        "uncleared": uncleared
    })


@app.route("/api/user/reports/<path:report_id>/export")
@require_user
def export_report(report_id):
    from backend.storage.persistence import load_digests as load_runtime_digests
    from backend.storage.legacy_data import load_digests as load_legacy_digests

    all_reports = load_runtime_digests(90) + load_legacy_digests(90)
    match = None
    for r in all_reports:
        rid = str(r.get("id") or r.get("generated_at") or r.get("report_date") or r.get("_legacy_path") or "")
        if rid == report_id or report_id in rid:
            match = r
            break
    if not match:
        return jsonify({"error": "report_not_found"}), 404
        
    fmt = request.args.get("format", "markdown").lower()
    if fmt == "json":
        res = make_response(json.dumps(match, indent=2))
        res.headers["Content-Type"] = "application/json"
        res.headers["Content-Disposition"] = f"attachment; filename=jarvis_report_{report_id[:20]}.json"
        return res
        
    md = [f"# JARVIS Intelligence Report — {match.get('report_date') or match.get('generated_at') or 'Digest'}"]
    if match.get("headline"):
        md.append(f"\n## 🎯 {match['headline']}\n")
    if match.get("strategic_note"):
        md.append(f"> **Strategic Note:** {match['strategic_note']}\n")
    for section_key, title in [
        ("cybersec_updates", "🛡️ Cybersecurity Updates"),
        ("ai_updates", "🧠 AI Updates"),
        ("tech_business_updates", "💼 Tech & Business"),
        ("hardware_mobile_updates", "📱 Hardware & Mobile"),
        ("escalating_threats", "🔺 Escalating Threats"),
        ("new_patterns", "🔍 Observed Patterns"),
        ("actor_activity", "🎭 Threat Actor Activity"),
        ("recommendations", "✅ Recommended Actions"),
    ]:
        items = match.get(section_key, [])
        if items:
            md.append(f"### {title}")
            for item in items:
                md.append(f"- {item}")
            md.append("")
    if match.get("key_cves") or match.get("critical_cves"):
        cves = match.get("key_cves") or match.get("critical_cves")
        md.append("### 🔴 Critical Vulnerabilities (CVEs)")
        for c in cves:
            md.append(f"- {c}")
        md.append("")
        
    res = make_response("\n".join(md))
    res.headers["Content-Type"] = "text/markdown; charset=utf-8"
    res.headers["Content-Disposition"] = f"attachment; filename=jarvis_report_{report_id[:20]}.md"
    return res


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
    from backend.storage.persistence import load_digests as load_runtime_digests
    from backend.storage.legacy_data import load_digests as load_legacy_digests

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


@app.route("/api/user/notification-channels/test", methods=["POST"])
@require_user
@require_csrf
def user_channel_test():
    """Test a user notification channel (Telegram/Slack) and return a visible result."""
    from notifier import test_channel
    data = _json_body()
    return jsonify(test_channel(str(data.get("kind", "")), str(data.get("target", "")), data.get("secret") or {}))


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


from backend.utils.telegram_client import telegram_post
from backend.config.config import TELEGRAM_MODE


@app.route("/api/admin/network/raw-evidence", methods=["GET"])
@require_admin
def admin_network_raw_evidence():
    """Endpoint executing exact raw socket, curl, and network route evidence collection."""
    from tools.raw_hf_diagnostics import execute_raw_diagnostics
    return jsonify(execute_raw_diagnostics())


@app.route("/api/admin/network/curl", methods=["POST"])
@require_admin
def admin_network_curl():
    """Diagnostic endpoint to run curl from within the container."""
    try:
        data = request.json or {}
        command = data.get("command")  # "getMe" or "sendMessage"
        
        if not TELEGRAM_TOKEN:
            return jsonify({"error": "Telegram token not configured"}), 400
            
        import subprocess
        
        if command == "getMe":
            cmd = ["curl", "-v", f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"]
        elif command == "sendMessage":
            chat_id = data.get("chat_id", os.getenv("TELEGRAM_CHAT_ID", ""))
            text = data.get("text", "HF diagnostic via curl")
            cmd = [
                "curl", "-v", "-X", "POST",
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                "-d", f"chat_id={chat_id}",
                "-d", f"text={text}"
            ]
        else:
            return jsonify({"error": f"Unknown curl command: {command}"}), 400
            
        print(f"[CURL] Running: {' '.join(cmd).replace(TELEGRAM_TOKEN, 'bot***')}")
        
        t0 = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        elapsed = time.time() - t0
        
        output = result.stdout + "\n" + result.stderr
        output = output.replace(TELEGRAM_TOKEN, "bot***")
        
        return jsonify({
            "elapsed_s": round(elapsed, 2),
            "returncode": result.returncode,
            "output": output
        })
    except subprocess.TimeoutExpired as exc:
        return jsonify({"error": "curl command timed out after 45s", "output": str(exc.output).replace(TELEGRAM_TOKEN, "bot***") if exc.output else ""}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/admin/telegram/timeouts", methods=["GET"])
@require_admin
def admin_telegram_timeouts():
    """Diagnostic endpoint to verify active Telegram timeout configurations."""
    import inspect
    from backend.utils.telegram_client import telegram_post, telegram_get
    
    post_sig = inspect.signature(telegram_post)
    get_sig = inspect.signature(telegram_get)
    
    return jsonify({
        "telegram_post_defaults": {
            "connect_timeout": post_sig.parameters["connect_timeout"].default,
            "read_timeout": post_sig.parameters["read_timeout"].default,
            "max_retries": post_sig.parameters["max_retries"].default,
            "retry_on_read_timeout": post_sig.parameters.get("retry_on_read_timeout").default if "retry_on_read_timeout" in post_sig.parameters else None
        },
        "telegram_get_defaults": {
            "connect_timeout": get_sig.parameters["connect_timeout"].default,
            "read_timeout": get_sig.parameters["read_timeout"].default,
            "max_retries": get_sig.parameters["max_retries"].default
        },
        "active_policies": {
            "sendMessage": "connect=10.0s, read=30.0s, max_retries=1/3 (ReadTimeout prevents retry)",
            "getUpdates": "connect=10.0s, read=35.0s, max_retries=1 (Must exceed 15s poll)",
            "setup": "connect=10.0s, read=20.0s, max_retries=2"
        }
    })


@app.route("/api/admin/telegram/setup", methods=["POST"])
@require_admin
@require_csrf
def admin_telegram_setup():
    """Manual endpoint to setup Telegram webhook or commands."""
    try:
        data = request.json or {}
        action = data.get("action")  # 'set_webhook', 'delete_webhook', 'set_commands'
        
        if not TELEGRAM_TOKEN:
            return jsonify({"error": "Telegram token not configured"}), 400
            
        if action == "set_webhook":
            if not HF_SPACE_URL:
                return jsonify({"error": "HF_SPACE_URL not configured"}), 400
            res = telegram_post("setWebhook", TELEGRAM_TOKEN, payload={"url": f"{HF_SPACE_URL}/telegram/{TELEGRAM_TOKEN}", "drop_pending_updates": False}, connect_timeout=10.0, read_timeout=20.0, max_retries=2)
            return jsonify({"status": "ok", "result": res})
            
        elif action == "delete_webhook":
            res = telegram_post("deleteWebhook", TELEGRAM_TOKEN, payload={"drop_pending_updates": False}, connect_timeout=10.0, read_timeout=20.0, max_retries=2)
            return jsonify({"status": "ok", "result": res})
            
        elif action == "set_commands":
            res = telegram_post("setMyCommands", TELEGRAM_TOKEN, payload={
                "commands": [
                    {"command": "start", "description": "Subscribe to JARVIS alerts"},
                    {"command": "stop", "description": "Unsubscribe from alerts"},
                    {"command": "status", "description": "System health & statistics"},
                    {"command": "quiz", "description": "Daily intelligence quiz"},
                    {"command": "deepdive", "description": "Threat research dossier on any topic"},
                ]
            }, connect_timeout=10.0, read_timeout=20.0, max_retries=2)
            return jsonify({"status": "ok", "result": res})
            
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400
            
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def main():
    global _scheduler_proc
    print("[CLOUD] Starting JARVIS backend...")
    if is_configured():
        pull_state()

    from backend.config.config import NOTIFICATION_PROVIDER, IS_TELEGRAM_ENABLED
    prov_display = NOTIFICATION_PROVIDER.capitalize()
    print(f"[CLOUD] Notification Provider: {prov_display}")
    if not IS_TELEGRAM_ENABLED:
        print("[TELEGRAM] Disabled by configuration")
    else:
        print(f"[CLOUD] Telegram mode: {TELEGRAM_MODE}")

    _scheduler_proc = subprocess.Popen([sys.executable, "scheduler.py"], env=os.environ.copy())
    print(f"[CLOUD] Scheduler started (pid={_scheduler_proc.pid})")

    if IS_TELEGRAM_ENABLED and TELEGRAM_TOKEN:
        if TELEGRAM_MODE == "polling":
            from backend.notifications.bot_listener import start_listener
            start_listener()
        elif TELEGRAM_MODE == "webhook":
            print(f"[CLOUD] Waiting for webhook POSTs at /telegram/{TELEGRAM_TOKEN[:5]}...")

    port = int(os.getenv("PORT", 7860))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
