"""Trusted in-process capabilities and transaction-local PostgreSQL context.

Only verified server-side sessions may mint web capabilities.
Never construct a principal from request JSON/URL owner IDs.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import hmac
import time
import uuid
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, transaction
from accounts.models import Student
from psycopg.pq import TransactionStatus


class OwnershipRequired(ValueError):
    def __init__(self):
        super().__init__("A trusted student identity is required.")


def signing_key():
    try:
        key = bytes.fromhex(getattr(settings, "UCC_CONTEXT_SIGNING_KEY", ""))
    except ValueError:
        key = b""
    if len(key) < 32:
        raise ImproperlyConfigured("Configure a random UCC_CONTEXT_SIGNING_KEY of at least 32 bytes.")
    return key


def signature(payload):
    return hmac.new(signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class TrustedStudent:
    student_id: uuid.UUID
    expires_at: int
    proof: str = field(repr=False)
    session_key: str | None = field(default=None, repr=False)
    auth_hash: str | None = field(default=None, repr=False)


def identity_for_verified_student(principal):
    """A model instance/is_authenticated flag alone never authenticates a web principal."""
    if getattr(settings, "ALLOW_INTERNAL_TEST_PRINCIPALS", False):
        # Historical 2B fixture adapter ONLY; auth application settings disable it.
        if (not isinstance(principal, Student) or principal._state.adding
                or not isinstance(principal.pk, uuid.UUID)
                or not principal.is_authenticated or not principal.is_active):
            raise OwnershipRequired()
        expires = int(time.time()) + 300
        return TrustedStudent(principal.pk, expires, signature(f"identity|{principal.pk}|{expires}"))
    from accounts.principals import validate_principal
    student = validate_principal(principal)
    expires = min(principal.expires_at, int(time.time()) + 300)
    payload = f"identity-session|{student.pk}|{expires}|{principal.session_key}|{principal.auth_hash}"
    return TrustedStudent(student.pk, expires, signature(payload), principal.session_key, principal.auth_hash)


def require_identity(identity):
    if (not isinstance(identity, TrustedStudent) or not isinstance(identity.student_id, uuid.UUID)
            or type(identity.expires_at) is not int or identity.expires_at <= time.time()
            or not isinstance(identity.proof, str) or not identity.proof.isascii() or len(identity.proof) != 64):
        raise OwnershipRequired()
    if getattr(settings, "AUTHENTICATION_REQUIRED_FOR_CAPABILITIES", False):
        from accounts.principals import session_student
        student = session_student(identity.session_key)
        if (not student or student.pk != identity.student_id or not isinstance(identity.auth_hash, str) or not identity.auth_hash.isascii()
                or not hmac.compare_digest(student.get_session_auth_hash(), identity.auth_hash)):
            raise OwnershipRequired()
        payload = (f"identity-session|{identity.student_id}|{identity.expires_at}|"
                   f"{identity.session_key}|{identity.auth_hash}")
    elif getattr(settings, "ALLOW_INTERNAL_TEST_PRINCIPALS", False):
        payload = f"identity|{identity.student_id}|{identity.expires_at}"
    else:
        raise OwnershipRequired()
    if not hmac.compare_digest(identity.proof, signature(payload)):
        raise OwnershipRequired()
    return identity.student_id


def database_alias():
    return getattr(settings, "STUDENT_DB_ALIAS", "default")


def require_runtime_role(connection):
    """Fail closed if an operator accidentally connects a service as a privileged role."""
    from accounts.boundary import maintain_anywhere_sql, runtime_support_violation_sql
    with connection.cursor() as cursor:
        # Bandit B608 false positive below: only module-constant identifiers are interpolated.
        cursor.execute("""
            SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole
                   OR r.rolinherit OR NOT r.rolcanlogin
                   OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                   OR EXISTS (SELECT 1 FROM pg_class WHERE relname IN
                       ('academics_semester','academics_course','academics_assignment','academics_studymaterial','academics_materialfile','academics_studentprofile',
                       'academics_studyairequest','academics_studyairesult','academics_materialtext','academics_classsession') AND relowner=r.oid)
                   -- Grants configure_runtime never gives: TRUNCATE/REFERENCES/TRIGGER anywhere
                   -- academic, and any UPDATE on stored files (they are never edited).
                   OR EXISTS (SELECT 1 FROM unnest(ARRAY['academics_semester','academics_course','academics_assignment','academics_studymaterial','academics_materialfile','academics_studentprofile',
                       'academics_studyairequest','academics_studyairesult','academics_materialtext','academics_classsession']) AS t(name)
                       WHERE has_table_privilege(current_user, to_regclass('public.' || t.name),
                                                 'TRUNCATE, REFERENCES, TRIGGER'))
                   OR COALESCE(has_any_column_privilege(current_user,
                       to_regclass('public.academics_materialfile'), 'UPDATE'), false)
                   -- Search text is saved once and never edited either.
                   OR COALESCE(has_any_column_privilege(current_user,
                       to_regclass('public.academics_materialtext'), 'UPDATE'), false)
                   -- Profiles are edited, never deleted.
                   OR COALESCE(has_table_privilege(current_user,
                       to_regclass('public.academics_studentprofile'), 'DELETE'), false)
                   -- AI results are never edited; the AI ledger is never deleted, and only
                   -- its status, error category, status class and update time may change.
                   OR COALESCE(has_any_column_privilege(current_user,
                       to_regclass('public.academics_studyairesult'), 'UPDATE'), false)
                   OR COALESCE(has_table_privilege(current_user,
                       to_regclass('public.academics_studyairequest'), 'DELETE'), false)
                   OR EXISTS (SELECT 1 FROM pg_attribute a
                       WHERE a.attrelid = to_regclass('public.academics_studyairequest')
                         AND a.attnum > 0 AND NOT a.attisdropped
                         AND a.attname NOT IN ('status', 'error_category', 'status_class', 'updated_at')
                         AND has_column_privilege(current_user, a.attrelid, a.attnum, 'UPDATE'))
                   OR has_any_column_privilege(current_user, 'public.accounts_student', 'SELECT')
                   -- S0-02A: no access to device/login-limit records; never PG17 MAINTAIN anywhere.
                   OR {support}
                   OR {maintain}
                   OR has_schema_privilege(current_user, 'public', 'CREATE')
                   OR has_database_privilege(current_user, current_database(), 'CREATE')
                   OR has_database_privilege(current_user, current_database(), 'TEMP')
            FROM pg_roles r WHERE rolname=current_user
        """.format(support=runtime_support_violation_sql(connection),  # nosec B608
                   maintain=maintain_anywhere_sql(connection)))
        if cursor.fetchone() != (False,):
            raise ImproperlyConfigured("Student services require a restricted runtime database role.")
        cursor.execute("""
            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname IN
            ('academics_semester','academics_course','academics_assignment','academics_studymaterial','academics_materialfile','academics_studentprofile',
                       'academics_studyairequest','academics_studyairesult','academics_materialtext','academics_classsession')
            AND c.relrowsecurity AND c.relforcerowsecurity
        """)
        if cursor.fetchone()[0] != 10:
            raise ImproperlyConfigured("All academic tables must have forced RLS enabled.")


_current = ContextVar("ucc_student_transaction", default=None)


@contextmanager
def student_transaction(identity):
    """An atomic unit for one student; nested services use rollback savepoints."""
    owner = require_identity(identity)
    alias = database_alias()
    connection = connections[alias]
    active = _current.get()
    if active is not None:
        if active != (owner, connection) or not connection.in_atomic_block:
            raise OwnershipRequired()
        with transaction.atomic(using=alias):
            yield
        return
    # Reject unknown outer transactions: their lifetime/context is not controlled here.
    if (connection.in_atomic_block or not connection.get_autocommit()
            or connection.connection.info.transaction_status != TransactionStatus.IDLE):
        raise OwnershipRequired()
    token = _current.set((owner, connection))
    try:
        with transaction.atomic(using=alias):
            require_runtime_role(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_current_xact_id()::text, pg_backend_pid()::text")
                xid, pid = cursor.fetchone()
                proof = signature(f"transaction|{owner}|{xid}|{pid}")
                cursor.execute("SELECT set_config('ucc.student_id', %s, true), set_config('ucc.student_signature', %s, true)",
                               [str(owner), proof])
                cursor.execute("SELECT ucc_security.current_student()")
                if cursor.fetchone()[0] != owner:
                    raise OwnershipRequired()
            yield
    finally:
        _current.reset(token)
