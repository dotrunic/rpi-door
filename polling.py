import imaplib
import email
import time
import re
from email.header import decode_header

from utils import log
import event_store
from dotenv import load_dotenv
import os
load_dotenv()

# Matches the "#<session id>" tag that reed_contacts embeds in each subject.
SESSION_RE = re.compile(r"#(\d+)")

IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT"))
OWNER_EMAIL = os.getenv("OWNER_EMAIL")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL"))
PASSWORD = os.getenv("IMAP_PASSWORD")
DRY_RUN = os.getenv("DRY_RUN", "true").strip().lower() in ("1", "true", "yes", "on")
ARCHIVE_FOLDER = "RPi-Door-Sessions"

def connect_imap() -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(OWNER_EMAIL, PASSWORD)
    log("[INFO] Connection from IMAP.")
    return mail

def _parse_email(raw_email: bytes):
    msg = email.message_from_bytes(raw_email)
    subject, encoding = decode_header(msg.get("Subject", ""))[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding or "utf-8", errors="ignore")
    from_address = msg.get("From", "")
    return from_address, subject

def _move_uid(mail, uid, folder):
    """Move one message to folder. Prefer IMAP MOVE, fall back to COPY + delete.
    Returns True on success. (Caller expunges to clear the fallback's flags.)"""
    try:
        status, _ = mail.uid("MOVE", uid, f'"{folder}"')
        if status == "OK":
            return True
    except imaplib.IMAP4.error:
        pass  # server/imaplib without MOVE support -> fall back
    status, _ = mail.uid("COPY", uid, f'"{folder}"')
    if status == "OK":
        mail.uid("STORE", uid, "+FLAGS", "\\Deleted")
        return True
    return False

def archive_or_delete(mail, uids, action_label="[OLD SESSION]"):
    """Move the messages to ARCHIVE_FOLDER if configured, else delete them.
    In DRY_RUN nothing is changed, only logged."""
    if DRY_RUN:
        verb = f"move to '{ARCHIVE_FOLDER}'" if ARCHIVE_FOLDER else "delete"
        for uid in uids:
            status, fetched = mail.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            _, subject = _parse_email(fetched[0][1])
            log(f"[DRY RUN] Would {verb} {action_label} UID {uid.decode()} - Subject: {subject}")
        return

    if ARCHIVE_FOLDER:
        moved = sum(_move_uid(mail, uid, ARCHIVE_FOLDER) for uid in uids)
        mail.expunge()  # clears \\Deleted flags left by the COPY fallback
        log(f"[INFO] Moved {moved}/{len(uids)} {action_label} emails to '{ARCHIVE_FOLDER}'.")
    else:
        for uid in uids:
            mail.uid("STORE", uid, "+FLAGS", "\\Deleted")
        mail.expunge()
        log(f"[INFO] Deleted {len(uids)} {action_label} emails.")

def _classify(subject):
    """Return the session id parsed from a door-email subject, or None if the
    subject carries no '#<id>' tag (e.g. the '[SERVER]: starting' mail)."""
    match = SESSION_RE.search(subject)
    if not match:
        return None
    return int(match.group(1))

def group_by_session(mail, uids):
    """Return {session_id: [uid, ...]} for our tagged door emails in the inbox."""
    sessions = {}
    untagged = 0
    for uid in sorted(uids, key=lambda x: int(x)):
        status, fetched = mail.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK":
            continue
        from_addr, subject = _parse_email(fetched[0][1])
        if "development.runic" not in from_addr:
            continue
        session_id = _classify(subject)
        if session_id is None:
            untagged += 1
            continue
        sessions.setdefault(session_id, []).append(uid)

    if untagged:
        log(f"[INFO] Ignored {untagged} untagged door email(s).")
    return sessions

def cleanup_existing_pairs(mail):
    """Keep the latest session in the mailbox, delete all older sessions, and
    reconcile the event store's live/deleted status to match."""
    mail.select("inbox")
    status, data = mail.uid("search", None, "ALL")
    if status != "OK":
        log(f"Status not ok: {status}")
        return
    uids = data[0].split()
    if not uids:
        return

    sessions = group_by_session(mail, uids)
    if not sessions:
        return

    latest = max(sessions)
    older = sorted(sid for sid in sessions if sid < latest)
    log(f"[INFO] Sessions present: {sorted(sessions)} | keeping {latest}")

    if not older:
        if not DRY_RUN:
            event_store.set_status([latest], "live")
        return

    to_remove = [uid for sid in older for uid in sessions[sid]]
    log(f"[INFO] removing sessions {older}: {[uid.decode() for uid in to_remove]}")
    archive_or_delete(mail, to_remove, "[OLD SESSION]")

    if not DRY_RUN:
        event_store.set_status([latest], "live")
        event_store.set_status(older, "archived" if ARCHIVE_FOLDER else "deleted")

def poll_inbox():
    while True:
        try:
            mail = connect_imap()
            cleanup_existing_pairs(mail)

        except Exception as e:
            log(f"[ERROR] Unexpected error: {e}")
        finally:
            try:
                mail.logout()
                log("[INFO] Disconnected from IMAP.")
            except Exception:
                pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    event_store.init_db()
    poll_inbox()
