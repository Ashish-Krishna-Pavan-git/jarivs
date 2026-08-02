import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = ""
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-long-enough"
os.environ["FLASK_SECRET_KEY"] = "test-flask-secret-that-is-long-enough"
os.environ["JARVIS_ENCRYPTION_KEY"] = "test-encryption-secret"
os.environ["JARVIS_DATA_DIR"] = "/tmp/jarvis-test-data"
import pytest
from backend.app import app
from jarvis_db import DB_PATH
from mcp_client import test_mcp_server as run_mcp_test
from mcp_client import call_mcp
from storage import save_digest
from security_utils import hash_password

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def setup_clean_db(tmp_path, monkeypatch):
    db_file = tmp_path / "jarvis.db"
    data_dir = tmp_path / "data"
    daily_dir = data_dir / "daily"
    archive_dir = data_dir / "archive"
    processed_dir = data_dir / "processed"
    raw_dir = data_dir / "raw_articles"

    import backend.database.jarvis_db as jarvis_db
    import backend.app as backend_app
    import jarvis_db as root_jarvis_db
    import backend.config.config as backend_config
    import backend.storage.persistence as backend_persistence

    monkeypatch.setattr(jarvis_db, "DB_PATH", str(db_file))
    monkeypatch.setattr(backend_app, "DB_PATH", str(db_file))
    monkeypatch.setattr(root_jarvis_db, "DB_PATH", str(db_file))
    monkeypatch.setattr(backend_config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(backend_config, "DAILY_DIR", str(daily_dir))
    monkeypatch.setattr(backend_config, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(backend_config, "PROCESSED_DIR", str(processed_dir))
    monkeypatch.setattr(backend_config, "RAW_DIR", str(raw_dir))
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_file))
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    jarvis_db.init_db()
    jarvis_db.ensure_admin_user(hash_password)


def login(client, password="admin123!ChangeMe"):
    res = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert res.status_code == 200, res.get_data(as_text=True)
    data = res.get_json()
    return data, {"Authorization": f"Bearer {data['token']}", "X-CSRF-Token": data["csrf"]}


def login_as_active_admin(client):
    data, headers = login(client)
    if data["user"].get("must_change_password"):
        changed = client.post("/api/auth/change-password", headers=headers, json={"current_password": "admin123!ChangeMe", "new_password": "ChangedPassword123!"})
        assert changed.status_code == 200
        res_data = changed.get_json()
        headers = {"Authorization": f"Bearer {res_data['token']}", "X-CSRF-Token": res_data["csrf"]}
    return headers


def test_login_forces_password_change_then_allows_admin():
    client = app.test_client()
    data, headers = login(client)
    assert data["user"]["must_change_password"]
    assert client.get("/api/admin/overview", headers=headers).status_code == 403
    missing_current = client.post("/api/auth/change-password", headers=headers, json={"new_password": "ChangedPassword123!"})
    assert missing_current.status_code == 400
    changed = client.post("/api/auth/change-password", headers=headers, json={"current_password": "admin123!ChangeMe", "new_password": "ChangedPassword123!"})
    assert changed.status_code == 200
    headers = {"Authorization": f"Bearer {changed.get_json()['token']}", "X-CSRF-Token": changed.get_json()["csrf"]}
    assert client.get("/api/admin/overview", headers=headers).status_code == 200
    save_digest({"headline": "Current runtime digest", "strategic_note": "Available from /data/daily."}, 1)
    reports = client.get("/api/user/reports", headers=headers)
    assert reports.status_code == 200
    assert any(item.get("headline") == "Current runtime digest" for item in reports.get_json()["reports"]), f"Reports failure: {reports.get_json()}"


def test_sources_models_channels_and_encryption():
    client = app.test_client()
    headers = login_as_active_admin(client)
    source = client.post("/api/admin/sources", headers=headers, json={"name": "Example", "url": "https://example.com/feed.xml", "category": "tech", "enabled": True})
    assert source.status_code == 200
    model = client.post("/api/admin/models", headers=headers, json={"name": "custom", "provider_type": "openai_compatible", "model": "model", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "enabled": True})
    assert model.status_code == 200
    channel = client.post("/api/admin/notification-channels", headers=headers, json={"kind": "slack", "label": "Slack", "target": "https://hooks.slack.com/services/T/B/C", "secret": {"webhook_url": "https://hooks.slack.com/services/T/B/C"}, "enabled": True})
    assert channel.status_code == 200
    import backend.database.jarvis_db as jarvis_db
    with sqlite3.connect(jarvis_db.DB_PATH) as db:
        secret = db.execute("SELECT secret_json FROM notification_channels WHERE label='Slack'").fetchone()[0]
    assert secret.startswith("fernet:")
    assert "hooks.slack.com" not in secret


