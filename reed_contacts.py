import RPi.GPIO as GPIO
import time
import datetime
import smtp_mail
import event_store

from utils import log
from dotenv import load_dotenv
import os
load_dotenv()

event_store.init_db()

PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

send_interval = int(os.getenv("send_interval"))
smtp_mail.sendMessage('[SERVER]: starting ...')
log(f"[SERVER]: starting ... {datetime.datetime.now()}")
door_is_open = GPIO.input(PIN) == GPIO.HIGH
last_sent = time.time()

try:
    while True:
        state = GPIO.input(PIN)
        current_time = time.time()

        if state == GPIO.LOW:
            if door_is_open:
                session_id = event_store.record_event('closed')
                smtp_mail.sendMessage('[CLOSED]', session_id)
                log(f"Door closed (session {session_id}): {datetime.datetime.now()}")
            door_is_open = False
            last_sent = 0  # reset open long timer

        else:
            if not door_is_open:  # First open detection
                session_id = event_store.record_event('open')
                smtp_mail.sendMessage('[OPEN]', session_id)
                log(f"Door opened (session {session_id}): {datetime.datetime.now()}")
                last_sent = current_time
                door_is_open = True
            elif current_time - last_sent >= send_interval:
                # Send OPEN LONG every minute while door stays open
                session_id = event_store.record_event('open long')
                smtp_mail.sendMessage('[OPEN LONG]', session_id)
                log(f"Door open (LONG, session {session_id}): {datetime.datetime.now()}")
                last_sent = current_time

        time.sleep(0.5)

except KeyboardInterrupt:
    log("Exiting...")

finally:
    GPIO.cleanup()
