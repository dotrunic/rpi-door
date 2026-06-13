import imaplib
import email
import time
from email.header import decode_header

import logging
from dotenv import load_dotenv
import os
load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT"))
OWNER_EMAIL = os.getenv("OWNER_EMAIL")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL"))
PASSWORD = os.getenv("IMAP_PASSWORD")
DRY_RUN = os.getenv("DRY_RUN")

def connect_imap() -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(OWNER_EMAIL, PASSWORD)
    return mail

def _parse_email(raw_email: bytes):
    msg = email.message_from_bytes(raw_email)
    subject, encoding = decode_header(msg.get("Subject", ""))[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding or "utf-8", errors="ignore")
    from_address = msg.get("From", "")
    return from_address, subject

def delete_or_dry_run(mail, uids, action_label="[PAIR]"):
    """Delete or just log depending on DRY_RUN mode."""
    if DRY_RUN:
        for uid in uids:
            status, fetched = mail.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            raw_email = fetched[0][1]
            _, subject = _parse_email(raw_email)
            log(f"[DRY RUN] Would delete {action_label} email UID {uid.decode()} - Subject: {subject}")
    else:
        for uid in uids:
            mail.uid("STORE", uid, "+FLAGS", "\\Deleted")
        mail.expunge()
        # log(f"[INFO] Deleted {len(uids)} {action_label} emails.")

def get_open_closed_pairs(mail, uids):
    """Return a list of tuples (open_uid, closed_uid) representing all complete pairs."""
    open_uids = []
    closed_uids = []
    pairs = []

    for uid in sorted(uids, key=lambda x: int(x)):
        status, fetched = mail.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK":
            continue
        raw_email = fetched[0][1]
        from_addr, subject = _parse_email(raw_email)
        if "development.runic" not in from_addr:
            continue
        subject_lower = subject.lower()
        if "[open]" in subject_lower and "[open long]" not in subject_lower:
            open_uids.append(uid)
        elif "[closed]" in subject_lower:
            closed_uids.append(uid)

    # Match OPEN to next CLOSED in chronological order
    while open_uids and closed_uids:
        open_uid = open_uids.pop(0)
        closed_uid = closed_uids.pop(0)
        pairs.append((open_uid, closed_uid))

    return pairs

def cleanup_existing_pairs(mail):
    """Cleanup on startup: keep the latest OPEN+CLOSED pair, delete older ones."""
    mail.select("inbox")
    status, data = mail.uid("search", None, "ALL")
    if status != "OK":
        return
    uids = data[0].split()
    if not uids:
        return

    pairs = get_open_closed_pairs(mail, uids)
    if len(pairs) <= 1:
        return  # nothing to delete

    # Keep the last pair, delete older ones
    to_delete = [uid for pair in pairs[:-1] for uid in pair]
    # log("[INFO] Startup cleanup: Removing old OPEN+CLOSED pairs, keeping the latest pair...")
    delete_or_dry_run(mail, to_delete, "[PAIR]")

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
                # log("[INFO] Disconnected from IMAP.")
            except Exception:
                pass
        time.sleep(POLL_INTERVAL)


poll_inbox()
