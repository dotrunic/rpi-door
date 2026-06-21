import datetime


def log(message):
    """Print a timestamped line to stdout. Under systemd this is captured by the
    journal (view with `journalctl -u <service>`); no file is written to disk."""
    print(f"{datetime.datetime.now()} - {message}")
