# Independent final PR #26 probes

Exact eight-test source executed against `e2624428` with PostgreSQL 17.11. Copy the Python block to a private temporary directory as `final26_probes.py`. Use that directory in PYTHONPATH and run the pinned checkout with the repository AuthenticationTestRunner and ephemeral PostgreSQL test credentials:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/probe/directory PGTESTDATABASE=test_final26_independent python server/manage.py test final26_probes --settings=config.settings.auth_test -v 2
```

Synthetic disposable test databases only; the test runner requires the documented offline provisioning credentials plus separate runtime/auth LOGINs and generated context/Django keys. Do not target a real-data database. The final probe deliberately demonstrates the permitted direct-SQL generation decrease; it asserts an accurately documented limitation, not a desired application operation. Source is an appendix rather than an executable application/test change in this documentation-only PR.

```python
"""Independent synthetic PostgreSQL 17 probes for pinned PR26 e262442."""
from datetime import timedelta
import os
from unittest import TestCase
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connections, transaction, IntegrityError
from django.utils import timezone
from psycopg import sql
from accounts import devices
from accounts.boundary import require_auth_role
from academics.ownership import require_runtime_role
from accounts.models import DeviceGeneration, Student, TrustedDevice
from auth_tests.test_trusted_devices import DeviceCase

class FinalReviewProbes(DeviceCase):
    def test_case_sensitive_target_and_uuid_rotation(self):
        other=Student.objects.db_manager('default').create_user('ALPHA','Synthetic-Case-Probe!83',email='uppercase-probe@example.invalid',email_verified_at=timezone.now())
        issued=self.issue()
        self.assertEqual(devices.check(issued.cookie,'ALPHA').status,'mismatch')
        self.assertFalse(devices.check(issued.cookie,'ALPHA').selects_trusted_limits)
        self.assertEqual(devices.rotate(issued.cookie,other.pk).status,'mismatch')
        self.assertEqual(devices.check(issued.cookie,'alpha').status,'trusted')

    def test_wrong_account_previous_cookie_is_non_destructive_for_check_and_rotate(self):
        issued=self.issue()
        fresh=devices.rotate(issued.cookie,self.a.pk)
        before=self.rows().get().current_digest
        late=timezone.now()+devices.ROTATION_GRACE+timedelta(seconds=1)
        self.assertEqual(devices.check(issued.cookie,'bravo',now=late).status,'mismatch')
        self.assertEqual(devices.rotate(issued.cookie,self.b.pk,now=late).status,'mismatch')
        self.assertEqual(self.rows().get().current_digest,before)
        self.assertEqual(devices.check(fresh.cookie,'alpha',now=late).status,'trusted')
        self.assertEqual(devices.check(issued.cookie,'alpha',now=late).status,'replayed')
        self.assertFalse(self.rows().exists())

    def test_null_rotation_truth_table_rejects_both_half_pairs(self):
        now=timezone.now()
        for previous,rotated in ((None,now),('b'*64,None)):
            with self.subTest(previous_is_null=previous is None), self.assertRaises(IntegrityError):
                with transaction.atomic(using='auth'):
                    TrustedDevice.objects.using('auth').create(student_id=self.a.pk,current_digest='a'*64,
                        previous_digest=previous,rotated_at=rotated,created_at=now,last_used_at=now,
                        expires_at=now+timedelta(days=30))

    def test_pg17_maintain_is_rejected_by_both_real_logins(self):
        self.assertGreaterEqual(connections['auth'].pg_version,170000)
        for alias,role,guard in (('auth',os.environ['UCC_AUTH_ROLE'],require_auth_role),
                                ('runtime',os.environ['UCC_RUNTIME_ROLE'],lambda: require_runtime_role(connections['runtime']))):
            with self.subTest(alias=alias):
                try:
                    with connections['default'].cursor() as c:
                        c.execute(sql.SQL('GRANT MAINTAIN ON accounts_trusteddevice TO {}').format(sql.Identifier(role)))
                    with self.assertRaises(ImproperlyConfigured): guard()
                finally:
                    call_command('configure_runtime',verbosity=0)
                    call_command('configure_auth_role',verbosity=0)
                guard()

    def test_revoked_update_column_is_detected(self):
        try:
            with connections['default'].cursor() as c:
                c.execute(sql.SQL('REVOKE UPDATE(rotated_at) ON accounts_trusteddevice FROM {}').format(sql.Identifier(os.environ['UCC_AUTH_ROLE'])))
            with self.assertRaises(ImproperlyConfigured): require_auth_role()
        finally:
            call_command('configure_auth_role',verbosity=0)
        require_auth_role()

    def test_unchanged_password_cannot_issue_with_pre_revocation_generation(self):
        stamp,old=self.stamp(),devices.generation(self.a.pk)
        devices.revoke_all(self.a.pk)
        with self.assertRaises(devices.DeviceError):
            devices.issue(self.a.pk,'alpha',credential_stamp=stamp,generation=old)
        self.assertFalse(self.rows().exists())
        self.assertEqual(devices.generation(self.a.pk),old+1)
        self.issue()
        self.assertEqual(self.rows().count(),1)

    def test_revocation_rollback_preserves_original_trust_and_epoch(self):
        issued=self.issue()
        old=devices.generation(self.a.pk)
        with self.assertRaises(RuntimeError):
            with transaction.atomic(using='auth'):
                devices.revoke_all(self.a.pk)
                raise RuntimeError('synthetic rollback')
        self.assertEqual(devices.generation(self.a.pk),old)
        self.assertEqual(devices.check(issued.cookie,'alpha').status,'trusted')

    def test_generation_monotonicity_is_application_enforced_not_a_database_trigger(self):
        devices.revoke_all(self.a.pk)
        self.assertEqual(devices.generation(self.a.pk),1)
        DeviceGeneration.objects.using('auth').filter(student_id=self.a.pk).update(generation=0)
        self.assertEqual(devices.generation(self.a.pk),0)
        require_auth_role()  # ordinary permitted UPDATE cannot enforce monotonic values
```
