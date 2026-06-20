"""Persistent store for door events.

Each event is grouped into a "session" so an OPEN and its matching CLOSED share
an id (OPEN LONG shares it too; only CLOSED advances the counter). The counter
is persisted so it survives the nightly reboot, and SQLite is used so the door
loop (reed_contacts) and the cleanup loop (polling) can both touch it safely.
"""
import sqlite3
import datetime
import os

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.db")


def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")  # safer concurrent access
    return conn


def init_db():
    """Create the tables if they don't exist. Idempotent; call once at startup."""
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   rowid      INTEGER PRIMARY KEY AUTOINCREMENT,
                   session_id INTEGER NOT NULL,
                   type       TEXT    NOT NULL,
                   time       TEXT    NOT NULL,
                   status     TEXT    NOT NULL DEFAULT 'live'
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS meta (
                   key   TEXT PRIMARY KEY,
                   value INTEGER NOT NULL
               )"""
        )
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('current_session_id', 0)"
        )
        conn.commit()
    finally:
        conn.close()


def record_event(event_type):
    """Insert a door event and return its session id.

    open / open long -> current session id (no increment)
    closed           -> current session id, then increment the counter
    """
    now = datetime.datetime.now().isoformat(sep=" ")
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")  # take the write lock before read+update
        row = conn.execute(
            "SELECT value FROM meta WHERE key='current_session_id'"
        ).fetchone()
        session_id = row[0] if row else 0
        conn.execute(
            "INSERT INTO events(session_id, type, time, status) VALUES (?, ?, ?, 'live')",
            (session_id, event_type, now),
        )
        if event_type == "closed":
            conn.execute(
                "UPDATE meta SET value=? WHERE key='current_session_id'",
                (session_id + 1,),
            )
        conn.commit()
    finally:
        conn.close()
    return session_id


def set_status(session_ids, status):
    """Set the status ('live' | 'archived' | 'deleted') for all events whose
    session is in session_ids."""
    ids = list(session_ids)
    if not ids:
        return
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE events SET status=? WHERE session_id IN ({placeholders})",
            [status, *ids],
        )
        conn.commit()
    finally:
        conn.close()


def get_events():
    """Return all events oldest-first (for inspection / the web UI)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT session_id, type, time, status FROM events ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "type": r[1], "time": r[2], "status": r[3]} for r in rows]
