from dotenv import load_dotenv
import os
load_dotenv()

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
from utils import log

smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT"))
sender_email = os.getenv("SENDER_EMAIL")
receiver_email = os.getenv("RECEIVER_EMAIL")
password = os.getenv("SMTP_PASSWORD")

def sendMessage(body, session_id=None):
    server = None
    try:
        subjectTime = datetime.datetime.now()
        tag = f' #{session_id}' if session_id is not None else ''
        subject = '[HOMENET - DOOR] ' + body + tag + ' ' + str(subjectTime)
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, password)
        currentTime = datetime.datetime.now()
        messageBody = body + '\n\n[TIME]: ' + str(currentTime) + '\n\n'
        msg.attach(MIMEText(messageBody, 'plain'))
        server.send_message(msg)
        log(f'Email successfully send: {msg}')
    except Exception as e:
        log(f'Error sending email: {e}')
    finally:
        if server is not None:
            server.quit()
