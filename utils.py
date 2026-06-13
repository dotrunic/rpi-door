import datetime
import os

# Shared log file. Every process (server, door loop, poller) writes here, and
# the web server reads from here. An in-memory list cannot be shared across
# separate processes, a file on disk can.
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "door.log")


def log(message):
    entry = f"{datetime.datetime.now()} - {message}"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def read_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        return [line.rstrip("\n") for line in f if line.strip()]


def reset_logs():
    open(LOG_FILE, "w").close()
