"""Launch step F, part 2: Settings -> Change email. The password and a 6-digit code sent to the
NEW address are both needed; the old address is told afterwards; nobody else is touched and the
page never reveals whether another account uses an address. Synthetic data, real PostgreSQL."""
import re
from urllib.parse import urlparse
from datetime import timedelta
from django.core import mail
from django.db import DatabaseError, connections, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import SignupCode, Student
from auth_tests.base import PASSWORD
from .base import WebsiteCase

NEW = 'alpha.new@example.invalid'


class EmailChangeTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()
        mail.outbox = []

    def ask(self, new_email=NEW, password=PASSWORD, client=None):
        return (client or self.client_a).post(reverse('student_web:email-change'),
                                              {'password': password, 'new_email': new_email})

    def enter(self, code, client=None):
        return (client or self.client_a).post(reverse('student_web:email-change-confirm'), {'code': code})

    def emailed_code(self):
        return re.search(r'code is (\d{6})\b', mail.outbox[-1].body).group(1)

    def email_of(self, username):
        return Student.objects.using('default').get(username=username).email

    def wrong(self, code):
        return f'{(int(code) + 1) % 1_000_000:06d}'

    def test_signed_out_visitors_are_sent_to_login(self):
        for response in (self.client.get(reverse('student_web:email-change')), self.ask(client=self.client),
                         self.enter('123456', client=self.client)):
            self.assertEqual(response.status_code, 302)

    def test_settings_links_to_a_page_that_works_without_javascript(self):
        self.assertContains(self.client_a.get(reverse('student_web:settings')),
                            f'href="{reverse("student_web:email-change")}"')
        page = self.client_a.get(reverse('student_web:email-change'))
        self.assertContains(page, 'alpha@example.invalid')
        self.assertContains(page, '<form method="post"')
        self.assertContains(page, 'name="new_email"')
        self.assertNotContains(page, '<script>')

    def test_code_goes_to_the_new_address_and_changes_the_email(self):
        self.assertContains(self.ask(NEW.upper()), 'we have sent it a 6-digit code')
        self.assertEqual(mail.outbox[-1].to, [NEW])
        code = self.emailed_code()
        self.assertEqual(self.email_of('alpha'), 'alpha@example.invalid')  # nothing changes yet
        page = self.client_a.get(reverse('student_web:email-change'))
        self.assertContains(page, 'Step 2: enter your code')
        self.assertContains(page, NEW)
        record = SignupCode.objects.using('default').get(new_email=NEW)
        self.assertNotIn(code, record.digest)
        self.assertEqual(record.expires_at - record.created_at, timedelta(minutes=10))
        response = self.enter(f'{code[:3]} {code[3:]}')
        self.assertRedirects(response, reverse('student_web:settings'), fetch_redirect_response=False)
        self.assertContains(self.client_a.get(reverse('student_web:settings')), 'Your email address was changed')
        student = Student.objects.using('default').get(username='alpha')
        self.assertEqual(student.email, NEW)
        self.assertIsNotNone(student.email_verified_at)
        self.assertEqual(mail.outbox[-1].to, ['alpha@example.invalid'])  # the old address is told
        self.assertIn('was changed', mail.outbox[-1].subject)
        self.assertEqual(self.client_a.get(reverse('student_web:dashboard')).status_code, 200)  # still signed in
        self.assertEqual(self.enter(code).status_code, 400)  # used up
        self.assertEqual(self.email_of('bravo'), 'bravo@example.invalid')

    def test_wrong_password_or_same_address_sends_nothing(self):
        self.assertContains(self.ask(password='Wrong-Passphrase-99'), 'That password is not right', status_code=400)
        self.assertContains(self.ask('alpha@example.invalid'), 'already your email', status_code=400)
        self.assertEqual(self.ask('é@example.invalid').status_code, 400)
        self.assertEqual(mail.outbox, [])
        self.assertFalse(SignupCode.objects.using('default').exists())

    def test_an_address_used_by_another_account_gets_the_same_reply_and_no_email(self):
        self.assertContains(self.ask('bravo@example.invalid'), 'we have sent it a 6-digit code')
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.email_of('alpha'), 'alpha@example.invalid')

    def test_five_wrong_tries_lock_the_code_and_a_new_code_replaces_the_old(self):
        self.ask()
        old = self.emailed_code()
        self.ask()
        new = self.emailed_code()
        if old != new:
            self.assertEqual(self.enter(old).status_code, 400)
        for _ in range(4 if old != new else 5):
            self.assertContains(self.enter(self.wrong(new)), 'wrong or has expired', status_code=400)
        self.assertContains(self.enter(new), 'wrong or has expired', status_code=400)
        self.assertEqual(self.email_of('alpha'), 'alpha@example.invalid')

    def test_code_expires_after_ten_minutes(self):
        self.ask()
        code = self.emailed_code()
        SignupCode.objects.using('default').update(created_at=timezone.now() - timedelta(minutes=11),
                                                   expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.enter(code).status_code, 400)
        self.assertEqual(self.email_of('alpha'), 'alpha@example.invalid')

    def test_a_code_works_only_for_the_account_that_asked(self):
        self.ask()
        code = self.emailed_code()
        self.assertEqual(self.enter(code, client=self.client_b).status_code, 400)
        self.assertEqual((self.email_of('alpha'), self.email_of('bravo')),
                         ('alpha@example.invalid', 'bravo@example.invalid'))

    def test_address_taken_after_the_code_was_sent_changes_nothing(self):
        self.ask()
        code = self.emailed_code()
        Student.objects.using('default').filter(username='bravo').update(email=NEW)
        self.assertEqual(self.enter(code).status_code, 400)
        self.assertEqual(self.email_of('alpha'), 'alpha@example.invalid')

    def test_old_reset_links_stop_working(self):
        self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        link = re.search(r'https?://\S+', mail.outbox[-1].body).group(0)
        self.ask()
        self.enter(self.emailed_code())
        self.assertEqual(self.client.get(urlparse(link).path).status_code, 400)

    def test_extra_fields_are_refused(self):
        response = self.client_a.post(reverse('student_web:email-change'),
                                      {'password': PASSWORD, 'new_email': NEW, 'student_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(mail.outbox, [])

    @override_settings(AUTH_RATE_LIMITS={'change-email': (2, 60), 'change-email-code': (2, 60), 'login': (10, 900)})
    def test_both_steps_are_rate_limited(self):
        self.assertEqual([self.ask(password='Wrong-Passphrase-99').status_code for _ in range(3)], [400, 400, 429])
        self.assertEqual([self.enter('000000').status_code for _ in range(3)], [400, 400, 429])

    def test_only_the_email_column_became_changeable_for_the_sign_in_login(self):
        auth = connections['auth']
        for statement in ("UPDATE accounts_student SET username='changed'", 'UPDATE accounts_student SET is_active=false',
                          'UPDATE accounts_signupcode SET new_email=NULL', "UPDATE accounts_signupcode SET digest='0'"):
            with self.subTest(statement=statement), self.assertRaises(DatabaseError), transaction.atomic(using='auth'):
                with auth.cursor() as cursor:
                    cursor.execute(statement)
        with self.assertRaises(DatabaseError), transaction.atomic(using='runtime'):
            with connections['runtime'].cursor() as cursor:
                cursor.execute("UPDATE accounts_student SET email='x@example.invalid'")
