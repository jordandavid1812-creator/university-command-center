"""S0-02A trusted-device primitives. DORMANT: not used by login until S0-02B is approved.

Design: docs/security/S1_PROPOSALS.md section A. A trusted device NEVER authenticates
a student; in S0-02B it may only select which throttle limits apply. The password is
always verified by the unchanged StudentBackend.

Security properties:
- Identifiers are 256-bit values from `secrets`; only a domain-separated SHA-256
  digest is stored. A database reader cannot reconstruct a usable cookie.
- Cookies are additionally signed (purpose salt, SECRET_KEY + SECRET_KEY_FALLBACKS,
  30-day max age) so junk is rejected before any database access.
- Records are bound to one account through an HMAC of the normalized username.
- Rotation replaces the identifier on each successful use; a superseded identifier
  is honoured only inside a short grace window (concurrent tabs) and otherwise
  revokes the record (replay of a copied cookie).
- All writes go through the restricted `auth` connection, never runtime/migrator.

Lock order (deadlock-free; S0-02B must follow it):
  1. accounts_student row (SELECT ... FOR UPDATE)   -- issue, revoke_all, password change/reset
  2. accounts_trusteddevice rows                     -- issue (eviction), revoke_all, rotate
  3. accounts_loginlimit rows (S0-02B)
rotate() locks only its device row (a suffix of this order) and never takes the
Student lock, so it cannot deadlock with issue/revoke_all. revoke_all() always
takes the Student lock first, so it serializes with issuance and its DELETE sees
every device committed before it; issue() re-checks the password-derived
credential stamp under that lock, so a login verified before a password change
or reset can never create trust after it.
"""
import base64
import binascii
from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
import hmac
import re
import secrets
import unicodedata
import uuid
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import LoginLimit, Student, TrustedDevice

DEVICE_LIFETIME = timedelta(days=30)
MAX_DEVICES_PER_STUDENT = 10
ROTATION_GRACE = timedelta(seconds=60)
COOKIE_SALT = 'ucc.trusted-device.v1'
USERNAME_KEY_SALT = 'ucc.trusted-device.username.v1'
MAX_COOKIE_LENGTH = 256
ALIAS = 'auth'
_IDENTIFIER = re.compile(r'\A[A-Za-z0-9_-]{43}\Z')  # 32 random bytes, unpadded URL-safe base64


class DeviceError(ValueError):
    """A device primitive was called with an ineligible student or malformed input."""


@dataclass(frozen=True)
class Issued:
    device_id: uuid.UUID
    expires_at: object
    cookie: str = field(repr=False)


@dataclass(frozen=True)
class Check:
    """status: trusted | grace | absent | mismatch | replayed. Never an authentication result."""
    status: str
    device_id: uuid.UUID | None = None

    @property
    def selects_trusted_limits(self):
        """Only a CURRENT identifier may select the trusted-device limits in S0-02B.

        'grace' (a superseded identifier inside the 60 s window) only prevents a
        false replay revocation for a concurrent tab; for throttling it is treated
        exactly like an unfamiliar browser, so replaying a copied cookie inside the
        window gains no IP bypass and no extra guessing capacity.
        """
        return self.status == 'trusted'


@dataclass(frozen=True)
class Rotation:
    """status: rotated (new cookie) | grace (no new cookie) | absent | mismatch | replayed."""
    status: str
    device_id: uuid.UUID | None = None
    cookie: str | None = field(default=None, repr=False)


def new_identifier():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('ascii')


def identifier_digest(identifier):
    if not isinstance(identifier, str) or not _IDENTIFIER.match(identifier):
        raise DeviceError('Malformed device identifier.')
    return hashlib.sha256(f'{COOKIE_SALT}|{identifier}'.encode('ascii')).hexdigest()


def _normalized(username):
    if not isinstance(username, str) or not username or len(username) > 150:
        raise DeviceError('A username is required.')
    return unicodedata.normalize('NFKC', username).casefold()


