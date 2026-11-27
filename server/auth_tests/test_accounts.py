from datetime import timedelta
import hashlib
import re
from urllib.parse import urlsplit
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from accounts.models import AccountToken, Student
from .base import AuthenticationCase, NEW_PASSWORD, PASSWORD


class AccountFlowTests(AuthenticationCase):
    def registration(self, **changes):
        values = {'username': 'new-student', 'email': 'new@example.invalid',
                  'password1': PASSWORD, 'password2': PASSWORD}
        values.update(changes)
        return self.client.post(reverse('accounts:register'), values)

    def link(self):
        return urlsplit(mail.outbox[-1].body.splitlines()[0]).path

    def issue_reset(self, email='alpha@example.invalid'):
        response = self.client.post(reverse('accounts:reset'), {'email': email})
        self.assertEqual(response.status_code, 200)
        return self.link()

    def test_valid_registration_stores_hash_and_requires_verification(self):
        self.assertEqual(self.registration().status_code, 200)
        student = Student.objects.using('auth').get(username='new-student')
        self.assertNotEqual(student.password, PASSWORD)
        self.assertTrue(student.check_password(PASSWORD))
        self.assertIsNone(student.email_verified_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.login(username='new-student').status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client_a.session)
        self.assertEqual(self.client.get(self.link()).status_code, 200)
        self.assertIsNone(AccountToken.objects.using('auth').get(student=student).consumed_at)
        self.assertEqual(self.client.post(self.link()).status_code, 200)
        student.refresh_from_db(using='auth')
        self.assertIsNotNone(student.email_verified_at)
        self.assertEqual(self.login(username='new-student').status_code, 302)

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_registration_uses_supported_django_password_hasher(self):
        self.registration()
        student = Student.objects.using('auth').get(username='new-student')
        self.assertTrue(student.password.startswith('pbkdf2_sha256$'))
        self.assertTrue(student.check_password(PASSWORD))

    def test_verification_secret_is_not_stored_in_database(self):
        self.registration()
        details = resolve(self.link()).kwargs
        token = AccountToken.objects.using('auth').get(pk=details['selector'])
        self.assertEqual(token.digest, hashlib.sha256(details['secret'].encode()).hexdigest())
        for field in token._meta.fields:
            self.assertNotEqual(str(getattr(token, field.attname)), details['secret'])
        self.assertEqual(mail.outbox[0].to, ['new@example.invalid'])

    def test_duplicate_username_and_email_get_same_generic_response(self):
        # Owner's choice: a taken username is now reported on the form; a taken email still gets
        # the same generic response as success.
        one = self.registration()
        mail.outbox.clear()
        taken = self.registration(username='new-student', email='different@example.invalid')
        self.assertContains(taken, 'That username is already taken')
        response = self.registration(username='different', email='NEW@example.invalid')
        self.assertEqual((response.status_code, response.content), (one.status_code, one.content))
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Student.objects.using('auth').count(), 3)

    def test_invalid_and_mismatched_passwords_do_not_create_accounts(self):
        for changes in ({'password1': 'short', 'password2': 'short'},
                        {'password1': '1234567890', 'password2': '1234567890'},
                        {'password2': 'Mismatch!83'},
                        {'password1': 'x' * 129, 'password2': 'x' * 129}):
            self.assertEqual(self.registration(**changes).status_code, 200)
        self.assertFalse(Student.objects.using('auth').filter(username='new-student').exists())
        self.assertEqual(mail.outbox, [])

    def test_identifier_policy_and_email_normalization(self):
        self.registration(username='CaseSensitive', email='Mixed@EXAMPLE.INVALID')
        student = Student.objects.using('auth').get(username='CaseSensitive')
        self.assertEqual(student.email, 'mixed@example.invalid')
        self.client.post(self.link())
        self.assertEqual(self.login(username='casesensitive').status_code, 200)
        self.assertEqual(self.login(username='CaseSensitive').status_code, 302)

    def test_invalid_registration_identifiers_are_rejected(self):
        for values in ({'username': 'x'}, {'username': 'école'}, {'email': 'invalid'}, {'email': 'é@example.invalid'}):
            self.registration(**values)
        self.assertEqual(Student.objects.using('auth').count(), 2)

    def test_verification_expiry_reuse_and_invalid_secret(self):
        self.registration()
        link = self.link()
        detail = resolve(link).kwargs
        invalid = reverse('accounts:verify', args=[detail['selector'], 'x' * 43])
        self.assertEqual(self.client.post(invalid).status_code, 400)
        self.assertEqual(self.client.post(link).status_code, 200)
        self.assertEqual(self.client.post(link).status_code, 400)
        self.registration(username='expired-user', email='expired@example.invalid')
        expired = self.link()
        AccountToken.objects.using('default').filter(pk=resolve(expired).kwargs['selector']).update(
            created_at=timezone.now() - timedelta(days=3), expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.client.post(expired).status_code, 400)

    def test_resend_invalidates_prior_verification_link(self):
        self.registration()
        first = self.link()
        self.client.post(reverse('accounts:resend'), {'email': 'new@example.invalid'})
        second = self.link()
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.post(first).status_code, 400)
        self.assertEqual(self.client.post(second).status_code, 200)

    def test_correct_and_incorrect_login_use_generic_failure(self):
        incorrect = self.login(password='incorrect')
        absent = self.login(username='does-not-exist')
        pending = self.make_student('pending', verified=False)
        unverified = self.login(username=pending.username)
        self.assertEqual((incorrect.status_code, absent.status_code, unverified.status_code), (200, 200, 200))
        self.assertEqual(incorrect.context['form'].non_field_errors(), absent.context['form'].non_field_errors())
        self.assertEqual(absent.context['form'].non_field_errors(), unverified.context['form'].non_field_errors())
        self.assertNotIn(SESSION_KEY, self.client_a.session)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client_a.session[SESSION_KEY], str(self.a.pk))

    def test_login_ignores_open_redirect_destinations(self):
        response = self.client_a.post(reverse('accounts:login') + '?next=https://evil.invalid/',
                                      {'username': 'alpha', 'password': PASSWORD})
        self.assertRedirects(response, reverse('accounts:academic'), fetch_redirect_response=False)

    def test_session_fixation_resistance(self):
        anonymous = self.client_a.session
        anonymous['before-login'] = 'synthetic'
        anonymous.save()
        old = anonymous.session_key
        self.assertEqual(self.login().status_code, 302)
        self.assertNotEqual(self.client_a.session.session_key, old)
        self.assertFalse(Session.objects.using('auth').filter(session_key=old).exists())

    def test_post_logout_invalidates_session_and_get_cannot_log_out(self):
        self.login()
        old = self.client_a.session.session_key
        self.assertEqual(self.client_a.get(reverse('accounts:logout')).status_code, 405)
        self.assertEqual(self.client_a.post(reverse('accounts:logout')).status_code, 302)
        self.assertFalse(Session.objects.using('auth').filter(session_key=old).exists())
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)

    def test_session_expiry_denies_academic_access(self):
        self.login()
        key = self.client_a.session.session_key
        Session.objects.using('default').filter(session_key=key).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)

    def test_cookie_and_cache_protections(self):
        response = self.login()
        cookie = response.cookies['sessionid']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(cookie['max-age'], '')
        self.assertTrue(self.client_a.session.get_expire_at_browser_close())
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client_a.session.get_expiry_age(), 1800)
        with override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True):
            secure = self.client_b.post(reverse('accounts:login'), {'username': 'bravo', 'password': PASSWORD})
            self.assertTrue(secure.cookies['sessionid']['secure'])
            self.assertTrue(secure.cookies['csrftoken']['secure'])

    def test_password_reset_and_reuse_invalidate_existing_sessions(self):
        self.login(self.client_a)
        other = Client()
        self.login(other)
        capability = self.identity(self.client_a)
        link = self.issue_reset()
        self.assertEqual(self.client.get(link).status_code, 200)
        response = self.client.post(link, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post(link, {'new_password1': PASSWORD, 'new_password2': PASSWORD}).status_code, 400)
        from academics.ownership import OwnershipRequired, require_identity
        with self.assertRaises(OwnershipRequired):
            require_identity(capability)
        for client in (self.client_a, other):
            self.assertEqual(client.get(reverse('accounts:academic')).status_code, 302)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)
        self.assertEqual(self.login(password=NEW_PASSWORD).status_code, 302)

    def test_reset_unknown_unverified_and_known_accounts_have_same_response(self):
        self.make_student('pending', verified=False)
        responses = [self.client.post(reverse('accounts:reset'), {'email': email}) for email in
                     ('alpha@example.invalid', 'unknown@example.invalid', 'pending@example.invalid')]
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(responses[0].content, responses[1].content)
        self.assertEqual(responses[1].content, responses[2].content)

    def test_expired_reset_link_is_rejected(self):
        link = self.issue_reset()
        AccountToken.objects.using('default').filter(pk=resolve(link).kwargs['selector']).update(
            created_at=timezone.now() - timedelta(days=3), expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.client.get(link).status_code, 400)
        self.assertEqual(self.client.post(link, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}).status_code, 400)

    def test_invalid_reset_secret_and_password_leave_token_unconsumed(self):
        link = self.issue_reset()
        details = resolve(link).kwargs
        invalid = reverse('accounts:reset-confirm', args=[details['selector'], 'x' * 43])
        self.assertEqual(self.client.post(invalid).status_code, 400)
        self.assertEqual(self.client.post(link, {'new_password1': 'short', 'new_password2': 'short'}).status_code, 200)
        self.assertIsNone(AccountToken.objects.using('auth').get(pk=details['selector']).consumed_at)

    def test_password_change_logs_out_all_sessions(self):
        self.login()
        other = Client()
        self.login(other)
        response = self.client_a.post(reverse('accounts:password-change'), {
            'old_password': PASSWORD, 'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)
        self.assertEqual(other.get(reverse('accounts:academic')).status_code, 302)
        self.assertEqual(self.login(password=NEW_PASSWORD).status_code, 302)

    def test_wrong_old_password_cannot_change_account(self):
        self.login()
        response = self.client_a.post(reverse('accounts:password-change'), {
            'old_password': 'wrong', 'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db(using='auth')
        self.assertTrue(self.a.check_password(PASSWORD))

    def test_email_change_invalidates_old_email_links(self):
        link = self.issue_reset()
        Student.objects.using('default').filter(pk=self.a.pk).update(email='other@example.invalid')
        self.assertEqual(self.client.get(link).status_code, 400)

    def test_password_change_invalidates_outstanding_reset_link(self):
        link = self.issue_reset()
        self.login()
        self.client_a.post(reverse('accounts:password-change'), {
            'old_password': PASSWORD, 'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertEqual(self.client.get(link).status_code, 400)

    def test_csrf_is_required_for_authentication_state_changes(self):
        client = Client(enforce_csrf_checks=True)
        for name in ('register', 'login', 'logout', 'reset', 'resend'):
            self.assertEqual(client.post(reverse('accounts:' + name), {}).status_code, 403)
        page = client.get(reverse('accounts:login'))
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        self.assertEqual(client.post(reverse('accounts:login'), {'username': 'alpha', 'password': PASSWORD,
                                                               'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(client.post(reverse('accounts:logout')).status_code, 403)

    def test_csrf_is_required_to_consume_verification_and_reset_tokens(self):
        self.registration()
        verify = self.link()
        reset = self.issue_reset()
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(verify).status_code, 403)
        self.assertEqual(client.post(reset, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}).status_code, 403)
        self.assertTrue(AccountToken.objects.using('auth').filter(consumed_at__isnull=False).count() == 0)

    def test_deactivated_account_cannot_login_reset_or_verify(self):
        self.registration(username='pending-active', email='pending-active@example.invalid')
        link = self.link()
        Student.objects.using('default').filter(username='pending-active').update(is_active=False)
        self.assertEqual(self.client.post(link).status_code, 400)
        Student.objects.using('default').filter(pk=self.a.pk).update(is_active=False)
        self.assertEqual(self.login().status_code, 200)
        mail.outbox.clear()
        self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        self.assertEqual(mail.outbox, [])

    def test_common_password_and_client_verification_flags_are_rejected(self):
        response = self.registration(password1='password', password2='password')
        self.assertIn('too common', str(response.context['form'].errors))
        self.registration(email_verified_at='2026-01-01', is_active='true', id='forged')
        student = Student.objects.using('auth').get(username='new-student')
        self.assertIsNone(student.email_verified_at)

    def test_email_delivery_failure_keeps_recovery_response_generic(self):
        from unittest.mock import patch
        with patch('accounts.tokens.send_mail', side_effect=RuntimeError('secret provider detail')):
            with self.assertLogs('accounts.tokens', level='WARNING') as logs:
                response = self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        absent = self.client.post(reverse('accounts:reset'), {'email': 'unknown@example.invalid'})
        self.assertEqual((response.status_code, response.content), (absent.status_code, absent.content))
        self.assertNotIn('secret provider detail', str(logs.output))

    def test_password_change_requires_csrf(self):
        self.login()
        client = Client(enforce_csrf_checks=True)
        client.cookies['sessionid'] = self.client_a.cookies['sessionid'].value
        self.assertEqual(client.post(reverse('accounts:password-change'), {
            'old_password': PASSWORD, 'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}).status_code, 403)

    def test_csrf_origin_checks_accept_same_origin_and_reject_hostile_or_null(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get(reverse('accounts:login'))
        self.assertEqual(page['Referrer-Policy'], 'same-origin')
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        data = {'username': 'alpha', 'password': PASSWORD, 'csrfmiddlewaretoken': token}
        for origin in ('null', 'https://evil.invalid'):
            self.assertEqual(client.post(reverse('accounts:login'), data, HTTP_ORIGIN=origin).status_code, 403)
        self.assertEqual(client.post(reverse('accounts:login'), data, HTTP_ORIGIN='http://testserver').status_code, 302)
