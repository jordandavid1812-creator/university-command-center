"""Presentation only: no database, provider calls, real addresses or valid secrets."""
import struct
from unittest.mock import patch
from xml.etree import ElementTree

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core import mail
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.test import SimpleTestCase, override_settings

from accounts import email_change, tokens
from accounts.email_content import branded_html


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailPresentationTests(SimpleTestCase):
    def setUp(self):
        mail.outbox = []

    def test_signup_code_keeps_plain_body_subject_sender_and_single_recipient(self):
        text = 'Your University Command Center sign-up code is 012345\n\nIt works for 1 minute.'
        subject = '012345 is your University Command Center code'
        tokens._deliver(subject, text, 'synthetic@example.invalid', code='012345',
                        action_url='https://ucc.example.invalid/accounts/verify/code/')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, subject)
        self.assertEqual(message.body, text + '\n\nIgnore this email if you did not request it.')
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(message.to, ['synthetic@example.invalid'])
        self.assertEqual((message.cc, message.bcc, message.attachments), ([], [], []))
        self.assertEqual(message.message().get_content_type(), 'multipart/alternative')
        self.assertEqual(len(message.alternatives), 1)
        html, mime = message.alternatives[0]
        self.assertEqual(mime, 'text/html')
        for value in ('University Command Center', '012345', 'It works for 1 minute.',
                      'href="https://ucc.example.invalid/accounts/verify/code/"'):
            self.assertIn(value, html)

    def test_email_change_code_and_notice_keep_existing_content_and_destinations(self):
        code_text = 'Your University Command Center email-change code is 654321\n\nIt works for 10 minutes.'
        email_change._send('Existing subject', code_text, 'new@example.invalid', code='654321')
        email_change._send('Email was changed', 'Existing notification text.', 'old@example.invalid')
        self.assertEqual([m.to for m in mail.outbox], [['new@example.invalid'], ['old@example.invalid']])
        self.assertEqual([m.body for m in mail.outbox], [code_text, 'Existing notification text.'])
        self.assertIn('654321', mail.outbox[0].alternatives[0].content)
        self.assertIn('It works for 10 minutes.', mail.outbox[0].alternatives[0].content)
        self.assertNotIn('Your one-time code', mail.outbox[1].alternatives[0].content)
        self.assertNotIn('654321', mail.outbox[1].alternatives[0].content)

    def test_recovery_link_is_identical_in_plain_and_html(self):
        link = 'https://ucc.example.invalid/accounts/reset/synthetic-selector/synthetic-secret/'
        tokens._deliver('Existing reset subject', link, 'synthetic@example.invalid', action_url=link)
        self.assertEqual(mail.outbox[0].body, link + '\n\nIgnore this email if you did not request it.')
        self.assertIn(f'href="{link}"', mail.outbox[0].alternatives[0].content)
        self.assertNotIn('Your one-time code', mail.outbox[0].alternatives[0].content)

    def test_payload_is_escaped_and_html_loads_no_tracking_or_external_assets(self):
        html = branded_html('<img src="https://tracker.example.invalid/pixel"> & SECRET',
                            code='012345', action_url='https://ucc.example.invalid/verify/?a=1&b=2')
        self.assertIn('&lt;img', html)
        self.assertIn('&amp; SECRET', html)
        self.assertIn('href="https://ucc.example.invalid/verify/?a=1&amp;b=2"', html)
        for tag in ('<img', '<script', '<iframe', '<form', '<link', 'url(', '@import'):
            self.assertNotIn(tag, html)
        for link in ('javascript:alert(1)', 'data:text/html,unsafe', '//other.example.invalid',
                     'https://ucc.example.invalid/\nunsafe', 'https://[malformed'):
            with self.subTest(link=link):
                html = branded_html('Existing safe message.', action_url=link)
                # Invalid URLs may fall back entirely to plain text; none become an anchor.
                self.assertTrue(html is None or '<a ' not in html)

    def test_renderer_failure_still_sends_plain_email_and_logs_no_payload(self):
        secret = 'SYNTHETIC_FORMATTER_SECRET'
        with patch('accounts.email_content.render_to_string', side_effect=RuntimeError(secret)), \
                self.assertLogs('accounts', level='WARNING') as captured:
            tokens._deliver('Existing subject', secret, 'private@example.invalid', code='012345')
            email_change._send('Existing subject', secret, 'private@example.invalid', code='012345')
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual([message.body for message in mail.outbox], [
            secret + '\n\nIgnore this email if you did not request it.', secret])
        self.assertEqual([message.to for message in mail.outbox], [['private@example.invalid']] * 2)
        self.assertTrue(all(not message.alternatives for message in mail.outbox))
        for value in (secret, 'private@example.invalid', '012345', 'RuntimeError'):
            self.assertNotIn(value, '\n'.join(captured.output))

    def test_plain_fallback_survives_ordinary_diagnostic_logging_failure(self):
        for stage in ('lookup', 'write'):
            mail.outbox = []
            with self.subTest(stage=stage), \
                    patch('accounts.email_content.render_to_string', side_effect=RuntimeError('synthetic formatter fault')), \
                    patch('accounts.email_content.logging.getLogger') as logger:
                if stage == 'lookup':
                    logger.side_effect = RuntimeError('synthetic logging lookup fault')
                else:
                    logger.return_value.warning.side_effect = OSError('synthetic log stream fault')
                tokens._deliver('Existing subject', 'Original body.', 'synthetic@example.invalid')
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].body, 'Original body.\n\nIgnore this email if you did not request it.')
            self.assertEqual(mail.outbox[0].alternatives, [])

    def test_smtp_failure_preserves_existing_handling_and_process_control_propagates(self):
        with patch('accounts.tokens.send_mail', side_effect=RuntimeError('SYNTHETIC_SMTP_SECRET')), \
                self.assertLogs('accounts.tokens', level='WARNING') as captured:
            tokens._deliver('Existing subject', 'Existing body', 'synthetic@example.invalid')
        self.assertNotIn('SYNTHETIC_SMTP_SECRET', '\n'.join(captured.output))
        self.assertEqual(mail.outbox, [])
        with patch('accounts.email_content.render_to_string', side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            tokens._deliver('Existing subject', 'Existing body', 'synthetic@example.invalid')
        self.assertEqual(mail.outbox, [])


class BrandIconTests(SimpleTestCase):
    def test_global_public_and_workspace_shells_link_packaged_icons(self):
        for enabled, authenticated in ((False, False), (True, False), (True, True)):
            with self.subTest(website=enabled, signed_in=authenticated), override_settings(
                    ROOT_URLCONF='config.web_urls' if enabled else 'config.auth_urls'):
                html = render_to_string('accounts/message.html', {
                    'website_enabled': enabled, 'workspace_authenticated': authenticated,
                    'navigation': [], 'message': 'Synthetic account message.',
                })
                for path in ('favicon.svg', 'favicon.ico', 'apple-touch-icon.png'):
                    asset = 'accounts/brand/' + path
                    self.assertIsNotNone(finders.find(asset))
                    self.assertIn(f'href="{static(asset)}"', html)
                self.assertEqual(html.count('referrerpolicy="no-referrer"'), 3)

    def test_vector_is_self_contained_and_bitmap_sizes_are_valid(self):
        from pathlib import Path
        svg = ElementTree.fromstring(Path(finders.find('accounts/brand/favicon.svg')).read_text())
        self.assertEqual(svg.attrib['viewBox'], '0 0 32 32')
        for element in svg.iter():
            self.assertIn(element.tag.split('}')[-1], ('svg', 'title', 'rect', 'path'))
            self.assertFalse(any(key.split('}')[-1] in ('href', 'src') or key.startswith('on')
                                 for key in element.attrib))
        ico = Path(finders.find('accounts/brand/favicon.ico')).read_bytes()
        self.assertEqual(struct.unpack_from('<HHH', ico), (0, 1, 2))
        for i, size in enumerate((16, 32)):
            width, height, _, _, planes, bits, length, offset = struct.unpack_from('<BBBBHHII', ico, 6 + i * 16)
            self.assertEqual((width, height, planes, bits), (size, size, 1, 32))
            png = ico[offset:offset + length]
            self.assertEqual(len(png), length)
            self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack_from('>II', png, 16), (size, size))
        touch = Path(finders.find('accounts/brand/apple-touch-icon.png')).read_bytes()
        self.assertEqual(touch[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack_from('>II', touch, 16), (180, 180))