def username_key(username):
    return salted_hmac(USERNAME_KEY_SALT, _normalized(username), algorithm='sha256').hexdigest()


def _username_matches(stored, username):
    """Accept keys made with SECRET_KEY or an explicitly configured fallback key."""
    value = _normalized(username)
    for secret in [settings.SECRET_KEY, *getattr(settings, 'SECRET_KEY_FALLBACKS', [])]:
        candidate = salted_hmac(USERNAME_KEY_SALT, value, secret=secret, algorithm='sha256').hexdigest()
        if hmac.compare_digest(candidate, stored):
            return True
    return False


def cookie_value(identifier):
    identifier_digest(identifier)  # validates format
    return signing.dumps(identifier, salt=COOKIE_SALT)


def read_cookie(value):
    """Return the identifier from a signed, unexpired cookie, or None. No database access."""
    if not isinstance(value, str) or not value or len(value) > MAX_COOKIE_LENGTH:
        return None
    try:
        identifier = signing.loads(value, salt=COOKIE_SALT, max_age=DEVICE_LIFETIME)
    except (signing.BadSignature, ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        return None
    if not isinstance(identifier, str) or not _IDENTIFIER.match(identifier):
        return None
    return identifier


def _live(now):
    return (TrustedDevice.objects.using(ALIAS)
            .filter(expires_at__gt=now, student__is_active=True))


def issue(student_id, username, *, credential_stamp, now=None):
    """Create a record for an ACTIVE student, enforcing the per-student cap atomically.

    Locks the Student row first, then verifies under that lock that:
    - `username` is exactly the student's stored username (the binding is derived
      from the record, never from the supplied string alone); and
    - `credential_stamp` (student.get_session_auth_hash() captured when the password
      was verified) still matches, so a password change/reset that committed in the
      meantime makes issuance fail instead of re-creating trust.
    """
    now = now or timezone.now()
    _normalized(username)
    if not isinstance(credential_stamp, str) or not credential_stamp:
        raise DeviceError('A credential stamp is required.')
    with transaction.atomic(using=ALIAS):
        student = (Student.objects.using(ALIAS).select_for_update()
                   .filter(pk=student_id, is_active=True).first())
        if student is None:
            raise DeviceError('Devices can only be issued to an active student.')
        if student.username != username:  # exact stored username (not a secret)
            raise DeviceError('The username does not belong to this student.')
        if not hmac.compare_digest(student.get_session_auth_hash(), credential_stamp):
            raise DeviceError('Credentials changed; device not issued.')
        key = username_key(student.username)
        devices = TrustedDevice.objects.using(ALIAS).filter(student_id=student_id)
        devices.filter(expires_at__lte=now).delete()
        live = list(devices.order_by('last_used_at', 'id').values_list('pk', flat=True))
        excess = len(live) - (MAX_DEVICES_PER_STUDENT - 1)
        if excess > 0:
            devices.filter(pk__in=live[:excess]).delete()
        identifier = new_identifier()
        record = TrustedDevice.objects.using(ALIAS).create(
            id=uuid.uuid4(), student_id=student_id, username_key=key,
            current_digest=identifier_digest(identifier), created_at=now,
            last_used_at=now, expires_at=now + DEVICE_LIFETIME)
    return Issued(record.pk, record.expires_at, cookie_value(identifier))


def _classify(record, digest, username, now):
    if record is None:
        return 'absent'
    if record.current_digest != digest:
        # Superseded identifier: a concurrent tab inside the grace window, otherwise replay.
        if record.rotated_at is not None and now - record.rotated_at <= ROTATION_GRACE:
            return 'grace' if _username_matches(record.username_key, username) else 'mismatch'
        return 'replayed'
    return 'trusted' if _username_matches(record.username_key, username) else 'mismatch'


def check(cookie, username, *, now=None):
    """Classify a presented cookie for a submitted username. Revokes a replayed record."""
    now = now or timezone.now()
    identifier = read_cookie(cookie)
    if identifier is None:
        return Check('absent')
    try:
        _normalized(username)
    except DeviceError:
        return Check('absent')
    digest = identifier_digest(identifier)
    record = _live(now).filter(Q(current_digest=digest) | Q(previous_digest=digest)).first()
    status = _classify(record, digest, username, now)
    if status == 'replayed':
        # Conditional delete: only the record that still lists this superseded digest.
        TrustedDevice.objects.using(ALIAS).filter(pk=record.pk, previous_digest=digest).delete()
    return Check(status, record.pk if record is not None and status != 'absent' else None)


def rotate(cookie, username, *, now=None):
    """After a SUCCESSFUL password check (S0-02B): replace the identifier atomically.

    The record row is locked, so two tabs presenting the same identifier are
    serialized: the first rotates and receives a new cookie; the second re-reads the
    rotated row, finds its identifier superseded within the grace window and gets
    status 'grace' with NO new cookie, so the browser keeps the first tab's cookie.
    """
    now = now or timezone.now()
    identifier = read_cookie(cookie)
    if identifier is None:
        return Rotation('absent')
    try:
        _normalized(username)
    except DeviceError:
        return Rotation('absent')
    digest = identifier_digest(identifier)
    with transaction.atomic(using=ALIAS):
        record = (_live(now).select_for_update(of=('self',))
                  .filter(Q(current_digest=digest) | Q(previous_digest=digest)).first())
        status = _classify(record, digest, username, now)
        if status == 'replayed':
            TrustedDevice.objects.using(ALIAS).filter(pk=record.pk).delete()
            return Rotation('replayed', record.pk)
        if status != 'trusted':
            return Rotation(status, record.pk if record is not None and status != 'absent' else None)
        fresh = new_identifier()
        changed = TrustedDevice.objects.using(ALIAS).filter(pk=record.pk, current_digest=digest).update(
            previous_digest=digest, current_digest=identifier_digest(fresh), rotated_at=now,
            last_used_at=now, expires_at=now + DEVICE_LIFETIME)
        if changed != 1:
            # Defence in depth: another rotation won despite the lock. Never hand out a
            # cookie whose digest was not stored; the browser keeps the winner's cookie.
            return Rotation('grace', record.pk)
    return Rotation('rotated', record.pk, cookie_value(fresh))


def revoke(device_id):
    return TrustedDevice.objects.using(ALIAS).filter(pk=device_id).delete()[0]


def revoke_all(student_id):
    """Delete every device of one student (password change/reset, explicit revocation).

    Always locks the Student row first (re-entrant inside a caller's transaction that
    already holds it), so the DELETE runs after any in-flight issuance has committed
    and sees its row. Rotations hold only their device-row lock; the DELETE waits for
    them and then removes the rotated row. An explicit revocation WITHOUT a password
    change cannot stop someone who still knows the password from logging in and
    earning trust again later: compromise response must be a password reset.
    """
    with transaction.atomic(using=ALIAS):
        list(Student.objects.using(ALIAS).select_for_update().filter(pk=student_id).values_list('pk', flat=True))
        return TrustedDevice.objects.using(ALIAS).filter(student_id=student_id).delete()[0]


def _delete_expired(model, now, batch_size):
    removed = 0
    while True:
        batch = list(model.objects.using(ALIAS).filter(expires_at__lte=now)
                     .values_list('pk', flat=True)[:batch_size])
        if not batch:
            return removed
        # Re-check expiry in the DELETE so a row renewed concurrently is never removed.
        removed += model.objects.using(ALIAS).filter(pk__in=batch, expires_at__lte=now).delete()[0]
        if len(batch) < batch_size:
            return removed


def cleanup_expired(*, now=None, batch_size=1000):
    """Remove expired device records and login-limit buckets in bounded batches."""
    if type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise DeviceError('batch_size must be between 1 and 10000.')
    now = now or timezone.now()
    return {'devices': _delete_expired(TrustedDevice, now, batch_size),
            'limits': _delete_expired(LoginLimit, now, batch_size)}
