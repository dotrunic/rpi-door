"""Email a daily door-activity summary.

Intended to run shortly before the nightly 00:00 reboot (a systemd timer at
23:30), so the figures cover the day since the last midnight reboot. Reads the
event store read-only and sends through smtp_mail.dailyReport.
"""
import datetime
import event_store
import smtp_mail
from utils import log
from dotenv import load_dotenv
load_dotenv()


def _fmt(seconds):
    """Human-readable duration, e.g. 75 -> '1m 15s', 3661 -> '1h 1m 1s'."""
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    out = []
    if h:
        out.append(f"{h}h")
    if m:
        out.append(f"{m}m")
    out.append(f"{s}s")
    return " ".join(out)


def collect(now=None):
    """Build today's door stats from the event store.

    Today = since the last midnight (matches the daily reboot cycle). Events are
    grouped by session so a session that opened before midnight and closed today
    still yields a correct open->close duration; the per-type counts, however,
    only count events that actually happened today.
    """
    now = now or datetime.datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    opened = closed = longs = 0
    sessions = {}
    for e in event_store.get_events():
        t = datetime.datetime.fromisoformat(e["time"])
        today = t >= day_start
        if today:
            if e["type"] == "open":
                opened += 1
            elif e["type"] == "closed":
                closed += 1
            elif e["type"] == "open long":
                longs += 1

        s = sessions.setdefault(e["id"], {"open": None, "closed": None, "long_today": 0})
        if e["type"] == "open":
            if s["open"] is None or t < s["open"]:
                s["open"] = t
        elif e["type"] == "closed":
            s["closed"] = t
        elif e["type"] == "open long" and today:
            s["long_today"] += 1

    def is_today(t):
        return t is not None and t >= day_start

    # closes that happened today, with a known open -> (session_id, seconds_open)
    durations = [
        (sid, (s["closed"] - s["open"]).total_seconds())
        for sid, s in sessions.items()
        if is_today(s["closed"]) and s["open"] is not None
    ]

    # sessions that triggered 'open long' today, with how long they were open
    # (use the close time, or 'now' if still open) -> (id, seconds, still_open)
    long_open = [
        (sid, ((s["closed"] or now) - s["open"]).total_seconds(), s["closed"] is None)
        for sid, s in sessions.items()
        if s["long_today"] > 0 and s["open"] is not None
    ]

    return {
        "now": now,
        "date": day_start.date().isoformat(),
        "opened": opened, "closed": closed, "longs": longs,
        "durations": durations, "long_open": long_open,
    }


def build_report(st):
    """Render the stats dict as a multi-line plain-text report."""
    lines = [
        f"Door activity for {st['date']} (since 00:00, as of {st['now'].strftime('%H:%M')})",
        "",
        f"Times opened:        {st['opened']}",
        f"Times closed:        {st['closed']}",
        f"'Open long' pings:   {st['longs']}",
        "",
    ]

    if st["durations"]:
        fastest = min(st["durations"], key=lambda x: x[1])
        slowest = max(st["durations"], key=lambda x: x[1])
        lines.append(f"Fastest close: {_fmt(fastest[1])} (session {fastest[0]})")
        lines.append(f"Slowest close: {_fmt(slowest[1])} (session {slowest[0]})")
    else:
        lines.append("No completed open/close cycle today.")

    lines.append("")

    if st["long_open"]:
        lines.append("Open-long events triggered:")
        for sid, secs, still_open in sorted(st["long_open"]):
            suffix = " (STILL OPEN)" if still_open else ""
            lines.append(f"  session {sid}: open for {_fmt(secs)}{suffix}")
    else:
        lines.append("No 'open long' events today.")

    return "\n".join(lines)


def main():
    event_store.init_db()
    st = collect()
    report = build_report(st)
    log(f"[DAILY STATS] opened={st['opened']} closed={st['closed']} longs={st['longs']}")
    smtp_mail.dailyReport(f"[DAILY STATS] {st['date']}", report)


if __name__ == "__main__":
    main()
