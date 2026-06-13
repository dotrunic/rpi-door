from dotenv import load_dotenv
import os
load_dotenv()

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import logging

smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT"))
sender_email = os.getenv("SENDER_EMAIL")
receiver_email = os.getenv("RECEIVER_EMAIL")
password = os.getenv("SMTP_PASSWORD")

def sendMessage(body):
    try:
        subjectTime = datetime.datetime.now()
        subject = '[HOMENET - DOOR] ' + body + ' ' + str(subjectTime)
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
        # log('EMAIL SUCCESSFULLY SEND TO OWNER!')
    except Exception as e:
        log(f'Error sending email: {e}')
    finally:
        server.quit()


sendMessage('[SERVER]: starting ...')
