from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from urllib.parse import urlsplit
from django.core import mail
from django.core.management import call_command
from django.db import connections
from django.test import Client, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from accounts.models import AccountToken, AuthThrottle, Student
from accounts import tokens
from .base import AuthenticationCase, NEW_PASSWORD, PASSWORD


class RateAndTokenTests(AuthenticationCase):
    @override_settings(AUTH_RATE_LIMITS={'login': (2, 60)})
    def test_shared_login_limit_is_not_bypassed_with_new_session_or_forwarded_ip(self):
        for index in range(2):
            response = Client().post(reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'},
                                     HTTP_X_FORWARDED_FOR=f'192.0.2.{index}')
            self.assertEqual(response.status_code, 200)
        blocked = Client().post(reverse('accounts:login'), {'username': 'alpha', 'password': PASSWORD},
                                 HTTP_X_FORWARDED_FOR='192.0.2.200')
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Retry-After', blocked)
        self.assertEqual(AuthThrottle.objects.using('auth').count(), 1)
        self.assertNotIn('127.0.0.1', AuthThrottle.objects.using('auth').get().bucket)

    @override_settings(AUTH_RATE_LIMITS={'login': (1, 60)})
    def test_rate_window_expires_without_sleep(self):
        self.login(password='wrong')
        self.assertEqual(self.login().status_code, 429)
        AuthThrottle.objects.using('default').update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.login().status_code, 302)

    @override_settings(AUTH_RATE_LIMITS={'register': (1, 60), 'reset': (1, 60), 'resend': (1, 60)})
    def test_registration_and_recovery_limits_are_shared_and_bounded(self):
        for name in ('register', 'reset', 'resend'):
            path = reverse('accounts:' + name)
            self.assertEqual(self.client.post(path, {}).status_code, 200)
            self.assertEqual(Client().post(path, {}).status_code, 429)
        self.assertEqual(AuthThrottle.objects.using('auth').count(), 3)

    @override_settings(AUTH_RATE_LIMITS={'login': (1, 60)})
    def test_concurrent_attempts_cannot_race_the_limit(self):
        def attempt(_):
            try:
                return Client().post(reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'}).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(attempt, (1, 2)))
        self.assertEqual(sorted(statuses), [200, 429])

    def issue(self, purpose='reset', email='alpha@example.invalid'):
        path = reverse('accounts:reset' if purpose == 'reset' else 'accounts:resend')
        self.client.post(path, {'email': email})
        return urlsplit(mail.outbox[-1].body.splitlines()[0]).path

    def test_new_reset_request_invalidates_earlier_link(self):
        first = self.issue()
        second = self.issue()
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.get(first).status_code, 400)
        self.assertEqual(self.client.get(second).status_code, 200)

    def test_token_purpose_cannot_be_swapped(self):
        reset = resolve(self.issue()).kwargs
        other = reverse('accounts:verify', args=[reset['selector'], reset['secret']])
        self.assertEqual(self.client.post(other).status_code, 400)

    def test_concurrent_reset_consumption_has_one_winner(self):
        link = self.issue()
        validate = tokens.valid_token
        barrier = Barrier(2)
        def synchronize(*args, **kwargs):
            barrier.wait(timeout=10)
            return validate(*args, **kwargs)
        def reset(password):
            try:
                response = Client().post(link, {'new_password1': password, 'new_password2': password})
                return response.status_code, password
            finally:
                connections.close_all()
        with patch('accounts.tokens.valid_token', side_effect=synchronize):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(reset, (NEW_PASSWORD, 'Second-Synthetic!85')))
        self.assertEqual(sorted(code for code, _ in results), [200, 400])
        winner = next(password for code, password in results if code == 200)
        student = Student.objects.using('auth').get(pk=self.a.pk)
        self.assertTrue(student.check_password(winner))
        self.assertIsNotNone(AccountToken.objects.using('auth').get().consumed_at)

    def test_failed_token_write_rolls_back_password_change(self):
        link = self.issue()
        save = AccountToken.save
        def fail_consumption(token, *args, **kwargs):
            if kwargs.get('update_fields') == ['consumed_at']:
                raise RuntimeError('Synthetic failure')
            return save(token, *args, **kwargs)
        with patch.object(AccountToken, 'save', fail_consumption):
            with self.assertRaises(RuntimeError):
                self.client.post(link, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.a.refresh_from_db(using='auth')
        self.assertTrue(self.a.check_password(PASSWORD))
        self.assertIsNone(AccountToken.objects.using('auth').get().consumed_at)

    def test_host_header_cannot_poison_email_links(self):
        self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'}, HTTP_HOST='localhost')
        self.assertTrue(mail.outbox[-1].body.startswith('http://testserver/'))
        self.assertNotIn('localhost', mail.outbox[-1].body)

    def test_cleanup_removes_expired_artifacts_without_printing_them(self):
        self.issue()
        AuthThrottle.objects.using('default').update(expires_at=timezone.now() - timedelta(seconds=1))
        AccountToken.objects.using('default').update(created_at=timezone.now() - timedelta(days=10),
                                                   expires_at=timezone.now() - timedelta(days=8))
        call_command('clear_auth_artifacts', verbosity=0)
        self.assertEqual(AuthThrottle.objects.using('auth').count(), 0)
        self.assertEqual(AccountToken.objects.using('auth').count(), 0)
