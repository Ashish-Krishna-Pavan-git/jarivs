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
os.environ["JARVIS_DB_PATH"] = "/tmp/jarvis-test-data/jarvis.db"
shutil.rmtree(os.environ["JARVIS_DATA_DIR"], ignore_errors=True)

from backend.app import app  # noqa: E402
from jarvis_db import DB_PATH  # noqa: E402
from mcp_client import test_mcp_server as run_mcp_test  # noqa: E402
from mcp_client import call_mcp  # noqa: E402
from storage import save_digest  # noqa: E402
from security_utils import hash_password  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def login(client, password="admin123!ChangeMe"):
    res = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert res.status_code == 200, res.get_data(as_text=True)
    data = res.get_json()
    return data, {"Authorization": f"Bearer {data['token']}", "X-CSRF-Token": data["csrf"]}


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
    assert any(item.get("headline") == "Current runtime digest" for item in reports.get_json()["reports"])


def test_sources_models_channels_and_encryption():
    client = app.test_client()
    _, headers = login(client, "ChangedPassword123!")
    source = client.post("/api/admin/sources", headers=headers, json={"name": "Example", "url": "https://example.com/feed.xml", "category": "tech", "enabled": True})
    assert source.status_code == 200
    model = client.post("/api/admin/models", headers=headers, json={"name": "custom", "provider_type": "openai_compatible", "model": "model", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "enabled": True})
    assert model.status_code == 200
    channel = client.post("/api/admin/notification-channels", headers=headers, json={"kind": "slack", "label": "Slack", "target": "https://hooks.slack.com/services/T/B/C", "secret": {"webhook_url": "https://hooks.slack.com/services/T/B/C"}, "enabled": True})
    assert channel.status_code == 200
    with sqlite3.connect(DB_PATH) as db:
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
    with patch("mcp_client.is_safe_external_url", return_value=(True, "")):
        with patch("mcp_client.requests.post", return_value=response) as post:
            result = call_mcp({"transport": "http", "endpoint": "https://mcp.example.com/rpc", "config": {}}, "initialize", {})
    assert result == {"ready": True}
    assert post.call_args.kwargs["json"]["method"] == "initialize"


def test_legacy_summary_endpoint_available():
    client = app.test_client()
    _, headers = login(client, "ChangedPassword123!")
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

    import jarvis_db
    monkeypatch.setattr(jarvis_db, "DB_PATH", str(legacy_db))
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
