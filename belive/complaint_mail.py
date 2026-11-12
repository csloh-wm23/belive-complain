"""Send complaint recovery codes to the address supplied at intake."""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage


def address(value):
    if not isinstance(value, str):
        raise ValueError('Enter a valid email address')
    value = value.strip()
    if value and (len(value) > 254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', value)):
        raise ValueError('Enter a valid email address')
    local, sep, domain = value.partition('@')
    return local + sep + domain.lower()


def configured():
    return bool(os.getenv('BELIVE_SMTP_HOST') and os.getenv('BELIVE_SMTP_FROM'))


def send_code(recipient, code):
    message = EmailMessage()
    message['From'] = os.environ['BELIVE_SMTP_FROM']
    message['To'] = recipient
    message['Subject'] = 'Your BeLive Complaint Code'
    message.set_content(f'Your private Complaint Code is {code}. Use it on the BeLive complaint page to open your complaint.')
    with smtplib.SMTP_SSL(os.environ['BELIVE_SMTP_HOST'], int(os.getenv('BELIVE_SMTP_PORT', '465')),
                          context=ssl.create_default_context(), timeout=10) as smtp:
        username = os.getenv('BELIVE_SMTP_USER')
        if username:
            smtp.login(username, os.environ['BELIVE_SMTP_PASSWORD'])
        smtp.send_message(message)
