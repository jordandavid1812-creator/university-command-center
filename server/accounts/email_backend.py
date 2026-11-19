"""The one approved email backend (launch step C): sign-up and password-reset emails.

Reviewed limits, so a settings mistake cannot weaken them:
- only a fixed list of email services, on port 587 with STARTTLS (never plain text, never SSL
  port 465 variants), verified certificates and host name, TLS 1.2 or newer;
- a 10-second time limit per connection;
- every message goes to exactly one recipient, from the configured sender address only.
Errors are raised to the caller (accounts.tokens._deliver), which logs a generic line only.
"""
import ssl

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends import smtp

APPROVED_HOSTS = ('smtp.gmail.com', 'smtp-relay.brevo.com')
PORT = 587
TIMEOUT_SECONDS = 10


class ReviewedSMTPBackend(smtp.EmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        # django.core.mail.send_mail always passes username=None and password=None; anything
        # else (another host, port, account or certificate) is refused.
        if any(value is not None for value in kwargs.values()) or set(kwargs) - {'username', 'password'}:
            raise ImproperlyConfigured('The reviewed email backend takes its settings only from Django settings.')
        host, port = settings.EMAIL_HOST, settings.EMAIL_PORT
        username, password = settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD
        if host not in APPROVED_HOSTS or port != PORT:
            raise ImproperlyConfigured('Email must use an approved service on port 587.')
        if not (settings.EMAIL_USE_TLS is True and settings.EMAIL_USE_SSL is False):
            raise ImproperlyConfigured('Email must use STARTTLS.')
        if not username or not password:
            raise ImproperlyConfigured('Email needs a sender account and an app password.')
        super().__init__(host=host, port=port, username=username, password=password, use_tls=True, use_ssl=False,
                         fail_silently=fail_silently, timeout=TIMEOUT_SECONDS, ssl_keyfile=None, ssl_certfile=None)

    @property
    def ssl_context(self):
        context = ssl.create_default_context()  # verifies the certificate and the host name
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    def send_messages(self, email_messages):
        for message in email_messages:
            recipients = message.recipients()
            if len(recipients) != 1:
                raise ValueError('Each email goes to exactly one recipient.')
            if message.from_email != settings.DEFAULT_FROM_EMAIL:
                raise ValueError('Email is sent only from the configured sender.')
        return super().send_messages(email_messages)
