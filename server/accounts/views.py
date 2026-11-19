"""Local authentication and a deliberately small academic integration surface."""
from functools import wraps
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import check_password
from django.db import DatabaseError, transaction
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST
from academics.ownership import OwnershipRequired, identity_for_verified_student
from academics.services import assignments, courses, semesters, InvalidRecord, RecordConflict, RecordNotFound
from .forms import (EmailRequestForm, RegistrationForm, BoundedAuthenticationForm,
                    BoundedPasswordChangeForm, BoundedSetPasswordForm, SignupCodeForm)
from .models import Student
from .principals import principal_for_request
from .throttling import rate_limit
from . import invites, signup_codes, tokens

CODE_SENT = 'If this email needs confirming, we have sent it a 6-digit code. It works for 1 minute.'
CODE_WRONG = 'That code is wrong or has expired. Check the newest email, or ask for a new code.'


def _code_page(request, form, notice=None):
    return render(request, 'accounts/code.html', {'form': form, 'title': 'Enter your code', 'notice': notice})


def _code_sent(request, email):
    """After sign-up or a resend on the public site: the code page with the email filled in."""
    return _code_page(request, SignupCodeForm(initial={'email': email}), CODE_SENT)


@never_cache
@sensitive_post_parameters()
@require_http_methods(['GET', 'POST'])
def register(request):
    if request.method == 'POST':
        limited = rate_limit(request, 'register')
        if limited is not None:
            return limited
    form = RegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        # The invite is used up in the same transaction as the account (and only when the rest of
        # the form is valid), so a failure leaves it unused. A duplicate username or email still
        # uses it and gets the same generic reply, so a code cannot be reused to probe accounts.
        with transaction.atomic(using='auth'):
            if getattr(settings, 'UCC_REQUIRE_INVITE', False) and not invites.consume(form.cleaned_data['invite_code']):
                form.add_error('invite_code', invites.INVALID)
            else:
                tokens.register(form.cleaned_data)
                if getattr(settings, 'UCC_SIGNUP_CODE', False):
                    return _code_sent(request, form.cleaned_data['email'])
                return render(request, 'accounts/message.html', {'message': tokens.GENERIC_EMAIL_MESSAGE})
    return render(request, 'accounts/form.html', {'form': form, 'title': 'Register', 'submit': 'Register'})


LEGAL_UPDATED = '19 November 2026'
LEGAL_CONTACT = 'unicommand.info@gmail.com'


@require_http_methods(['GET', 'HEAD'])
def privacy(request):
    """Public privacy notice (launch step G). Keep it in step with what the site stores and sends."""
    return render(request, 'accounts/privacy.html', {'updated': LEGAL_UPDATED, 'contact': LEGAL_CONTACT})


@require_http_methods(['GET', 'HEAD'])
def terms(request):
    """Public terms of use (launch step G)."""
    return render(request, 'accounts/terms.html', {'updated': LEGAL_UPDATED, 'contact': LEGAL_CONTACT})


