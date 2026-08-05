"""SQLite control plane for JARVIS."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Load local configuration before resolving database and security settings.
# Docker-provided environment variables keep precedence over values in .env.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

from security_utils import decrypt_json, encrypt_json

DB_PATH = os.getenv("JARVIS_DB_PATH", os.path.join(os.getenv("JARVIS_DATA_DIR", "/tmp/jarvis/data"), "jarvis.db"))
_lock = threading.Lock()

DEFAULT_SOURCES = [
    ("TheHackerNews", "https://feeds.feedburner.com/TheHackersNews", "cybersec"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/", "cybersec"),
    ("KrebsOnSecurity", "https://krebsonsecurity.com/feed/", "cybersec"),
    ("SecurityWeek", "https://feeds.feedburner.com/securityweek", "cybersec"),
    ("DarkReading", "https://www.darkreading.com/rss.xml", "cybersec"),
    ("CISAAdvisories", "https://www.cisa.gov/cybersecurity-advisories/advisories.xml", "cybersec"),
    ("MITTechReview", "https://www.technologyreview.com/feed/", "ai"),
    ("VentureBeat_AI", "https://venturebeat.com/category/ai/feed/", "ai"),
    ("TheVerge", "https://www.theverge.com/rss/index.xml", "tech"),
    ("TechCrunch", "https://techcrunch.com/feed/", "tech"),
    ("HackerNews_Top", "https://hnrss.org/frontpage", "tech"),
    ("GSMArena", "https://www.gsmarena.com/rss-news-reviews.php3", "mobile"),
    ("AndroidAuthority", "https://www.androidauthority.com/feed/", "mobile"),
    ("TomsHardware", "https://www.tomshardware.com/feeds/all", "hardware"),
    ("TLDRNewsletter", "https://tldr.tech/rss", "newsletter"),
]

DEFAULT_MODEL_PROVIDERS = [
    ("gemini-flash", "gemini", "gemini-2.5-flash", "", "GEMINI_API_KEY", 1, 4.5),
    ("gemini-pro", "gemini", "gemini-2.5-pro", "", "GEMINI_API_KEY", 1, 13.0),
    ("groq-fast", "groq", "llama-3.1-8b-instant", "", "GROQ_API_KEY", 1, 2.5),
    ("groq-70b", "groq", "llama-3.3-70b-versatile", "", "GROQ_API_KEY", 1, 2.5),
    ("ollama-local", "ollama", os.getenv("OLLAMA_MODEL", "phi4-mini"), os.getenv("OLLAMA_URL", "http://localhost:11434"), "", 0, 0.0),
]

DEFAULT_MODEL_ROUTES = {
    "article": ["groq-fast", "gemini-flash", "ollama-local"],
    "digest": ["gemini-flash", "groq-70b", "ollama-local"],
    "premium": ["gemini-pro", "gemini-flash", "groq-70b"],
    "text": ["gemini-flash", "groq-70b", "ollama-local"],
}

SCHEMA_VERSION = 4


class SchemaMigrationError(RuntimeError):
    """Raised when a database cannot be upgraded without risking stored data."""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _rows(cur) -> list[dict[str, Any]]:
    return [dict(row) for row in cur.fetchall()]


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in db.execute(f'PRAGMA table_info("{table}")')}


def _ensure_column(db: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in _columns(db, table):
        db.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')


def _ensure_schema_journal(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )""")


