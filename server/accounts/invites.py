"""One-use sign-up invitations (launch step 3).

A code looks like ABCD-EFGH-JKMN-PQRS-TVWX: 20 characters from 30 easy-to-read letters and
digits (no 0/O, 1/I/L or U), about 98 bits of randomness. Only its SHA-256 digest is stored,
so the codes cannot be read back from the database.
"""
from datetime import timedelta
import hashlib
import secrets
from django.utils import timezone
from .models import InviteCode

ALPHABET = 'ABCDEFGHJKMNPQRSTVWXYZ23456789'
GROUPS, GROUP_SIZE = 5, 4
INVALID = 'This invite code is not valid. It may be mistyped, already used or expired. Ask for a new one.'


def new_code():
    return '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(GROUP_SIZE)) for _ in range(GROUPS))


def normalize(text):
    """Accepts any case, spaces and dashes. Returns the 20 characters, or None if malformed."""
    if not isinstance(text, str) or len(text) > 64:
        return None
    value = ''.join(text.split()).replace('-', '').upper()
    if len(value) != GROUPS * GROUP_SIZE or any(character not in ALPHABET for character in value):
        return None
    return value


def digest(normalized):
    return hashlib.sha256(normalized.encode('ascii')).hexdigest()


def create(count, days, note='', using=None):
    """Create `count` codes valid for `days` days. Returns the codes; they are never stored."""
    now = timezone.now()
    codes = [new_code() for _ in range(count)]
    InviteCode.objects.using(using).bulk_create(
        InviteCode(code_hash=digest(normalize(code)), note=note, created_at=now, expires_at=now + timedelta(days=days))
        for code in codes)
    return codes


def consume(text):
    """Mark one valid, unused, unexpired code as used. Call inside transaction.atomic(using='auth')
    with the registration, so a failure leaves the code unused. Returns True if a code was used."""
    normalized = normalize(text)
    if normalized is None:
        return False
    now = timezone.now()
    invite = (InviteCode.objects.using('auth').select_for_update()
              .filter(code_hash=digest(normalized), used_at__isnull=True, expires_at__gt=now).first())
    if invite is None:
        return False
    InviteCode.objects.using('auth').filter(pk=invite.pk).update(used_at=now)
    return True
