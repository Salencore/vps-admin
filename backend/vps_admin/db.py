import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def db_path() -> Path:
    path = Path(get_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                ip TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                username TEXT,
                ip TEXT,
                message TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_state (
                key TEXT PRIMARY KEY,
                last_sent_at TEXT NOT NULL
            );
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def get_setting(key: str, default: Any = None) -> Any:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return row["value"]


def set_setting(key: str, value: Any) -> None:
    payload = json.dumps(value)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, payload, utcnow()),
        )


def add_audit(actor: str, action: str, target: str | None = None, ip: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (actor, action, target, ip, created_at) VALUES (?, ?, ?, ?, ?)",
            (actor, action, target, ip, utcnow()),
        )


def list_audit(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def add_security_event(event: dict[str, str]) -> bool:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO security_events
            (event_key, event_type, username, ip, message, occurred_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_key"],
                event["event_type"],
                event.get("username"),
                event.get("ip"),
                event["message"],
                event["occurred_at"],
                utcnow(),
            ),
        )
        return cur.rowcount > 0


def list_security_events(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM security_events ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]
