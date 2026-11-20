"""Synthetic MIME parsing for the Docker smoke fixture; no Django, Docker or SMTP needed."""
from email.message import EmailMessage
import re
import unittest

from tools.test_server_package import console_email_messages


def console_output(*, multipart=True):
    message = EmailMessage()
    message.set_content('Your University Command Center sign-up code is 012345\n')
    if multipart:
        message.add_alternative('<p>Your University Command Center sign-up code is 012345</p>', subtype='html')
    message['Subject'] = '012345 is your University Command Center code'
    message['From'] = 'synthetic-sender@example.invalid'
    message['To'] = 'synthetic.student@example.invalid'
    return 'Synthetic console startup line\n' + message.as_string() + '\n' + '-' * 79 + '\n'


class ConsoleEmailFixtureTests(unittest.TestCase):
    def test_multipart_and_legacy_plain_messages_keep_one_plain_code(self):
        for multipart in (False, True):
            with self.subTest(multipart=multipart):
                output = console_output(multipart=multipart)
                # The former raw regex double-counted the code in HTML alternatives.
                self.assertEqual(len(re.findall(r'sign-up code is (\d{6})', output)), 2 if multipart else 1)
                messages = console_email_messages(output)
                self.assertEqual(len(messages), 1)
                self.assertEqual(str(messages[0]['To']), 'synthetic.student@example.invalid')
                plain = messages[0].get_body(preferencelist=('plain',))
                self.assertIsNotNone(plain)
                self.assertEqual(re.findall(r'sign-up code is (\d{6})', plain.get_content()), ['012345'])

    def test_duplicate_messages_are_not_deduplicated_even_when_the_code_matches(self):
        one = console_output()
        messages = console_email_messages(one + one)
        self.assertEqual(len(messages), 2)
        self.assertEqual([re.findall(r'sign-up code is (\d{6})', m.get_body(('plain',)).get_content())
                          for m in messages], [['012345'], ['012345']])

    def test_incomplete_messages_and_noise_do_not_masquerade_as_delivery(self):
        self.assertEqual(console_email_messages('noise: sign-up code is 012345\n'), [])
        self.assertEqual(console_email_messages(console_output().rsplit('-' * 79, 1)[0]), [])