def test_mcp_stdio_mock(tmp_path):
    script = tmp_path / "mock_mcp.py"
    script.write_text("import json,sys\nr=json.loads(sys.stdin.readline())\nprint(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':{'ok':True}}))\n", encoding="utf-8")
    result = run_mcp_test({"name": "mock", "transport": "stdio", "endpoint": sys.executable, "enabled": True, "config": {"command": sys.executable, "args": [str(script)], "timeout_seconds": 5}})
    assert result["ok"]


def test_mcp_http_mock():
    response = Mock()
    response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {"ready": True}}
    response.raise_for_status.return_value = None
    with patch("backend.services.mcp_client.is_safe_external_url", return_value=(True, "")), \
         patch("mcp_client.is_safe_external_url", return_value=(True, "")):
        with patch("backend.services.mcp_client.requests.post", return_value=response) as post:
            result = call_mcp({"transport": "http", "endpoint": "https://mcp.example.com/rpc", "config": {}}, "initialize", {})
    assert result == {"ready": True}
    assert post.call_args.kwargs["json"]["method"] == "initialize"


def test_legacy_summary_endpoint_available():
    client = app.test_client()
    headers = login_as_active_admin(client)
    res = client.get("/api/admin/migrations", headers=headers)
    assert res.status_code == 200
    assert "legacy" in res.get_json()


