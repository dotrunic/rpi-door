# rpi-door

Raspberry Pi door monitor. The work is split across independent processes, each
run as its own systemd unit on the Pi (units live in `/etc/systemd/system/`).
The code is checked out at `/home/user/development/` and run with the venv
interpreter `/home/user/development/.venv/bin/python` as user `user`.

| Service                  | Script             | What it does                                          |
| ------------------------ | ------------------ | ----------------------------------------------------- |
| `reed_contacts.service`  | `reed_contacts.py` | Reads the reed switch on GPIO 17, emails open/close.  |
| `reed_mailing.service`   | `polling.py`       | Polls the IMAP inbox and cleans up old mail pairs.    |
| `reed_dailystats.service`| `daily_stats.py`   | Oneshot, emails the day's door stats. Triggered by the timer below. |
| `reed_dailystats.timer`  | —                  | Fires daily at 23:30 (`OnCalendar=*-*-* 23:30:00`, `Persistent=true`), 30 min before the reboot. |
| `reed_reboot.service`    | `/sbin/reboot`     | Oneshot, triggered by the timer below.                |
| `reed_reboot.timer`      | —                  | Reboots the Pi daily at midnight (`OnCalendar=*-*-* 00:00:00`, `Persistent=true`). |

The processes don't write a log file; each one prints to stdout, which systemd
captures in the journal (see **View logs** below).

## Managing the services (systemd)

### List the project's services

```bash
systemctl list-units --type=service | grep reed
```

### Check status

```bash
sudo systemctl status reed_contacts.service
```

### View logs

systemd captures each service's stdout/stderr in the journal:

```bash
# last 100 lines
sudo journalctl -u reed_contacts.service -n 100

# follow live (Ctrl-C to stop)
sudo journalctl -u reed_contacts.service -f

# only since the last boot
sudo journalctl -u reed_contacts.service -b
```

### The reboot timer

`reed_reboot.service` is triggered by `reed_reboot.timer`, not run directly. To
inspect timers (when each last/next fires):

```bash
systemctl list-timers | grep reed
sudo systemctl status reed_reboot.timer
```

Enable/disable the schedule by acting on the **`.timer`**, not the `.service`:

```bash
sudo systemctl enable --now reed_reboot.timer
sudo systemctl disable --now reed_reboot.timer
```

### Start / stop / restart

```bash
sudo systemctl start   reed_contacts.service
sudo systemctl stop    reed_contacts.service
sudo systemctl restart reed_contacts.service
```

### Add a new service

1. Create a unit file in `/etc/systemd/system/`, e.g. `reed_contacts.service`:

   ```ini
   [Unit]
   Description=Reedcontact service
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   ExecStartPre=/bin/sleep 60
   ExecStart=/home/user/development/.venv/bin/python /home/user/development/reed_contacts.py
   Restart=always
   User=user
   WorkingDirectory=/home/user/development/

   [Install]
   WantedBy=multi-user.target
   ```

   > This matches the pattern of the existing units. Change `ExecStart` to the
   > target script (`reed_contacts.py` or `polling.py`). The
   > `ExecStartPre=/bin/sleep 60` gives the network/clock time to settle after
   > the midnight reboot before the process starts.

2. Reload systemd so it picks up the new file, then enable + start it:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now reed_contacts.service
   ```

   `enable` makes it start automatically on boot; `--now` also starts it
   immediately.

### Remove a service

```bash
sudo systemctl disable --now reed_contacts.service   # stop + no auto-start
sudo rm /etc/systemd/system/reed_contacts.service
sudo systemctl daemon-reload
sudo systemctl reset-failed                          # clear any failed state
```
