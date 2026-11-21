"""Email sign-up codes for the public site (owner's choice: open sign-up, 5-minute codes).

Registering creates an unverified account and emails a 6-digit code. Entering it within
LIFETIME verifies the email; a code allows MAX_ATTEMPTS tries, and asking for a new code
retires the old one (tokens.request_email sends it). Codes are stored only as an HMAC keyed with the site's secret key, so a copy
of the database cannot be used to work them out. Every answer is generic, so these pages never
reveal whether an email or username has an account.
"""
from datetime import timedelta
import secrets
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from .models import SignupCode, Student

LIFETIME = timedelta(minutes=5)  # owner's choice: time to find the email, even in Spam
MAX_ATTEMPTS = 5
DIGITS = 6


def _digest(student_id, code):
    return salted_hmac('accounts.signup_codes', f'{student_id}:{code}', algorithm='sha256').hexdigest()


def clean_code(text):
    """The 6 digits, allowing spaces (as some phones copy them); otherwise None."""
    value = ''.join(str(text or '').split())
    return value if len(value) == DIGITS and value.isascii() and value.isdigit() else None


def issue_locked(student):
    """Inside transaction.atomic(using='auth') with the Student row locked: retire earlier codes,
    store a new one and email it after commit."""
    from .tokens import _deliver
    now = timezone.now()
    SignupCode.objects.using('auth').filter(student=student, consumed_at__isnull=True).update(consumed_at=now)
    code = f'{secrets.randbelow(10 ** DIGITS):0{DIGITS}d}'
    SignupCode.objects.using('auth').create(student=student, digest=_digest(student.pk, code), created_at=now,
                                            expires_at=now + LIFETIME)
    origin = settings.AUTH_LINK_ORIGIN.rstrip('/')
    text = (f'Your UniCommand sign-up code is {code}\n\n'
            f'It works for 5 minutes. Enter it on the page that opened after you registered,\n'
            f'or at {origin}/accounts/verify/code/ (you can ask for a new code there).')
    transaction.on_commit(lambda: _deliver(f'{code} is your UniCommand code', text, student.email,
                                           code=code, action_url=f'{origin}/accounts/verify/code/'),
                          using='auth')


def _pending(email, lock):
    students = Student.objects.using('auth')
    if lock:
        students = students.select_for_update()
    return students.filter(email=email, is_active=True, email_verified_at__isnull=True).first()


def verify(email, text):
    """True if `text` is the newest unexpired code for this unverified email. Wrong guesses count."""
    code = clean_code(text)
    if code is None:
        return False
    with transaction.atomic(using='auth'):
        student = _pending(email, lock=True)  # Student before code, like every other token path
        if student is None:
            return False
        record = (SignupCode.objects.using('auth').select_for_update()
                  .filter(student=student, consumed_at__isnull=True, new_email__isnull=True)
                  .order_by('-created_at').first())
        now = timezone.now()
        if record is None or record.expires_at <= now or record.attempts >= MAX_ATTEMPTS:
            return False
        if not constant_time_compare(record.digest, _digest(student.pk, code)):
            record.attempts += 1
            record.save(using='auth', update_fields=['attempts'])
            return False
        student.email_verified_at = now
        student.save(using='auth', update_fields=['email_verified_at', 'updated_at'])
        record.consumed_at = now
        record.save(using='auth', update_fields=['consumed_at'])
        return True


def _stale(student):
    record = (SignupCode.objects.using('auth').filter(student=student, consumed_at__isnull=True, new_email__isnull=True)
              .order_by('-created_at').first())
    return record is None or record.expires_at <= timezone.now() or record.attempts >= MAX_ATTEMPTS


def needs_new_code(email):
    """Read-only, before a code is checked: True if this unverified email has no usable code left."""
    student = _pending(email, lock=False)
    return student is not None and _stale(student)


def renew_if_stale(email, allowed):
    """After a failed code: if this unverified email's newest code has expired or used up its tries
    (or none is open), email a fresh one, so a student is never stuck (owner's choice). `allowed()`
    is asked only then, so ordinary wrong guesses do not use up the resend limit. Returns nothing:
    the reply is the same for every email, so it never reveals whether an account exists."""
    with transaction.atomic(using='auth'):
        student = _pending(email, lock=True)  # Student before code, like every other token path
        if student is None:
            return
        if _stale(student) and student.has_usable_password() and allowed():
            issue_locked(student)

