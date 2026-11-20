"""Self-reported editable names, separate from login identity, using restricted roles."""
from django.db import connections, DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from accounts.models import Student
from academics import services
from .base import WebsiteCase
from auth_tests.base import PASSWORD


class FullNameTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.url = reverse('student_web:full-name')

    def save(self, name, previous='', **extra):
        return self.client_a.post(self.url, dict(full_name=name, previous_name=previous, **extra))

    def account(self):
        return Student.objects.using('default').get(pk=self.a.pk)

    def test_optional_full_name_is_separate_on_registration(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertContains(page, 'name="full_name"')
        self.assertContains(page, 'name="username"')
        self.assertNotContains(page, 'name="matric_number"')
        from accounts.forms import RegistrationForm
        self.assertFalse(RegistrationForm().fields['full_name'].required)

    def test_registration_saves_unicode_name_without_changing_verification(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'new.synthetic', 'email': 'new@example.invalid', 'full_name': 'Ọlá O’Connor 王',
            'password1': PASSWORD, 'password2': PASSWORD})
        self.assertEqual(response.status_code, 200)
        student = Student.objects.using('default').get(username='new.synthetic')
        self.assertEqual(student.full_name, 'Ọlá O’Connor 王')
        self.assertIsNone(student.email_verified_at)
        self.assertTrue(student.check_password(PASSWORD))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signed_out_and_unverified_users_cannot_edit_names(self):
        self.assertRedirects(self.client.get(self.url), reverse('accounts:login'), fetch_redirect_response=False)
        unverified = self.make_student('unverified', verified=False)
        client = Client(); client.force_login(unverified, backend='accounts.backends.StudentBackend')
        self.assertEqual(client.post(self.url, {'full_name': 'Not allowed'}).status_code, 302)
        self.assertEqual(Student.objects.using('default').get(pk=unverified.pk).full_name, '')

    def test_existing_user_edits_and_clears_name_without_changing_session_or_credentials(self):
        before = self.account()
        key = self.client_a.session.session_key
        self.assertEqual(self.save('  Ada   Ọlá  ').status_code, 302)
        after = self.account()
        self.assertEqual(after.full_name, 'Ada Ọlá')
        for field in ('id','username','email','email_verified_at','password','is_active'):
            self.assertEqual(getattr(before,field),getattr(after,field))
        self.assertEqual(self.client_a.session.session_key, key)
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, 'Ada Ọlá')
        self.assertNotContains(page, 'Your matric number is partly hidden here.')
        self.assertEqual(self.save('', previous='Ada Ọlá').status_code, 302)
        self.assertEqual(self.account().full_name, '')

    def test_foreign_owner_and_account_fields_are_rejected(self):
        for field,value in (('owner_id', str(self.b.pk)), ('student_id', str(self.b.pk)),
                            ('username','bravo'), ('email','bravo@example.invalid')):
            with self.subTest(field=field):
                self.assertEqual(self.save('Injected', **{field:value}).status_code,400)
        self.assertEqual(self.account().full_name,'')
        self.assertEqual(Student.objects.using('default').get(pk=self.b.pk).full_name,'')

    def test_account_disappearing_after_identity_validation_denies_cleanly(self):
        from unittest.mock import patch
        from django.db.models.query import QuerySet
        # Simulate the row disappearing at the lock read, after the outer session check.
        # Real authorization/DB paths still run; no other account is substituted.
        with patch.object(QuerySet, 'select_for_update', lambda records, *a, **kw: records.none()):
            response = self.client_a.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, 'name="full_name"', status_code=403)
        self.assertEqual(self.account().full_name, '')

    def test_stale_form_does_not_overwrite_changed_name(self):
        self.assertEqual(self.save('First Name').status_code,302)
        self.assertEqual(self.save('Stale Name').status_code,409)
        self.assertEqual(self.account().full_name,'First Name')
        self.assertContains(self.client_a.get(reverse('student_web:dashboard')), 'Welcome back, First Name.')

    def test_unicode_and_escaping_with_bounded_input(self):
        for bad in ('x'*151,'Ada\nSecret','Ada\x00B','Ada\x7fB'):
            with self.subTest(bad=bad):self.assertEqual(self.save(bad).status_code,400)
        self.assertEqual(self.save('<script>alert(1)</script>').status_code,302)
        page=self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(page,'<script>alert(1)</script>')

    def test_post_requires_csrf_and_forms_work_without_javascript(self):
        page=self.client_a.get(self.url)
        self.assertIn('no-store', page['Cache-Control'])
        self.assertContains(page,'method="post"')
        self.assertContains(page,'name="csrfmiddlewaretoken"')
        client=Client(enforce_csrf_checks=True);client.cookies=self.client_a.cookies.copy()
        self.assertEqual(client.post(self.url,{'full_name':'No CSRF','previous_name':''}).status_code,403)
        self.assertEqual(self.account().full_name,'')

    def test_export_is_owner_only_and_has_full_name_without_matric(self):
        self.save('Alpha Full Name')
        services.profiles.create(self.identity_a,display_name='A nickname')
        data=self.client_a.get(reverse('student_web:data-export')).json()
        self.assertEqual(data['account']['full_name'],'Alpha Full Name')
        self.assertNotIn('matric_number',data['profile'])
        self.assertNotContains(self.client_b.get(self.url),'Alpha Full Name')
        self.assertNotContains(self.client_b.get(reverse('student_web:data-export')),'Alpha Full Name')

    def test_runtime_cannot_read_or_change_full_name(self):
        for statement in ('SELECT full_name FROM accounts_student', "UPDATE accounts_student SET full_name='No'"):
            with self.subTest(statement=statement), self.assertRaises(DatabaseError), transaction.atomic(using='runtime'):
                with connections['runtime'].cursor() as cursor:cursor.execute(statement)

    def test_database_rejects_unsafe_name_values_even_without_forms(self):
        self.assertEqual(Student.objects.using('default').filter(pk=self.a.pk).update(full_name='Valid Name'), 1)
        for bad in (' padded', 'Ada\x01Hidden', 'Ada\x85Hidden', 'x'*151):
            with self.subTest(bad=bad), self.assertRaises(DatabaseError), transaction.atomic(using='default'):
                Student.objects.using('default').filter(pk=self.a.pk).update(full_name=bad)
        self.assertEqual(self.account().full_name, 'Valid Name')

    def test_missing_name_update_grant_fails_closed_without_changing_account(self):
        from psycopg import sql
        role = connections['auth'].settings_dict['USER']
        with connections['default'].cursor() as cursor:
            cursor.execute(sql.SQL('REVOKE UPDATE(full_name) ON accounts_student FROM {}').format(sql.Identifier(role)))
        try:
            self.assertEqual(self.save('Must Not Persist').status_code, 503)
            self.assertEqual(self.account().full_name, '')
            self.assertTrue(self.account().check_password(PASSWORD))
        finally:
            with connections['default'].cursor() as cursor:
                cursor.execute(sql.SQL('GRANT UPDATE(full_name) ON accounts_student TO {}').format(sql.Identifier(role)))

    def test_duplicate_signup_does_not_overwrite_existing_full_name(self):
        self.save('Existing Private Name')
        response = self.client.post(reverse('accounts:register'), {'username': 'alpha',
            'email': 'alpha@example.invalid', 'full_name': 'Injected Replacement',
            'password1': PASSWORD, 'password2': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Existing Private Name')
        self.assertEqual(self.account().full_name, 'Existing Private Name')

    def test_legacy_column_retained_but_matric_collection_is_rejected(self):
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_attribute WHERE attrelid='academics_studentprofile'::regclass AND attname='matric_number' AND NOT attisdropped")
            self.assertEqual(cursor.fetchone(),(1,))
        with self.assertRaises(services.InvalidRecord):
            services.profiles.create(self.identity_a,matric_number='NO-LONGER-ACCEPTED')

    def test_registration_rejects_invalid_name_without_creating_account(self):
        for name in ('x'*151,'Synthetic\nHidden'):
            response=self.client.post(reverse('accounts:register'),{'username':'not.created',
                'email':'not-created@example.invalid','full_name':name,'password1':PASSWORD,'password2':PASSWORD})
            self.assertEqual(response.status_code,200)
            self.assertFalse(Student.objects.using('default').filter(username='not.created').exists())
