"""Change the account's email (launch step F, part 2).

The signed-in student types their password and the new address (student_web checks the
password). A 6-digit code is emailed to the NEW address; entering it within LIFETIME replaces
the email and keeps it verified. The old address is told afterwards. Codes live in
accounts_signupcode with new_email set, stored only as an HMAC keyed with the site's secret,
5 tries, and a new code retires the old one. Earlier password-reset and verification links stop
working by themselves, because they were issued for the old address.
"""
from datetime import timedelta
import logging
import secrets
from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from .models import SignupCode, Student
from .signup_codes import DIGITS, MAX_ATTEMPTS, clean_code

LIFETIME = timedelta(minutes=10)  # time to open a different inbox


def _digest(student_id, new_email, code):
    return salted_hmac('accounts.email_change', f'{student_id}:{new_email}:{code}', algorithm='sha256').hexdigest()


def _send(subject, text, email):
    try:
        send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [email])
    except Exception:
        logging.getLogger(__name__).warning('Email-change message could not be sent.')


def _student(student_id):
    return (Student.objects.using('auth').select_for_update()
            .filter(pk=student_id, is_active=True, email_verified_at__isnull=False).first())


def request_code(student_id, new_email):
    """Email a code to new_email. If another account already uses that address, nothing is sent,
    but the caller shows the same reply, so this page cannot be used to find accounts."""
    with transaction.atomic(using='auth'):
        student = _student(student_id)  # Student before code, like every other token path
        if student is None:
            return
        now = timezone.now()
        SignupCode.objects.using('auth').filter(student=student, consumed_at__isnull=True).update(consumed_at=now)
        if Student.objects.using('auth').filter(email=new_email).exclude(pk=student.pk).exists():
            return
        code = f'{secrets.randbelow(10 ** DIGITS):0{DIGITS}d}'
        SignupCode.objects.using('auth').create(student=student, new_email=new_email, created_at=now,
                                                expires_at=now + LIFETIME, digest=_digest(student.pk, new_email, code))
        text = (f'Your University Command Center email-change code is {code}\n\n'
                f'It works for 10 minutes. Enter it on the Change email page to use this address.\n'
                f'If you did not ask for this, ignore this email; nothing changes.')
        transaction.on_commit(lambda: _send(f'{code} is your University Command Center code', text, new_email),
                              using='auth')


def pending(student_id):
    """The address waiting for its code, or None."""
    record = (SignupCode.objects.using('auth')
              .filter(student_id=student_id, consumed_at__isnull=True, new_email__isnull=False,
                      expires_at__gt=timezone.now(), attempts__lt=MAX_ATTEMPTS)
              .order_by('-created_at').first())
    return record.new_email if record else None


def confirm(student_id, text):
    """True if `text` is the newest unexpired code: the email is then replaced. Wrong guesses count."""
    code = clean_code(text)
    if code is None:
        return False
    with transaction.atomic(using='auth'):
        student = _student(student_id)
        if student is None:
            return False
        record = (SignupCode.objects.using('auth').select_for_update()
                  .filter(student=student, consumed_at__isnull=True).order_by('-created_at').first())
        now = timezone.now()
        if (record is None or record.new_email is None or record.expires_at <= now
                or record.attempts >= MAX_ATTEMPTS):
            return False
        if not constant_time_compare(record.digest, _digest(student.pk, record.new_email, code)):
            record.attempts += 1
            record.save(using='auth', update_fields=['attempts'])
            return False
        old_email = student.email
        record.consumed_at = now
        record.save(using='auth', update_fields=['consumed_at'])
        try:
            with transaction.atomic(using='auth'):
                student.email = record.new_email
                student.email_verified_at = now
                student.save(using='auth', update_fields=['email', 'email_verified_at', 'updated_at'])
        except IntegrityError:
            return False  # another account took the address meanwhile; the code is used up
        if old_email:
            transaction.on_commit(lambda: _send(
                'Your University Command Center email was changed',
                'The email address on your University Command Center account was just changed, so '
                'messages now go to the new address.\n\nIf you did not do this, reply to this email '
                'straight away.', old_email), using='auth')
        return True
