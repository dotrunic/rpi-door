import RPi.GPIO as GPIO
import time
import datetime
import smtp_mail

from utils import log, stash
from dotenv import load_dotenv
import os
load_dotenv()

PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

send_interval = int(os.getenv("send_interval"))
last_sent = int(os.getenv("last_sent"))
door_is_open = os.getenv("door_is_open")

try:
    while True:
        state = GPIO.input(PIN)
        current_time = time.time()

        if state == GPIO.LOW:
            if door_is_open:
                smtp_mail.sendMessage('[CLOSED]')
                log(f"Door closed: {datetime.datetime.now()}")
            door_is_open = False
            last_sent = 0  # reset open long timer

        else:
            if not door_is_open:  # First open detection
                smtp_mail.sendMessage('[OPEN]')
                log(f"Door opened: {datetime.datetime.now()}")
                last_sent = current_time
                door_is_open = True
            elif current_time - last_sent >= send_interval:
                # Send OPEN LONG every minute while door stays open
                smtp_mail.sendMessage('[OPEN LONG]')
                log(f"Door open (LONG): {datetime.datetime.now()}")
                last_sent = current_time

        time.sleep(0.5)

except KeyboardInterrupt:
    log("Exiting...")

finally:
    GPIO.cleanup()