def _bootstrap_tables(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'admin',
          display_name TEXT NOT NULL DEFAULT '',
          must_change_password INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE,
          category TEXT NOT NULL DEFAULT 'tech',
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_providers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          provider_type TEXT NOT NULL,
          model TEXT NOT NULL,
          base_url TEXT NOT NULL DEFAULT '',
          api_key_env TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          min_interval REAL NOT NULL DEFAULT 0,
          blocked_until TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_routes (
          task TEXT NOT NULL,
          provider_name TEXT NOT NULL,
          priority INTEGER NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (task, provider_name)
        );
        CREATE TABLE IF NOT EXISTS integrations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          kind TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0,
          config_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mcp_servers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          transport TEXT NOT NULL DEFAULT 'http',
          endpoint TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          config_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS event_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          level TEXT NOT NULL,
          component TEXT NOT NULL,
          message TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_channels (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER,
          kind TEXT NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          target TEXT NOT NULL DEFAULT '',
          secret_json TEXT NOT NULL DEFAULT '{}',
          enabled INTEGER NOT NULL DEFAULT 1,
          verified_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS app_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS migration_records (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_path TEXT NOT NULL,
          kind TEXT NOT NULL,
          item_key TEXT NOT NULL,
          status TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          UNIQUE(source_path, kind, item_key)
        );
    """)


def _migration_1_bootstrap(db: sqlite3.Connection) -> None:
    """Create the complete control-plane schema for a fresh installation."""
    _bootstrap_tables(db)


def _migration_2_users_upgrade(db: sqlite3.Connection) -> None:
    """Upgrade pre-auth user tables without replacing account rows or passwords."""
    _bootstrap_tables(db)
    if not _table_exists(db, "users"):
        return
    _ensure_column(db, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
    _ensure_column(db, "users", "display_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "users", "active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(db, "users", "created_at", "TEXT NOT NULL DEFAULT ''")

    now = datetime.now(timezone.utc).isoformat()
    admin_username = os.getenv("ADMIN_USERNAME", "admin") or "admin"
    db.execute("UPDATE users SET role='user' WHERE role IS NULL OR role NOT IN ('admin','user')")
    db.execute("UPDATE users SET role='admin' WHERE username=?", (admin_username,))
    db.execute("UPDATE users SET display_name=username WHERE display_name IS NULL OR trim(display_name)='' ")
    db.execute("UPDATE users SET active=1 WHERE active IS NULL")
    db.execute("UPDATE users SET must_change_password=0 WHERE must_change_password IS NULL")
    db.execute("UPDATE users SET created_at=? WHERE created_at IS NULL OR trim(created_at)=''", (now,))


def _migration_3_additive_control_plane_upgrade(db: sqlite3.Connection) -> None:
    """Add every later control-plane field to databases created by intermediate builds."""
    _bootstrap_tables(db)
    additions = {
        "sources": {
            "name": "TEXT NOT NULL DEFAULT ''",
            "url": "TEXT NOT NULL DEFAULT ''",
            "category": "TEXT NOT NULL DEFAULT 'tech'",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "model_providers": {
            "name": "TEXT NOT NULL DEFAULT ''",
            "provider_type": "TEXT NOT NULL DEFAULT 'openai_compatible'",
            "model": "TEXT NOT NULL DEFAULT ''",
            "base_url": "TEXT NOT NULL DEFAULT ''",
            "api_key_env": "TEXT NOT NULL DEFAULT ''",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
            "min_interval": "REAL NOT NULL DEFAULT 0",
            "blocked_until": "TEXT",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "model_routes": {
            "task": "TEXT NOT NULL DEFAULT ''",
            "provider_name": "TEXT NOT NULL DEFAULT ''",
            "priority": "INTEGER NOT NULL DEFAULT 1",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
        },
        "integrations": {
            "name": "TEXT NOT NULL DEFAULT ''",
            "kind": "TEXT NOT NULL DEFAULT ''",
            "enabled": "INTEGER NOT NULL DEFAULT 0",
            "config_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "mcp_servers": {
            "name": "TEXT NOT NULL DEFAULT ''",
            "transport": "TEXT NOT NULL DEFAULT 'http'",
            "endpoint": "TEXT NOT NULL DEFAULT ''",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
            "config_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "event_logs": {
            "level": "TEXT NOT NULL DEFAULT 'INFO'",
            "component": "TEXT NOT NULL DEFAULT 'system'",
            "message": "TEXT NOT NULL DEFAULT ''",
            "details_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
        },
        "notification_channels": {
            "user_id": "INTEGER",
            "kind": "TEXT NOT NULL DEFAULT 'telegram'",
            "label": "TEXT NOT NULL DEFAULT ''",
            "target": "TEXT NOT NULL DEFAULT ''",
            "secret_json": "TEXT NOT NULL DEFAULT '{}'",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
            "verified_at": "TEXT",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "app_settings": {
            "value": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "migration_records": {
            "source_path": "TEXT NOT NULL DEFAULT ''",
            "kind": "TEXT NOT NULL DEFAULT ''",
            "item_key": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "details_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
        },
    }
    for table, columns in additions.items():
        for name, definition in columns.items():
            _ensure_column(db, table, name, definition)

    now = datetime.now(timezone.utc).isoformat()
    for table in ["sources", "model_providers", "integrations", "mcp_servers", "notification_channels"]:
        db.execute(f"UPDATE {table} SET created_at=? WHERE created_at IS NULL OR trim(created_at)=''", (now,))
        db.execute(f"UPDATE {table} SET updated_at=created_at WHERE updated_at IS NULL OR trim(updated_at)='' ")
    for table in ["event_logs", "migration_records", "app_settings"]:
        db.execute(f"UPDATE {table} SET created_at=? WHERE created_at IS NULL OR trim(created_at)=''", (now,)) if table != "app_settings" else db.execute("UPDATE app_settings SET updated_at=? WHERE updated_at IS NULL OR trim(updated_at)=''", (now,))


def _assert_unique_values(db: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> None:
    column_sql = ", ".join(f'"{column}"' for column in columns)
    duplicate = db.execute(f"SELECT {column_sql}, COUNT(*) FROM {table} GROUP BY {column_sql} HAVING COUNT(*) > 1 LIMIT 1").fetchone()
    if duplicate:
        values = ", ".join(str(value) for value in duplicate[:-1])
        raise SchemaMigrationError(f"Cannot add unique index to {table} ({', '.join(columns)}): duplicate value {values!r}. Resolve duplicates before retrying; no data was changed.")


def _ensure_unique_index(db: sqlite3.Connection, name: str, table: str, columns: tuple[str, ...]) -> None:
    _assert_unique_values(db, table, columns)
    column_sql = ", ".join(f'"{column}"' for column in columns)
    db.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table}" ({column_sql})')


def _has_notification_user_foreign_key(db: sqlite3.Connection) -> bool:
    return any(
        row[2] == "users" and row[3] == "user_id" and row[6].upper() == "SET NULL"
        for row in db.execute('PRAGMA foreign_key_list("notification_channels")')
    )


def _rebuild_notification_channels_with_foreign_key(db: sqlite3.Connection) -> None:
    """Repair a pre-foreign-key channel table while preserving every valid row."""
    if _has_notification_user_foreign_key(db):
        return
    orphan = db.execute("""SELECT channel.id, channel.user_id FROM notification_channels channel
        LEFT JOIN users user ON user.id=channel.user_id
        WHERE channel.user_id IS NOT NULL AND user.id IS NULL LIMIT 1""").fetchone()
    if orphan:
        raise SchemaMigrationError(
            f"Cannot add notification_channels foreign key: channel {orphan[0]} references missing user {orphan[1]}. "
            "No data was changed; repair the orphaned user reference and retry."
        )
    db.execute('ALTER TABLE notification_channels RENAME TO notification_channels_pre_fk')
    _bootstrap_tables(db)
    db.execute("""INSERT INTO notification_channels(id,user_id,kind,label,target,secret_json,enabled,verified_at,created_at,updated_at)
        SELECT id,user_id,kind,label,target,secret_json,enabled,verified_at,created_at,updated_at
        FROM notification_channels_pre_fk""")
    db.execute("DROP TABLE notification_channels_pre_fk")


def _migration_4_indexes_and_constraints(db: sqlite3.Connection) -> None:
    """Add the indexes/uniqueness guarantees required by runtime queries."""
    _bootstrap_tables(db)
    _rebuild_notification_channels_with_foreign_key(db)
    for name, table, columns in [
        ("ux_users_username", "users", ("username",)),
        ("ux_sources_url", "sources", ("url",)),
        ("ux_model_providers_name", "model_providers", ("name",)),
        ("ux_integrations_name", "integrations", ("name",)),
        ("ux_mcp_servers_name", "mcp_servers", ("name",)),
        ("ux_model_routes_task_provider", "model_routes", ("task", "provider_name")),
        ("ux_migration_records_source_kind_key", "migration_records", ("source_path", "kind", "item_key")),
    ]:
        _ensure_unique_index(db, name, table, columns)

    db.executescript("""
        CREATE INDEX IF NOT EXISTS idx_users_active_username ON users(active, username);
        CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled, name);
        CREATE INDEX IF NOT EXISTS idx_model_providers_enabled ON model_providers(enabled, name);
        CREATE INDEX IF NOT EXISTS idx_model_routes_task_priority ON model_routes(task, enabled, priority);
        CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_event_logs_level_created_at ON event_logs(level, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notification_channels_user_enabled ON notification_channels(user_id, enabled);
        CREATE INDEX IF NOT EXISTS idx_notification_channels_kind_enabled ON notification_channels(kind, enabled);
    """)


MIGRATIONS = (
    (1, "bootstrap_control_plane", _migration_1_bootstrap),
    (2, "upgrade_users_for_authentication", _migration_2_users_upgrade),
    (3, "upgrade_control_plane_columns", _migration_3_additive_control_plane_upgrade),
    (4, "add_runtime_indexes_and_constraints", _migration_4_indexes_and_constraints),
)


def _seed_defaults(db: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    # Seed default sources ONLY if sources table is empty (prevents resurrecting deleted sources)
    if db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0:
        for name, url, category in DEFAULT_SOURCES:
            db.execute("INSERT INTO sources(name,url,category,enabled,created_at,updated_at) VALUES(?,?,?,1,?,?)", (name, url, category, now, now))
    # Seed default model providers ONLY if model_providers table is empty
    if db.execute("SELECT COUNT(*) FROM model_providers").fetchone()[0] == 0:
        for row in DEFAULT_MODEL_PROVIDERS:
            db.execute("INSERT INTO model_providers(name,provider_type,model,base_url,api_key_env,enabled,min_interval,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (*row, now, now))
    if db.execute("SELECT COUNT(*) FROM model_routes").fetchone()[0] == 0:
        for task, providers in DEFAULT_MODEL_ROUTES.items():
            for priority, provider in enumerate(providers, 1):
                db.execute("INSERT INTO model_routes(task,provider_name,priority,enabled) VALUES(?,?,?,1)", (task, provider, priority))
    if db.execute("SELECT COUNT(*) FROM integrations").fetchone()[0] == 0:
        for name, kind in [("telegram", "telegram"), ("slack", "slack")]:
            db.execute("INSERT INTO integrations(name,kind,enabled,config_json,created_at,updated_at) VALUES(?,?,0,?,?,?)", (name, kind, encrypt_json({}), now, now))


def init_db() -> None:
    """Run all pending, transactional schema migrations and seed defaults."""
    with _lock, _connect() as db:
        _ensure_schema_journal(db)
        applied = {int(row[0]) for row in db.execute("SELECT version FROM schema_migrations")}
        for version, name, migration in MIGRATIONS:
            if version in applied:
                continue
            try:
                migration(db)
                db.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)", (version, name, datetime.now(timezone.utc).isoformat()))
                db.execute(f"PRAGMA user_version={version}")
            except Exception as exc:
                raise SchemaMigrationError(f"Schema migration v{version} ({name}) failed: {exc}") from exc
        _seed_defaults(db)


def schema_status() -> dict[str, Any]:
    """Return a complete, read-only schema inventory for admin diagnostics."""
    with _connect() as db:
        tables = {}
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            tables[table] = {
                "columns": [dict(row) for row in db.execute(f'PRAGMA table_info("{table}")')],
                "indexes": [dict(row) for row in db.execute(f'PRAGMA index_list("{table}")')],
                "foreign_keys": [dict(row) for row in db.execute(f'PRAGMA foreign_key_list("{table}")')],
            }
        return {
            "expected_version": SCHEMA_VERSION,
            "user_version": int(db.execute("PRAGMA user_version").fetchone()[0]),
            "applied_migrations": _rows(db.execute("SELECT version,name,applied_at FROM schema_migrations ORDER BY version")),
            "tables": tables,
        }


def ensure_admin_user(make_hash) -> None:
    username = os.getenv("ADMIN_USERNAME", "admin") or "admin"
    env_password = os.getenv("ADMIN_PASSWORD", "")
    password = env_password or "admin123!ChangeMe"
    must_change = 0 if env_password else 1
    with _connect() as db:
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return
    with _lock, _connect() as db:
        db.execute("INSERT INTO users(username,password_hash,role,display_name,must_change_password,active,created_at) VALUES(?,?,'admin','Administrator',?,1,?)", (username, make_hash(password), must_change, datetime.now(timezone.utc).isoformat()))
    if must_change:
        print(f"[SECURITY] Default admin credentials: {username} / {password} - change after first login.")


def log_event(level: str, component: str, message: str, details: dict[str, Any] | None = None) -> None:
    try:
        with _lock, _connect() as db:
            db.execute("INSERT INTO event_logs(level,component,message,details_json,created_at) VALUES(?,?,?,?,?)", (level.upper(), component, message, json.dumps(details or {}), datetime.now(timezone.utc).isoformat()))
    except Exception:
        pass


def list_logs(limit: int = 500) -> list[dict[str, Any]]:
    with _connect() as db:
        return _rows(db.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT ?", (min(int(limit), 1000),)))


def clear_logs() -> None:
    with _lock, _connect() as db:
        db.execute("DELETE FROM event_logs")


def get_notification_diagnostics() -> dict[str, Any]:
    with _connect() as db:
        logs = _rows(db.execute(
            "SELECT * FROM event_logs WHERE component IN ('notifier', 'telegram', 'slack', 'telegram_client') ORDER BY id DESC LIMIT 100"
        ))

    tg_logs = [l for l in logs if l.get("component") in ("telegram", "telegram_client") or "Telegram" in str(l.get("message", ""))]
    slack_logs = [l for l in logs if l.get("component") == "slack" or "Slack" in str(l.get("message", ""))]

    tg_last_ok = next((l for l in tg_logs if l.get("level") == "INFO"), None)
    tg_last_err = next((l for l in tg_logs if l.get("level") in ("WARN", "ERROR")), None)

    slack_last_ok = next((l for l in slack_logs if l.get("level") == "INFO"), None)
    slack_last_err = next((l for l in slack_logs if l.get("level") in ("WARN", "ERROR")), None)

    crit_alerts = len([l for l in logs if "immediate" in str(l.get("message", "")).lower() or "critical" in str(l.get("message", "")).lower()])
    cycle_digests = len([l for l in logs if "digest" in str(l.get("message", "")).lower()])
    daily_summaries = len([l for l in logs if "daily" in str(l.get("message", "")).lower()])

    return {
        "telegram": {
            "last_success": tg_last_ok.get("created_at") if tg_last_ok else None,
            "last_error": tg_last_err.get("created_at") if tg_last_err else None,
            "last_error_message": tg_last_err.get("message") if tg_last_err else None,
        },
        "slack": {
            "last_success": slack_last_ok.get("created_at") if slack_last_ok else None,
            "last_error": slack_last_err.get("created_at") if slack_last_err else None,
            "last_error_message": slack_last_err.get("message") if slack_last_err else None,
        },
        "metrics": {
            "critical_alerts": crit_alerts,
            "cycle_digests": cycle_digests,
            "daily_summaries": daily_summaries,
        },
        "recent_logs": logs[:10],
    }


def list_enabled_sources() -> list[tuple[str, str]]:
    with _connect() as db:
        rows = db.execute("SELECT name,url FROM sources WHERE enabled=1 ORDER BY name").fetchall()
    return [(row["name"], row["url"]) for row in rows]


def list_sources() -> list[dict[str, Any]]:
    with _connect() as db:
        return _rows(db.execute("SELECT * FROM sources ORDER BY name"))


def upsert_source(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    params = (str(data["name"]).strip(), str(data["url"]).strip(), str(data.get("category", "tech")).strip() or "tech", 1 if data.get("enabled", True) else 0, now)
    with _lock, _connect() as db:
        if data.get("id"):
            db.execute("UPDATE sources SET name=?,url=?,category=?,enabled=?,updated_at=? WHERE id=?", (*params, int(data["id"])))
            sid = int(data["id"])
        else:
            db.execute("INSERT INTO sources(name,url,category,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?)", (params[0], params[1], params[2], params[3], now, now))
            sid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return dict(db.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone())


def delete_source(source_id: int) -> None:
    with _lock, _connect() as db:
        db.execute("DELETE FROM sources WHERE id=?", (int(source_id),))


def list_model_providers() -> list[dict[str, Any]]:
    with _connect() as db:
        return _rows(db.execute("SELECT * FROM model_providers ORDER BY name"))


def upsert_model_provider(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    params = (str(data["name"]).strip(), str(data.get("provider_type", "openai_compatible")).strip(), str(data["model"]).strip(), str(data.get("base_url", "")).strip(), str(data.get("api_key_env", "")).strip(), 1 if data.get("enabled", True) else 0, float(data.get("min_interval", 0) or 0), now)
    with _lock, _connect() as db:
        if data.get("id"):
            db.execute("UPDATE model_providers SET name=?,provider_type=?,model=?,base_url=?,api_key_env=?,enabled=?,min_interval=?,updated_at=? WHERE id=?", (*params, int(data["id"])))
            pid = int(data["id"])
        else:
            db.execute("INSERT INTO model_providers(name,provider_type,model,base_url,api_key_env,enabled,min_interval,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (*params[:-1], now, now))
            pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return dict(db.execute("SELECT * FROM model_providers WHERE id=?", (pid,)).fetchone())


def get_model_route(task: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        return _rows(db.execute("""SELECT p.* FROM model_routes r JOIN model_providers p ON p.name=r.provider_name
            WHERE r.task=? AND r.enabled=1 AND p.enabled=1 AND (p.blocked_until IS NULL OR p.blocked_until < ?)
            ORDER BY r.priority""", (task, now)))


def block_model_provider(name: str, seconds: int, reason: str) -> None:
    until = (datetime.now(timezone.utc) + timedelta(seconds=max(int(seconds), 1))).isoformat()
    with _lock, _connect() as db:
        db.execute("UPDATE model_providers SET blocked_until=?,updated_at=? WHERE name=?", (until, datetime.now(timezone.utc).isoformat(), name))
    log_event("WARN", "ai_router", f"Blocked provider {name}", {"seconds": seconds, "reason": reason})


def list_integrations() -> list[dict[str, Any]]:
    with _connect() as db:
        rows = _rows(db.execute("SELECT * FROM integrations ORDER BY name"))
    for row in rows:
        row["config"] = decrypt_json(row.pop("config_json", "{}"))
    return rows


def upsert_integration(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connect() as db:
        db.execute("""INSERT INTO integrations(name,kind,enabled,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET kind=excluded.kind,enabled=excluded.enabled,config_json=excluded.config_json,updated_at=excluded.updated_at""",
            (str(data["name"]).strip(), str(data.get("kind", data["name"])).strip(), 1 if data.get("enabled", False) else 0, encrypt_json(data.get("config") or {}), now, now))
        row = dict(db.execute("SELECT * FROM integrations WHERE name=?", (str(data["name"]).strip(),)).fetchone())
    row["config"] = decrypt_json(row.pop("config_json", "{}"))
    return row


def list_mcp_servers() -> list[dict[str, Any]]:
    with _connect() as db:
        rows = _rows(db.execute("SELECT * FROM mcp_servers ORDER BY name"))
    for row in rows:
        row["config"] = decrypt_json(row.pop("config_json", "{}"))
    return rows


def upsert_mcp_server(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    config = encrypt_json(data.get("config") or {})
    params = (str(data["name"]).strip(), str(data.get("transport", "http")).strip(), str(data.get("endpoint", "")).strip(), 1 if data.get("enabled", True) else 0, config, now)
    with _lock, _connect() as db:
        if data.get("id"):
            db.execute("UPDATE mcp_servers SET name=?,transport=?,endpoint=?,enabled=?,config_json=?,updated_at=? WHERE id=?", (*params, int(data["id"])))
            sid = int(data["id"])
        else:
            db.execute("INSERT INTO mcp_servers(name,transport,endpoint,enabled,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (params[0], params[1], params[2], params[3], params[4], now, now))
            sid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = dict(db.execute("SELECT * FROM mcp_servers WHERE id=?", (sid,)).fetchone())
    row["config"] = decrypt_json(row.pop("config_json", "{}"))
    return row


def get_user(username: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with _connect() as db:
        return _rows(db.execute("SELECT id,username,role,display_name,must_change_password,active,created_at FROM users ORDER BY username"))


def create_user(data: dict[str, Any], make_hash) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    role = str(data.get("role", "user"))
    if role not in {"admin", "user"}:
        role = "user"
    with _lock, _connect() as db:
        db.execute("INSERT INTO users(username,password_hash,role,display_name,must_change_password,active,created_at) VALUES(?,?,?,?,1,1,?)", (str(data["username"]).strip(), make_hash(str(data.get("password") or "ChangeMe123!")), role, str(data.get("display_name", "")).strip(), now))
        return dict(db.execute("SELECT id,username,role,display_name,must_change_password,active,created_at FROM users WHERE username=?", (str(data["username"]).strip(),)).fetchone())


def update_user(user_id: int, data: dict[str, Any], make_hash=None) -> dict[str, Any]:
    with _lock, _connect() as db:
        current = db.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
        if not current:
            raise ValueError("user_not_found")
        role = str(data.get("role", current["role"]))
        if role not in {"admin", "user"}:
            role = current["role"]
        db.execute("UPDATE users SET display_name=?,role=?,active=? WHERE id=?", (str(data.get("display_name", current["display_name"] or "")).strip(), role, 1 if data.get("active", bool(current["active"])) else 0, int(user_id)))
        if data.get("password") and make_hash:
            db.execute("UPDATE users SET password_hash=?,must_change_password=? WHERE id=?", (make_hash(str(data["password"])), 1 if data.get("must_change_password", True) else 0, int(user_id)))
        return dict(db.execute("SELECT id,username,role,display_name,must_change_password,active,created_at FROM users WHERE id=?", (int(user_id),)).fetchone())


def change_password(user_id: int, new_password_hash: str) -> None:
    with _lock, _connect() as db:
        db.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?", (new_password_hash, int(user_id)))


def list_notification_channels(user_id: int | None = None, include_disabled: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM notification_channels"
    where, params = [], []
    if user_id is not None:
        where.append("user_id=?")
        params.append(int(user_id))
    if not include_disabled:
        where.append("enabled=1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY kind,label"
    with _connect() as db:
        rows = _rows(db.execute(sql, params))
    for row in rows:
        row["secret"] = decrypt_json(row.pop("secret_json", "{}"))
    return rows


def upsert_notification_channel(data: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    params = (user_id if user_id is not None else data.get("user_id"), str(data.get("kind", "telegram")).strip(), str(data.get("label", "")).strip(), str(data.get("target", "")).strip(), encrypt_json(data.get("secret") or {}), 1 if data.get("enabled", True) else 0, now)
    with _lock, _connect() as db:
        if data.get("id"):
            db.execute("UPDATE notification_channels SET user_id=?,kind=?,label=?,target=?,secret_json=?,enabled=?,updated_at=? WHERE id=?", (*params, int(data["id"])))
            cid = int(data["id"])
        else:
            db.execute("INSERT INTO notification_channels(user_id,kind,label,target,secret_json,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (params[0], params[1], params[2], params[3], params[4], params[5], now, now))
            cid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = dict(db.execute("SELECT * FROM notification_channels WHERE id=?", (cid,)).fetchone())
    row["secret"] = decrypt_json(row.pop("secret_json", "{}"))
    return row


def disable_notification_channel(channel_id: int, user_id: int | None = None) -> None:
    sql, params = "UPDATE notification_channels SET enabled=0,updated_at=? WHERE id=?", [datetime.now(timezone.utc).isoformat(), int(channel_id)]
    if user_id is not None:
        sql += " AND user_id=?"
        params.append(int(user_id))
    with _lock, _connect() as db:
        db.execute(sql, params)


def delete_notification_channel(channel_id: int, user_id: int | None = None) -> None:
    """Permanently delete a notification channel from the database."""
    sql, params = "DELETE FROM notification_channels WHERE id=?", [int(channel_id)]
    if user_id is not None:
        sql += " AND user_id=?"
        params.append(int(user_id))
    with _lock, _connect() as db:
        db.execute(sql, params)


def record_migration(source_path: str, kind: str, item_key: str, status: str, details: dict[str, Any] | None = None) -> None:
    with _lock, _connect() as db:
        db.execute("""INSERT INTO migration_records(source_path,kind,item_key,status,details_json,created_at) VALUES(?,?,?,?,?,?)
            ON CONFLICT(source_path,kind,item_key) DO UPDATE SET status=excluded.status,details_json=excluded.details_json,created_at=excluded.created_at""",
            (source_path, kind, item_key, status, json.dumps(details or {}), datetime.now(timezone.utc).isoformat()))


def list_migration_records(limit: int = 500) -> list[dict[str, Any]]:
    with _connect() as db:
        return _rows(db.execute("SELECT * FROM migration_records ORDER BY id DESC LIMIT ?", (min(int(limit), 1000),)))


def set_setting(key: str, value: Any) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connect() as db:
        db.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, str(value), now))


def get_setting(key: str, default: Any = None) -> Any:
    with _connect() as db:
        row = db.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
