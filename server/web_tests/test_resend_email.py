"""Resend (owner's choice): account emails from an address on the site's own domain through
smtp.resend.com, with replies to the public contact inbox. No network: smtplib is replaced."""
from email import message_from_bytes
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from accounts import checks
from accounts.email_backend import ReviewedSMTPBackend
from config.settings import public_site
from .base import WebsiteCase
from .test_email_backend import RecordingSMTP

KEY = 're_synthetic_0123456789abcdef'
SENDER = 'UniCommand <noreply@unicommand.example.ng>'
RESEND = dict(EMAIL_BACKEND='accounts.email_backend.ReviewedSMTPBackend', EMAIL_HOST='smtp.resend.com', EMAIL_PORT=587,
              EMAIL_USE_TLS=True, EMAIL_USE_SSL=False, EMAIL_HOST_USER='resend', EMAIL_HOST_PASSWORD=KEY,
              DEFAULT_FROM_EMAIL=SENDER, UCC_EMAIL_REPLY_TO='unicommand.info@gmail.com')


class MessageRecorder(RecordingSMTP):
    def login(self, user, password):
        self.calls.append(('login', user, password == KEY))

    def sendmail(self, from_address, recipients, message):
        raw = message if isinstance(message, (bytes, bytearray)) else message.encode()
        self.calls.append(('sendmail', from_address, list(recipients), message_from_bytes(bytes(raw))))
        return {}


def configured(environ, host='unicommand.example.ng'):
    namespace = {'UCC_SITE_HOST': host}
    public_site.configure_email(namespace, environ)
    return namespace


@override_settings(**RESEND)
class ResendBackendTests(SimpleTestCase):
    def setUp(self):
        RecordingSMTP.instances = []
        patcher = patch.object(ReviewedSMTPBackend, 'connection_class', MessageRecorder)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sends_through_resend_from_the_own_domain_with_replies_to_the_contact_inbox(self):
        self.assertEqual(send_mail('Synthetic subject', 'Synthetic body', SENDER, ['student@example.invalid']), 1)
        [smtp] = RecordingSMTP.instances
        self.assertEqual((smtp.host, smtp.port), ('smtp.resend.com', 587))
        self.assertEqual([call[0] for call in smtp.calls][:3], ['starttls', 'login', 'sendmail'])
        self.assertEqual(smtp.calls[1], ('login', 'resend', True))
        _, sender, recipients, message = smtp.calls[2]
        self.assertEqual((sender, recipients), (SENDER, ['student@example.invalid']))
        self.assertEqual(message['From'], SENDER)
        self.assertEqual(message['Reply-To'], 'unicommand.info@gmail.com')
        self.assertNotIn('unicommand.info@gmail.com', recipients)  # a reply address is never a copy

    def test_it_is_still_the_one_approved_backend(self):
        with override_settings(UCC_SECURE_PROFILE=True):
            self.assertEqual(checks.secure_email_check(), [])

    def test_gmail_messages_get_no_reply_to(self):
        gmail = dict(RESEND, EMAIL_HOST='smtp.gmail.com', EMAIL_HOST_USER='ucc.synthetic.site@gmail.com',
                     DEFAULT_FROM_EMAIL='UniCommand <ucc.synthetic.site@gmail.com>', UCC_EMAIL_REPLY_TO='')
        with override_settings(**gmail):
            send_mail('s', 'b', 'UniCommand <ucc.synthetic.site@gmail.com>', ['student@example.invalid'])
        message = RecordingSMTP.instances[-1].calls[2][3]
        self.assertIsNone(message['Reply-To'])


class ResendSettingsTests(SimpleTestCase):
    def test_an_address_on_the_site_domain_selects_resend(self):
        settings = configured({'UCC_EMAIL_ADDRESS': 'NoReply@unicommand.example.ng', 'UCC_RESEND_API_KEY': KEY})
        self.assertEqual((settings['EMAIL_HOST'], settings['EMAIL_PORT'], settings['EMAIL_USE_TLS'],
                          settings['EMAIL_USE_SSL'], settings['EMAIL_HOST_USER'], settings['EMAIL_HOST_PASSWORD']),
                         ('smtp.resend.com', 587, True, False, 'resend', KEY))
        self.assertEqual(settings['DEFAULT_FROM_EMAIL'], SENDER)
        self.assertEqual(settings['UCC_EMAIL_REPLY_TO'], 'unicommand.info@gmail.com')
        self.assertEqual(settings['EMAIL_BACKEND'], 'accounts.email_backend.ReviewedSMTPBackend')

    def test_resend_needs_a_well_formed_key_and_never_echoes_it(self):
        for key in ('', 'short', 'sk_live_0123456789abcdef', 're_has spaces 0123456789', 're_' + 'a' * 200):
            with self.subTest(key=key[:12]), self.assertRaises(ImproperlyConfigured) as caught:
                configured({'UCC_EMAIL_ADDRESS': 'noreply@unicommand.example.ng', 'UCC_RESEND_API_KEY': key})
            self.assertIn('UCC_RESEND_API_KEY', str(caught.exception))
            if key:
                self.assertNotIn(key, str(caught.exception))

    def test_only_the_site_domain_or_gmail_can_send(self):
        for address in ('noreply@other.example.ng', 'noreply@sub.unicommand.example.ng', 'someone@yahoo.com',
                        'noreply@unicommand.example.ng.evil.com', 'not an address'):
            with self.subTest(address=address), self.assertRaises(ImproperlyConfigured) as caught:
                configured({'UCC_EMAIL_ADDRESS': address, 'UCC_RESEND_API_KEY': KEY})
            self.assertIn('UCC_EMAIL_ADDRESS', str(caught.exception))

    def test_gmail_is_unchanged(self):
        settings = configured({'UCC_EMAIL_ADDRESS': 'ucc.synthetic.site@gmail.com',
                               'UCC_EMAIL_APP_PASSWORD': 'abcd efgh ijkl mnop', 'UCC_RESEND_API_KEY': KEY})
        self.assertEqual((settings['EMAIL_HOST'], settings['EMAIL_HOST_USER'], settings['EMAIL_HOST_PASSWORD'],
                          settings['UCC_EMAIL_REPLY_TO']),
                         ('smtp.gmail.com', 'ucc.synthetic.site@gmail.com', 'abcdefghijklmnop', ''))


class PrivacyNoticeNamesTheEmailServiceTests(WebsiteCase):
    def test_gmail_until_resend_is_configured(self):
        with override_settings(EMAIL_HOST='smtp.gmail.com'):
            html = self.client.get(reverse('accounts:privacy')).content.decode()
        self.assertIn('<strong>Google (Gmail)</strong> delivers our emails', html)
        self.assertNotIn('<strong>Resend</strong>', html)
        with override_settings(EMAIL_HOST='smtp.resend.com'):
            html = self.client.get(reverse('accounts:privacy')).content.decode()
        self.assertIn('<strong>Resend</strong> (a United States company; our emails are sent from its Ireland region)', html)
        self.assertNotIn('<strong>Google (Gmail)</strong> delivers our emails', html)
        self.assertIn('your reply goes to our Gmail contact inbox', html)
