import sys
import sqlite3
import imaplib
import email
from email.header import decode_header

import polling
import event_store
from dotenv import load_dotenv
import os
load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT"))
IMAP_USER = os.getenv("OWNER_EMAIL")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")


# ---------------------------------------------------------------------------
# IMAP debugging
# ---------------------------------------------------------------------------

def mail_login() -> imaplib.IMAP4_SSL:
    """Open an IMAP connection and log in with the configured user."""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)
    return mail


def mail_logout(mail):
    """Close the connection."""
    mail.logout()


def mail_fetch(mail):
    """Fetch all messages currently in the inbox WITHOUT marking them as read.

    Uses BODY.PEEK[] so the \\Seen flag is never set (a plain BODY[]/RFC822
    fetch would mark each message as read). Returns a list of parsed
    email.message.Message objects.
    """
    mail.select("inbox")
    status, data = mail.uid("search", None, "ALL")
    if status != "OK":
        return []

    messages = []
    for uid in data[0].split():
        status, fetched = mail.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK":
            continue
        raw_email = fetched[0][1]
        messages.append(email.message_from_bytes(raw_email))
    return messages


def test_dry_run(mail):
    """Read-only: show what polling's cleanup WOULD delete, without deleting.

    Reuses polling.group_by_session (the real grouping logic) and applies the
    same "keep the latest session, delete older ones" rule as
    cleanup_existing_pairs, but only prints the result. Never touches the
    mailbox, regardless of the DRY_RUN setting.
    """
    print(f"DRY_RUN currently = {polling.DRY_RUN}")
    mail.select("inbox")
    status, data = mail.uid("search", None, "ALL")
    uids = data[0].split() if status == "OK" else []
    print(f"{len(uids)} message(s) in inbox")

    sessions = polling.group_by_session(mail, uids)
    print(f"Detected {len(sessions)} tagged session(s):")
    for session_id in sorted(sessions):
        print(f"  session {session_id}: {[uid.decode() for uid in sessions[session_id]]}")

    if len(sessions) <= 1:
        print("=> Nothing would be deleted (only the latest session is kept).")
        return

    latest = max(sessions)
    older = sorted(sid for sid in sessions if sid < latest)
    to_remove = [uid for sid in older for uid in sessions[sid]]
    verb = f"move to '{polling.ARCHIVE_FOLDER}'" if polling.ARCHIVE_FOLDER else "delete"
    print(f"=> Would {verb} sessions {older} "
          f"({[uid.decode() for uid in to_remove]}), keeping session {latest}.")


def mail_report():
    """Print the inbox contents and the dry-run cleanup preview."""
    mail = mail_login()
    try:
        messages = mail_fetch(mail)
        print(f"{len(messages)} message(s) in inbox:")
        for msg in messages:
            subject, encoding = decode_header(msg.get("Subject", ""))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8", errors="ignore")
            print(f"  - {msg.get('From', '')}: {subject}")

        print("\n--- dry-run cleanup preview ---")
        test_dry_run(mail)
    finally:
        mail_logout(mail)


# ---------------------------------------------------------------------------
# SQL debugging (events.db)
#
# All queries are READ-ONLY. The connection is opened with query_only=ON so a
# stray UPDATE/DELETE here can never corrupt the live event store. The DB path
# is taken from event_store so there is a single source of truth.
# ---------------------------------------------------------------------------

