"""Launch step C: the one approved email backend. No network: smtplib.SMTP is replaced by a recorder."""
import ssl
from unittest.mock import patch
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, send_mail
from django.test import SimpleTestCase, override_settings
from accounts import checks
from accounts.email_backend import ReviewedSMTPBackend

SENDER = 'University Command Center <ucc.synthetic.site@gmail.com>'
SETTINGS = dict(EMAIL_BACKEND='accounts.email_backend.ReviewedSMTPBackend', EMAIL_HOST='smtp.gmail.com', EMAIL_PORT=587,
                EMAIL_USE_TLS=True, EMAIL_USE_SSL=False, EMAIL_HOST_USER='ucc.synthetic.site@gmail.com',
                EMAIL_HOST_PASSWORD='abcdefghijklmnop', DEFAULT_FROM_EMAIL=SENDER)


class RecordingSMTP:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.host, self.port, self.kwargs, self.calls = host, port, kwargs, []
        RecordingSMTP.instances.append(self)

    def starttls(self, context=None):
        self.calls.append(('starttls', context))

    def login(self, user, password):
        self.calls.append(('login', user, password == 'abcdefghijklmnop'))

    def sendmail(self, from_address, recipients, message):
        self.calls.append(('sendmail', from_address, list(recipients)))
        return {}

    def quit(self):
        self.calls.append(('quit',))

    def close(self):
        pass


@override_settings(**SETTINGS)
class ReviewedEmailBackendTests(SimpleTestCase):
    def setUp(self):
        RecordingSMTP.instances = []
        patcher = patch.object(ReviewedSMTPBackend, 'connection_class', RecordingSMTP)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_is_the_one_approved_backend(self):
        with override_settings(UCC_SECURE_PROFILE=True):
            self.assertEqual(checks.secure_email_check(), [])
            for other in ('django.core.mail.backends.smtp.EmailBackend', 'django.core.mail.backends.console.EmailBackend'):
                with self.subTest(backend=other), override_settings(EMAIL_BACKEND=other):
                    self.assertEqual([e.id for e in checks.secure_email_check()], ['accounts.E105'])

    def test_sends_over_verified_starttls_with_login_to_one_recipient(self):
        sent = send_mail('Synthetic subject', 'Synthetic body', SENDER, ['student@example.invalid'])
        self.assertEqual(sent, 1)
        [smtp] = RecordingSMTP.instances
        self.assertEqual((smtp.host, smtp.port, smtp.kwargs['timeout']), ('smtp.gmail.com', 587, 10))
        names = [call[0] for call in smtp.calls]
        self.assertEqual(names[:3], ['starttls', 'login', 'sendmail'])  # encryption before the password
        context = smtp.calls[0][1]
        self.assertEqual((context.verify_mode, context.check_hostname), (ssl.CERT_REQUIRED, True))
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(smtp.calls[1], ('login', 'ucc.synthetic.site@gmail.com', True))
        self.assertEqual(smtp.calls[2][2], ['student@example.invalid'])

    def test_refuses_more_than_one_recipient_or_another_sender(self):
        for message in (EmailMessage('s', 'b', SENDER, ['a@example.invalid', 'b@example.invalid']),
                        EmailMessage('s', 'b', SENDER, ['a@example.invalid'], cc=['c@example.invalid']),
                        EmailMessage('s', 'b', SENDER, ['a@example.invalid'], bcc=['c@example.invalid']),
                        EmailMessage('s', 'b', 'someone@gmail.com', ['a@example.invalid'])):
            with self.subTest(to=message.recipients(), sender=message.from_email), self.assertRaises(ValueError):
                ReviewedSMTPBackend().send_messages([message])
        self.assertEqual(RecordingSMTP.instances, [])  # nothing was even connected

    def test_unsafe_settings_are_refused(self):
        for changes in ({'EMAIL_HOST': 'smtp.evil.example.com'}, {'EMAIL_PORT': 25}, {'EMAIL_PORT': 465},
                        {'EMAIL_USE_TLS': False}, {'EMAIL_USE_SSL': True}, {'EMAIL_HOST_USER': ''},
                        {'EMAIL_HOST_PASSWORD': ''}):
            with self.subTest(changes=changes), override_settings(**changes), self.assertRaises(ImproperlyConfigured):
                ReviewedSMTPBackend()
        for kwargs in ({'host': 'smtp.evil.example.com'}, {'username': 'other@gmail.com'}, {'password': 'other'},
                       {'use_ssl': False}, {'ssl_certfile': None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ImproperlyConfigured):
                ReviewedSMTPBackend(**kwargs)  # nothing can be passed in directly
        ReviewedSMTPBackend(username=None, password=None)  # what send_mail passes

    def test_a_delivery_failure_never_shows_details(self):
        from accounts import tokens

        class Broken(RecordingSMTP):
            def login(self, user, password):
                raise OSError('synthetic failure for ucc.synthetic.site@gmail.com')
        with patch.object(ReviewedSMTPBackend, 'connection_class', Broken), \
                self.assertLogs('accounts.tokens', 'WARNING') as logs:
            tokens._deliver('Subject', 'https://ucc-synthetic.example.com/accounts/verify/x/y/', 'student@example.invalid')
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn('@', logs.output[0])
        self.assertNotIn('verify', logs.output[0])
        self.assertEqual(mail.outbox if hasattr(mail, 'outbox') else [], [])
