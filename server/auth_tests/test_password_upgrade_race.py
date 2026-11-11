"""F04b: a stale login must never overwrite a newer password or create a session after a
credential change. Real separate auth/runtime/migrator LOGIN roles on PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from unittest.mock import patch
from urllib.parse import urlsplit
from django.contrib.auth import HASH_SESSION_KEY
from django.contrib.auth.hashers import PBKDF2PasswordHasher, check_password as verify_only
from django.core import mail
from django.db import connections
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from accounts.models import Student
from .base import AuthenticationCase, NEW_PASSWORD, PASSWORD

UPGRADE_HASHERS = ['django.contrib.auth.hashers.PBKDF2PasswordHasher']


@contextmanager
def interleave(action, *, after_verify=False):
    """Run `action` (a committed credential change) once, around the FIRST password verification.

    Deterministically reproduces: login loads the account row -> another request changes the
    password and commits -> login verifies against its stale row (or: login verifies first,
    then the change commits before the session is created).
    """
    real = PBKDF2PasswordHasher.verify
    state = {'done': False}

    def verify(self, password, encoded):
        if state['done']:
            return real(self, password, encoded)
        state['done'] = True
        if not after_verify:
            action()
        result = real(self, password, encoded)
        if after_verify:
            action()
        return result
    with patch.object(PBKDF2PasswordHasher, 'verify', verify):
        yield state
    assert state['done'], 'interleaved credential change never ran'


@override_settings(PASSWORD_HASHERS=UPGRADE_HASHERS)
class PasswordUpgradeRaceTests(AuthenticationCase):
    def setUp(self):
        super().setUp()
        self.weaken()

    def weaken(self, username='alpha', password=PASSWORD):
        hasher = PBKDF2PasswordHasher()
        weak = hasher.encode(password, hasher.salt(), iterations=1000)  # requires an upgrade
        Student.objects.using('default').filter(username=username).update(password=weak)

    def stored(self, username='alpha'):
        return Student.objects.using('default').get(username=username).password

    def valid(self, password, username='alpha'):
        return verify_only(password, self.stored(username))  # no setter: never mutates

    def reset_link(self):
        self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        return urlsplit(mail.outbox[-1].body.splitlines()[0]).path

    def complete_reset(self, link):
        def action():
            response = Client(REMOTE_ADDR='10.9.0.1').post(
                link, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
            assert response.status_code == 200 and b'Password changed' in response.content
            assert verify_only(NEW_PASSWORD, self.stored()), 'reset did not take effect'
        return action

    def assert_unauthenticated(self, client):
        response = client.get(reverse('accounts:password-change'))
        self.assertRedirects(response, reverse('accounts:login'), fetch_redirect_response=False)

    def assert_reset_survived(self):
        self.assertTrue(self.valid(NEW_PASSWORD), 'new password must remain valid')
        self.assertFalse(self.valid(PASSWORD), 'old password must remain invalid')

    def test_normal_login_still_upgrades_a_weak_hash(self):
        self.assertTrue(self.stored().startswith('pbkdf2_sha256$1000$'))
        self.assertEqual(self.login().status_code, 302)
        iterations = int(self.stored().split('$')[1])
        self.assertEqual(iterations, PBKDF2PasswordHasher.iterations)
        self.assertTrue(self.valid(PASSWORD))

    def test_reset_committed_before_verification_is_not_overwritten(self):
        link = self.reset_link()
        client = Client(REMOTE_ADDR='10.9.0.2')
        with interleave(self.complete_reset(link)):
            response = self.login(client)
        self.assert_reset_survived()
        self.assertEqual(response.status_code, 200)  # generic invalid-login form, no session
        self.assert_unauthenticated(client)
        self.assertEqual(self.login(Client(REMOTE_ADDR='10.9.0.3'), password=NEW_PASSWORD).status_code, 302)

    def test_reset_committed_after_verification_is_not_overwritten_and_creates_no_session(self):
        link = self.reset_link()
        client = Client(REMOTE_ADDR='10.9.0.4')
        with interleave(self.complete_reset(link), after_verify=True):
            response = self.login(client)
        self.assert_reset_survived()
        self.assertEqual(response.status_code, 200)
        self.assert_unauthenticated(client)

    def test_stale_verification_without_upgrade_creates_no_session(self):
        Student.objects.using('default').filter(username='alpha').update(
            password=PBKDF2PasswordHasher().encode(PASSWORD, PBKDF2PasswordHasher().salt()))
        link = self.reset_link()
        client = Client(REMOTE_ADDR='10.9.0.5')
        with interleave(self.complete_reset(link), after_verify=True):
            response = self.login(client)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', client.session)
        self.assert_reset_survived()

    def change_during_login(self, after_verify):
        owner = Client(REMOTE_ADDR='10.9.0.6')
        self.assertEqual(self.login(owner).status_code, 302)
        self.weaken()  # the owner's login upgraded the hash; the racing login needs one again
        # Keep the owner's session valid for the weak hash (as if they had logged in while it
        # was current); otherwise the change view would just redirect to login.
        session = owner.session
        session[HASH_SESSION_KEY] = Student.objects.using('auth').get(username='alpha').get_session_auth_hash()
        session.save()

        def change():
            response = owner.post(reverse('accounts:password-change'), {
                'old_password': PASSWORD, 'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
            assert response.status_code == 302, response.status_code
            assert verify_only(NEW_PASSWORD, self.stored()), 'password change did not take effect'
        attacker = Client(REMOTE_ADDR='10.9.0.7')
        with interleave(change, after_verify=after_verify):
            response = self.login(attacker)
        self.assert_reset_survived()
        self.assertEqual(response.status_code, 200)
        self.assert_unauthenticated(attacker)

    def test_password_change_before_verification_is_not_overwritten(self):
        self.change_during_login(after_verify=False)

    def test_password_change_after_verification_is_not_overwritten(self):
        self.change_during_login(after_verify=True)

    def test_real_concurrent_logins_and_reset_leave_only_the_new_password(self):
        link = self.reset_link()
        barrier = Barrier(7)

        def login(index):
            client = Client(REMOTE_ADDR=f'10.8.0.{index + 1}')
            try:
                barrier.wait()
                return client, client.post(reverse('accounts:login'),
                                           {'username': 'alpha', 'password': PASSWORD}).status_code
            finally:
                connections.close_all()

        def reset():
            try:
                barrier.wait()
                return Client(REMOTE_ADDR='10.8.1.1').post(
                    link, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=7) as executor:
            logins = [executor.submit(login, index) for index in range(6)]
            reset_status = executor.submit(reset).result(timeout=120)
            results = [future.result(timeout=120) for future in logins]
        self.assertEqual(reset_status, 200)
        self.assert_reset_survived()
        for client, status in results:
            self.assertIn(status, (200, 302))
            self.assert_unauthenticated(client)  # sessions from before the reset are invalid too

    def test_concurrent_logins_with_a_weak_hash_all_succeed_and_upgrade_once(self):
        barrier = Barrier(5)

        def login(index):
            try:
                barrier.wait()
                return Client(REMOTE_ADDR=f'10.7.0.{index + 1}').post(
                    reverse('accounts:login'), {'username': 'alpha', 'password': PASSWORD}).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=5) as executor:
            statuses = list(executor.map(login, range(5)))
        self.assertEqual(statuses, [302] * 5)
        self.assertEqual(int(self.stored().split('$')[1]), PBKDF2PasswordHasher.iterations)
        self.assertTrue(self.valid(PASSWORD))

    def test_wrong_password_and_role_boundaries_unchanged(self):
        before = self.stored()
        self.assertEqual(self.login(password='wrong-password-x').status_code, 200)
        self.assertEqual(self.stored(), before)  # a failed login never rewrites the hash
        with CaptureQueriesContext(connections['default']) as migrator:
            self.assertEqual(self.login().status_code, 302)
        self.assertEqual(len(migrator), 0)