@never_cache
@sensitive_post_parameters()
@require_http_methods(['GET', 'POST'])
def login(request):
    if request.method == 'POST':
        limited = rate_limit(request, 'login')
        if limited is not None:
            return limited
    form = BoundedAuthenticationForm(request, data=request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        verified = form.get_user()
        # F04b: the password was verified against a row read WITHOUT a lock. Re-read it
        # under the Student lock (the lock reset/change also take) and create the session
        # only if the stored hash is still exactly the one verified. A credential change
        # committed in between refuses the login; one committed afterwards waits for this
        # lock and then invalidates the new session through the existing auth-hash check.
        with transaction.atomic(using='auth'):
            current = (Student.objects.using('auth').select_for_update()
                       .filter(pk=verified.pk, is_active=True, email_verified_at__isnull=False,
                               email__isnull=False).first())
            # A different hash with the SAME secret (a concurrent hash upgrade) still accepts
            # this password; re-verify under the lock only in that rare case (no setter).
            if current is not None and (constant_time_compare(current.password, verified.password)
                                        or check_password(form.cleaned_data['password'], current.password)):
                auth_login(request, current)  # Django rotates the anonymous session key.
                request.session.set_expiry(0)  # Browser-session cookie; server-side limit is 30 minutes.
                return redirect('student_web:dashboard' if getattr(settings, 'STUDENT_WEBSITE_ENABLED', False) else 'accounts:academic')
        form.add_error(None, form.get_invalid_login_error())  # Same generic error as a wrong password.
    return render(request, 'accounts/form.html', {'form': form, 'title': 'Login', 'submit': 'Login'})


@never_cache
@require_POST
def logout(request):
    auth_logout(request)
    return redirect('accounts:login')


@never_cache
@require_http_methods(['GET', 'POST'])
def email_request(request, purpose):
    if request.method == 'POST':
        limited = rate_limit(request, 'resend' if purpose == 'verify' else 'reset')
        if limited is not None:
            return limited
    form = EmailRequestForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        tokens.request_email(form.cleaned_data['email'], purpose)
        if purpose == 'verify' and getattr(settings, 'UCC_SIGNUP_CODE', False):
            return _code_sent(request, form.cleaned_data['email'])
        return render(request, 'accounts/message.html', {'message': tokens.GENERIC_EMAIL_MESSAGE})
    title = 'Resend email verification' if purpose == 'verify' else 'Reset password'
    return render(request, 'accounts/form.html', {'form': form, 'title': title, 'submit': 'Send email'})


@never_cache
@sensitive_post_parameters('code')
@require_http_methods(['GET', 'POST'])
def verify_code(request):
    """Public site: type the emailed code (1 minute, 5 tries), or press "Send me a new code".
    One form with two buttons, so it works without JavaScript. Replies never reveal accounts."""
    if not getattr(settings, 'UCC_SIGNUP_CODE', False):
        return HttpResponse('Not found.', status=404)
    if request.method != 'POST':
        return _code_page(request, SignupCodeForm())
    resend = request.POST.get('action') == 'resend'
    limited = rate_limit(request, 'resend' if resend else 'verify-code')
    if limited is not None:
        return limited
    form = SignupCodeForm(request.POST)
    if not form.is_valid():
        return _code_page(request, form)
    email = form.cleaned_data['email']
    if resend:
        tokens.request_email(email, 'verify')
        return _code_sent(request, email)
    if signup_codes.verify(email, form.cleaned_data['code']):
        return render(request, 'accounts/message.html', {'message': 'Email confirmed. You can now log in.'})
    form.add_error('code', CODE_WRONG)
    return _code_page(request, form)


@never_cache
@require_http_methods(['GET', 'POST'])
def verify(request, selector, secret):
    limited = rate_limit(request, 'verify')
    if limited is not None:
        return limited
    if request.method == 'POST':
        if tokens.verify_email(selector, secret):
            return render(request, 'accounts/message.html', {'message': 'Email verified. You can now log in.'})
    elif tokens.valid_token(selector, secret, 'verify'):
        return render(request, 'accounts/form.html', {'title': 'Verify email', 'submit': 'Confirm email'})
    return HttpResponse('Link is invalid or expired.', status=400)


@never_cache
@sensitive_post_parameters()
@require_http_methods(['GET', 'POST'])
def reset_confirm(request, selector, secret):
    limited = rate_limit(request, 'reset-confirm')
    if limited is not None:
        return limited
    # Consumption and password replacement are serialized under the same auth transaction.
    with transaction.atomic(using='auth'):
        result = tokens.valid_token(selector, secret, 'reset', lock=request.method == 'POST')
        if not result:
            return HttpResponse('Link is invalid or expired.', status=400)
        token, student = result
        form = BoundedSetPasswordForm(student, request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            student.set_password(form.cleaned_data['new_password1'])
            student.save(using='auth', update_fields=['password', 'updated_at'])
            token.consumed_at = timezone.now()
            token.save(using='auth', update_fields=['consumed_at'])
            auth_logout(request)
            return render(request, 'accounts/message.html', {'message': 'Password changed. Please log in again.'})
    return render(request, 'accounts/form.html', {'form': form, 'title': 'Choose a new password', 'submit': 'Change password'})


def student_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            principal = principal_for_request(request)
            identity = identity_for_verified_student(principal)
        except OwnershipRequired:
            if request.session.get("_auth_user_id"):
                request.user = AnonymousUser()  # Do not evaluate a malformed lazy session user while flushing it.
                auth_logout(request)
            return redirect('accounts:login')
        request.student_identity = identity
        return view(request, identity, *args, **kwargs)
    return wrapped


@never_cache
@sensitive_post_parameters()
@require_http_methods(['GET', 'POST'])
@student_required
def password_change(request, identity):
    if request.method == 'POST':
        limited = rate_limit(request, 'password-change')
        if limited is not None:
            return limited
    with transaction.atomic(using='auth'):
        student = Student.objects.using('auth').select_for_update().get(pk=identity.student_id)
        form = BoundedPasswordChangeForm(student, request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            student.set_password(form.cleaned_data['new_password1'])
            student.save(using='auth', update_fields=['password', 'updated_at'])
            auth_logout(request)  # Other sessions fail their password-derived auth hash on next use.
            return redirect('accounts:login')
    return render(request, 'accounts/form.html', {'form': form, 'title': 'Change password', 'submit': 'Change password'})


def academic_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except RecordNotFound:
            return JsonResponse({'error': 'Record not found.'}, status=404)
        except RecordConflict:
            return JsonResponse({'error': 'Record has changed; reload and try again.'}, status=409)
        except OwnershipRequired:
            return JsonResponse({'error': 'Authentication required.'}, status=403)
        except (InvalidRecord, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid record.'}, status=400)
        except DatabaseError:
            return JsonResponse({'error': 'The operation could not be completed.'}, status=503)
    return wrapped


@never_cache
@require_http_methods(['GET'])
@student_required
@academic_errors
def academic(request, identity):
    if getattr(settings, 'STUDENT_WEBSITE_ENABLED', False):
        return redirect('student_web:dashboard')
    return render(request, 'accounts/academic.html', {
        'courses': courses.list(identity), 'assignments': assignments.list(identity),
        'semesters': semesters.list(identity),
    })


@never_cache
@require_http_methods(['GET', 'POST'])
@student_required
@academic_errors
def course(request, identity, identifier):
    if request.method == 'GET':
        record = courses.retrieve(identity, identifier)
        return JsonResponse({'id': str(record.pk), 'name': record.name, 'actual_grade': record.actual_grade,
                             'record_version': record.record_version})
    if set(request.POST) - {'csrfmiddlewaretoken', 'version', 'actual_grade'}:
        raise InvalidRecord()
    record = courses.update(identity, identifier, version=int(request.POST.get('version', '')),
                            actual_grade=request.POST.get('actual_grade'))
    if 'text/html' in request.headers.get('Accept', ''):
        return redirect('accounts:academic')
    return JsonResponse({'id': str(record.pk), 'record_version': record.record_version, 'actual_grade': record.actual_grade})


@never_cache
@require_POST
@student_required
@academic_errors
def delete_assignment(request, identity, identifier):
    if set(request.POST) - {'csrfmiddlewaretoken', 'version'}:
        raise InvalidRecord()
    assignments.delete(identity, identifier, version=int(request.POST.get('version', '')))
    if 'text/html' in request.headers.get('Accept', ''):
        return redirect('accounts:academic')
    return HttpResponse(status=204)
