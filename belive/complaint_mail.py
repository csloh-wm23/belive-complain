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
    if value:
        labels=domain.split('.')
        if (not local or len(local)>64 or local.startswith('.') or local.endswith('.') or '..' in local
                or any(not label or len(label)>63 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?',label) for label in labels)):
            raise ValueError('Enter a valid email address')
        if domain.lower() in {'gmail.com','googlemail.com'} and not re.fullmatch(r'[A-Za-z0-9.]+(?:\+[A-Za-z0-9._-]+)?',local):
            raise ValueError('Enter a valid Gmail address')
    return local + sep + domain.lower()


def configured():
    return bool(os.getenv('BELIVE_SMTP_HOST') and os.getenv('BELIVE_SMTP_FROM'))


def send_code(recipient, code):
    send_message(recipient,'Your BeLive Complaint Code',
                 f'Your private Complaint Code is {code}. Use it on the BeLive complaint page to open your complaint.')


def send_verification(recipient, code):
    send_message(recipient,'Verify your BeLive recovery email',
                 f'Your BeLive email verification code is {code}. It expires in 10 minutes.')


def send_message(recipient, subject, body):
    message = EmailMessage()
    message['From'] = os.environ['BELIVE_SMTP_FROM']
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    with smtplib.SMTP_SSL(os.environ['BELIVE_SMTP_HOST'], int(os.getenv('BELIVE_SMTP_PORT', '465')),
                          context=ssl.create_default_context(), timeout=10) as smtp:
        username = os.getenv('BELIVE_SMTP_USER')
        if username:
            smtp.login(username, os.environ['BELIVE_SMTP_PASSWORD'])
        smtp.send_message(message)