def _query(sql, params=()):
    """Run a read-only SQL query against events.db and return sqlite3.Row rows."""
    conn = sqlite3.connect(event_store.DB_FILE, timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")  # hard guard: no writes from debug
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _print_rows(rows, title=None, empty="(no rows)"):
    """Pretty-print a list of sqlite3.Row as an aligned table."""
    if title:
        print(f"\n=== {title} ===")
    if not rows:
        print(empty)
        return
    cols = rows[0].keys()
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


def counter():
    """The persisted session counter (next id handed to an 'open'). Survives
    reboots; only a 'closed' event advances it."""
    rows = _query("SELECT key, value FROM meta")
    _print_rows(rows, "meta (session counter)")
    return rows


def all_events(limit=None):
    """Every event, oldest first. Pass limit to cap the output."""
    sql = ("SELECT rowid, session_id, type, time, status "
           "FROM events ORDER BY rowid")
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = _query(sql)
    _print_rows(rows, f"all events{f' (first {limit})' if limit else ''}")
    return rows


def recent_events(n=20):
    """The most recent n events, newest first."""
    rows = _query(
        "SELECT rowid, session_id, type, time, status "
        "FROM events ORDER BY rowid DESC LIMIT ?",
        (int(n),),
    )
    _print_rows(rows, f"{n} most recent events")
    return rows


def by_type():
    """Count events grouped by type (open / open long / closed)."""
    rows = _query(
        "SELECT type, COUNT(*) AS count FROM events GROUP BY type ORDER BY count DESC"
    )
    _print_rows(rows, "event count by type")
    return rows


def by_status():
    """Count events grouped by status (live / archived / deleted)."""
    rows = _query(
        "SELECT status, COUNT(*) AS count FROM events GROUP BY status ORDER BY count DESC"
    )
    _print_rows(rows, "event count by status")
    return rows


def sessions():
    """One row per session: how many events it has, when it was first/last seen,
    how many of each event type, and the distinct statuses on it."""
    rows = _query(
        """SELECT session_id,
                  COUNT(*)                         AS events,
                  SUM(type = 'open')               AS opens,
                  SUM(type = 'open long')          AS open_longs,
                  SUM(type = 'closed')             AS closes,
                  MIN(time)                        AS first_seen,
                  MAX(time)                        AS last_seen,
                  GROUP_CONCAT(DISTINCT status)    AS statuses
           FROM events
           GROUP BY session_id
           ORDER BY session_id"""
    )
    _print_rows(rows, "sessions overview")
    return rows


def open_sessions():
    """Sessions that have an 'open' but no 'closed' — i.e. still open, or whose
    close was missed (e.g. the door closed while the Pi was rebooting)."""
    rows = _query(
        """SELECT session_id,
                  COUNT(*)   AS events,
                  MIN(time)  AS opened,
                  MAX(time)  AS last_seen
           FROM events
           GROUP BY session_id
           HAVING SUM(type = 'closed') = 0
           ORDER BY session_id"""
    )
    _print_rows(rows, "incomplete sessions (no 'closed')",
                empty="(none — every session has a matching close)")
    return rows


def durations():
    """For every closed session, how long the door was open (open -> closed),
    in seconds. Useful for spotting stuck/long openings."""
    rows = _query(
        """SELECT session_id,
                  MIN(time)                                          AS opened,
                  MAX(CASE WHEN type = 'closed' THEN time END)       AS closed,
                  ROUND(
                      (julianday(MAX(CASE WHEN type = 'closed' THEN time END))
                       - julianday(MIN(time))) * 86400, 1)           AS seconds_open
           FROM events
           GROUP BY session_id
           HAVING closed IS NOT NULL
           ORDER BY session_id"""
    )
    _print_rows(rows, "open durations per session (seconds)")
    return rows


def counter_sanity():
    """Cross-check the persisted counter against the events table.

    Normal: counter == (max closed session) + 1, and any session_id >= counter
    means a session is currently open / in flight. A session that has an 'open'
    but session_id < counter and no 'closed' is a missed close (see
    open_sessions)."""
    rows = _query(
        """SELECT (SELECT value FROM meta WHERE key = 'current_session_id') AS counter,
                  (SELECT MAX(session_id) FROM events)                        AS max_session,
                  (SELECT MAX(session_id) FROM events WHERE type = 'closed')  AS max_closed,
                  (SELECT COUNT(*) FROM events)                               AS total_events"""
    )
    _print_rows(rows, "counter sanity check")
    if rows:
        r = rows[0]
        counter_val, max_closed = r["counter"], r["max_closed"]
        expected = (max_closed + 1) if max_closed is not None else 0
        if counter_val == expected:
            print(f"OK: counter ({counter_val}) == max_closed+1 ({expected}); "
                  "no open session in flight.")
        elif counter_val > expected:
            print(f"NOTE: counter ({counter_val}) > max_closed+1 ({expected}) — "
                  "normal if a session is currently open and not yet closed.")
        else:
            print(f"WARNING: counter ({counter_val}) < max_closed+1 ({expected}) — "
                  "unexpected; the counter looks behind the recorded closes.")
    return rows


def report():
    """Run the full SQL debugging report."""
    counter()
    by_type()
    by_status()
    sessions()
    open_sessions()
    durations()
    counter_sanity()


def run(sql, *params):
    """Run an arbitrary READ-ONLY query and print the result. Writes are blocked
    by PRAGMA query_only, so this is safe for ad-hoc SELECTs, e.g.:
        python -c "import debug; debug.run('SELECT * FROM events WHERE session_id=4')"
    """
    rows = _query(sql, params)
    _print_rows(rows, sql)
    return rows


# ---------------------------------------------------------------------------

USAGE = """usage: python debug.py [command]

  events   full SQL report on events.db (default)
  mail     inbox contents + dry-run cleanup preview (IMAP)
  help     show this message

Individual SQL helpers are importable, e.g.:
  python -c "import debug; debug.recent_events(10)"
  python -c "import debug; debug.durations()"
  python -c "import debug; debug.run('SELECT * FROM events WHERE status=\\'archived\\'')"
"""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "events"
    if cmd == "events":
        report()
    elif cmd == "mail":
        mail_report()
    else:
        print(USAGE)
