"""Local authentication and a deliberately small academic integration surface."""
from functools import wraps
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.db import DatabaseError, transaction
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST
from academics.ownership import OwnershipRequired, identity_for_verified_student
from academics.services import assignments, courses, semesters, InvalidRecord, RecordConflict, RecordNotFound
from .forms import (EmailRequestForm, RegistrationForm, BoundedAuthenticationForm,
                    BoundedPasswordChangeForm, BoundedSetPasswordForm)
from .models import Student
from .principals import principal_for_request
from .throttling import rate_limit
from . import tokens


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
        tokens.register(form.cleaned_data)
        return render(request, 'accounts/message.html', {'message': tokens.GENERIC_EMAIL_MESSAGE})
    return render(request, 'accounts/form.html', {'form': form, 'title': 'Register', 'submit': 'Register'})


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
        auth_login(request, form.get_user())  # Django rotates the anonymous session key.
        request.session.set_expiry(0)  # Browser-session cookie; server-side limit is 30 minutes.
        return redirect('accounts:academic')  # Ignore request-controlled redirect destinations.
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
        return render(request, 'accounts/message.html', {'message': tokens.GENERIC_EMAIL_MESSAGE})
    title = 'Resend email verification' if purpose == 'verify' else 'Reset password'
    return render(request, 'accounts/form.html', {'form': form, 'title': title, 'submit': 'Send email'})


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
