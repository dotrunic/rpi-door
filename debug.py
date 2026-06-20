import imaplib
import email
from email.header import decode_header

import polling
from dotenv import load_dotenv
import os
load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT"))
IMAP_USER = os.getenv("OWNER_EMAIL")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")


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


if __name__ == "__main__":
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