def test_startup_migrates_legacy_database_and_preserves_auth_data(tmp_path, monkeypatch):
    legacy_db = tmp_path / "legacy.db"
    admin_hash = hash_password("LegacyAdminPassword123!")
    user_hash = hash_password("LegacyUserPassword123!")
    with sqlite3.connect(legacy_db) as db:
        db.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE notification_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                kind TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                target TEXT NOT NULL DEFAULT '',
                secret_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE legacy_notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
        """)
        db.execute("INSERT INTO users(username,password_hash,role,must_change_password,created_at) VALUES(?,?,?,?,?)", ("legacy-admin", admin_hash, "admin", 1, "2025-01-01T00:00:00"))
        db.execute("INSERT INTO users(username,password_hash,role,must_change_password,created_at) VALUES(?,?,?,?,?)", ("legacy-user", user_hash, "user", 0, "2025-01-01T00:00:00"))
        db.execute("INSERT INTO notification_channels(user_id,kind,label,target,secret_json,enabled,created_at,updated_at) VALUES(1,'telegram','Legacy channel','12345','{}',1,'2025-01-01T00:00:00','2025-01-01T00:00:00')")
        db.execute("INSERT INTO legacy_notes(id,body) VALUES(1,'preserve this row')")

    startup_env = os.environ.copy()
    startup_env.update({
        "JARVIS_DB_PATH": str(legacy_db),
        "JARVIS_DATA_DIR": str(tmp_path / "runtime"),
        "ADMIN_USERNAME": "legacy-admin",
        "ADMIN_PASSWORD": "",
    })
    startup = subprocess.run(
        [sys.executable, "-c", "from backend.app import app; from jarvis_db import schema_status; print(schema_status()['user_version'])"],
        cwd=ROOT,
        env=startup_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert startup.stdout.rstrip().endswith("4")

    with sqlite3.connect(legacy_db) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        assert {"active", "display_name", "must_change_password", "role"}.issubset(columns)
        assert db.execute("SELECT password_hash FROM users WHERE username='legacy-admin'").fetchone()[0] == admin_hash
        assert db.execute("SELECT role,active,must_change_password FROM users WHERE username='legacy-admin'").fetchone() == ("admin", 1, 1)
        assert db.execute("SELECT role,active FROM users WHERE username='legacy-user'").fetchone() == ("user", 1)
        assert db.execute("SELECT body FROM legacy_notes WHERE id=1").fetchone()[0] == "preserve this row"
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 4
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert any(row[2] == "users" and row[3] == "user_id" for row in db.execute("PRAGMA foreign_key_list(notification_channels)"))
        assert any(row[1] == "idx_users_active_username" for row in db.execute("PRAGMA index_list(users)"))

    import backend.database.jarvis_db as jarvis_db
    import backend.app as backend_app
    import jarvis_db as root_jarvis_db
    monkeypatch.setattr(jarvis_db, "DB_PATH", str(legacy_db))
    monkeypatch.setattr(backend_app, "DB_PATH", str(legacy_db))
    monkeypatch.setattr(root_jarvis_db, "DB_PATH", str(legacy_db))
    client = app.test_client()
    admin_login = client.post("/api/auth/login", json={"username": "legacy-admin", "password": "LegacyAdminPassword123!"})
    assert admin_login.status_code == 200
    admin_data = admin_login.get_json()
    assert admin_data["user"]["must_change_password"]
    admin_headers = {"Authorization": f"Bearer {admin_data['token']}", "X-CSRF-Token": admin_data["csrf"]}
    assert client.get("/api/admin/overview", headers=admin_headers).status_code == 403
    changed = client.post("/api/auth/change-password", headers=admin_headers, json={"current_password": "LegacyAdminPassword123!", "new_password": "MigratedPassword123!"})
    assert changed.status_code == 200
    changed_data = changed.get_json()
    changed_headers = {"Authorization": f"Bearer {changed_data['token']}", "X-CSRF-Token": changed_data["csrf"]}
    assert client.get("/api/admin/overview", headers=changed_headers).status_code == 200

    user_login = client.post("/api/auth/login", json={"username": "legacy-user", "password": "LegacyUserPassword123!"})
    assert user_login.status_code == 200
    user_data = user_login.get_json()
    user_headers = {"Authorization": f"Bearer {user_data['token']}", "X-CSRF-Token": user_data["csrf"]}
    assert client.get("/api/admin/overview", headers=user_headers).status_code == 403


def test_testing_center_endpoints():
    client = app.test_client()
    headers = login_as_active_admin(client)
    
    live_state = client.get("/api/admin/testing/live-state", headers=headers)
    assert live_state.status_code == 200
    data = live_state.get_json()
    assert "runtime" in data and "counts" in data
    
    toggle = client.post("/api/admin/testing/pipeline-toggle", headers=headers)
    assert toggle.status_code == 200
    assert "paused" in toggle.get_json()
    
    # Toggle back to unpaused
    client.post("/api/admin/testing/pipeline-toggle", headers=headers)
    
    test_prov = client.post("/api/admin/testing/test-providers", headers=headers)
    assert test_prov.status_code == 200
    assert "providers" in test_prov.get_json()
    
    test_src = client.post("/api/admin/testing/test-collectors", headers=headers)
    assert test_src.status_code == 200
    assert "sources" in test_src.get_json()
    
    test_ai = client.post("/api/admin/testing/run-ai-analysis", headers=headers, json={"title": "Test CVE", "content": "Critical RCE zero-day flaw observed."})
    assert test_ai.status_code == 200
    assert "analysis" in test_ai.get_json()
    
    reset = client.post("/api/admin/testing/reset-scheduler", headers=headers)
    assert reset.status_code == 200


def test_clear_all_test_data_maintenance_action():
    client = app.test_client()
    headers = login_as_active_admin(client)
    
    # Run a test collection and report generation to populate artifacts
    client.post("/api/admin/testing/run-ai-analysis", headers=headers, json={"title": "Test Article", "content": "Sample test content."})
    save_digest({"headline": "Test Digest", "strategic_note": "Test digest note."}, 1)
    
    # Execute Clear All Test Data maintenance action
    res = client.post("/api/admin/testing/clear", headers=headers, json={"target": "clear_all_test_data"})
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"]
    assert payload["verified_clean"], f"Payload verification failed: {payload}"
    assert payload["verification"]["daily_reports_count"] == 0
    assert payload["verification"]["archive_reports_count"] == 0
    assert payload["verification"]["processed_articles_count"] == 0
    assert payload["verification"]["queue_total"] == 0
    assert payload["verification"]["dedupe_fingerprints_count"] == 0
    # Exactly 1 log should exist (the cleanup log itself)
    assert payload["verification"]["event_logs_count"] == 1
    
    # Verify app and auth still work normally post-cleanup
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.get_json()["user"]["username"] == "admin"



