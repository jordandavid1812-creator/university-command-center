"""Expiring one-use digests. Password handling always uses Django hashers/forms."""
from datetime import timedelta
import hashlib
import logging
import secrets
from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from .models import AccountToken, Student
from .email_content import branded_html


GENERIC_EMAIL_MESSAGE = 'If these details are eligible, an email with the next steps will be sent.'


def _deliver(subject, link, email, *, code=None, action_url=None):
    try:
        body = f'{link}\n\nIgnore this email if you did not request it.'
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email],
                  html_message=branded_html(body, code=code, action_url=action_url))
    except Exception:
        # Keep account existence and link secrets out of failure responses/logs.
        logging.getLogger(__name__).warning('Account email delivery failed; retry through the recovery form.')


def _issue_locked(student, purpose):
    now = timezone.now()
    AccountToken.objects.using('auth').filter(student=student, purpose=purpose, consumed_at__isnull=True).update(consumed_at=now)
    secret = secrets.token_urlsafe(32)
    token = AccountToken.objects.using('auth').create(
        student=student, purpose=purpose, digest=hashlib.sha256(secret.encode()).hexdigest(),
        credential_stamp=student.get_session_auth_hash(), email_at_issue=student.email,
        expires_at=now + timedelta(hours=24 if purpose == 'verify' else 1),
    )
    name = 'verify' if purpose == 'verify' else 'reset-confirm'
    path = reverse(f'accounts:{name}', args=[token.pk, secret])
    link = settings.AUTH_LINK_ORIGIN.rstrip('/') + path
    subject = 'Verify your University Command Center email' if purpose == 'verify' else 'Reset your University Command Center password'
    # Commit the digest before sending. Console/locmem only in this milestone.
    transaction.on_commit(lambda: _deliver(subject, link, student.email, action_url=link), using='auth')


def _issue_verification(student):
    """Public site (UCC_SIGNUP_CODE): a 6-digit email code. Otherwise the original email link."""
    if getattr(settings, 'UCC_SIGNUP_CODE', False):
        from .signup_codes import issue_locked
        issue_locked(student)
    else:
        _issue_locked(student, 'verify')


def register(values):
    try:
        with transaction.atomic(using='auth'):
            from .names import clean_full_name
            student = Student(username=values['username'], email=values['email'],
                              full_name=clean_full_name(values.get('full_name', '')))
            student.set_password(values['password1'])
            student.save(using='auth', force_insert=True)
            _issue_verification(student)
    except IntegrityError:
        # Duplicate username OR normalized email gets the same response as success.
        return


def request_email(email, purpose):
    with transaction.atomic(using='auth'):
        students = Student.objects.using('auth').select_for_update().filter(email=email, is_active=True)
        students = students.filter(email_verified_at__isnull=(purpose == 'verify'))
        student = students.first()
        if student and student.has_usable_password():
            if purpose == 'verify':
                _issue_verification(student)
            else:
                _issue_locked(student, purpose)


def valid_token(selector, secret, purpose, *, lock=False):
    if not isinstance(secret, str) or len(secret) != 43 or not secret.isascii():
        return None
    # Always lock Student before AccountToken, matching issuance/password-change order.
    token = AccountToken.objects.using('auth').filter(pk=selector).first()
    if not token:
        return None
    students = Student.objects.using('auth')
    if lock:
        students = students.select_for_update()
    student = students.filter(pk=token.student_id).first()
    records = AccountToken.objects.using('auth')
    if lock:
        records = records.select_for_update()
    token = records.filter(pk=selector).first()
    now = timezone.now()
    if (not token or not student or not student.is_active or token.purpose != purpose
            or token.consumed_at is not None or token.expires_at <= now
            or token.email_at_issue != student.email
            or not constant_time_compare(token.credential_stamp, student.get_session_auth_hash())
            or not constant_time_compare(token.digest, hashlib.sha256(secret.encode()).hexdigest())
            or (purpose == 'reset' and student.email_verified_at is None)
            or (purpose == 'verify' and student.email_verified_at is not None)):
        return None
    return token, student


def verify_email(selector, secret):
    with transaction.atomic(using='auth'):
        result = valid_token(selector, secret, 'verify', lock=True)
        if not result:
            return False
        token, student = result
        now = timezone.now()
        student.email_verified_at = now
        student.save(using='auth', update_fields=['email_verified_at', 'updated_at'])
        token.consumed_at = now
        token.save(using='auth', update_fields=['consumed_at'])
        return True
