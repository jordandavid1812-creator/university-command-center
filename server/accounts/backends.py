"""Django authentication with explicit private-account routing and generic failures.

F04b: passwords are verified WITHOUT Django's auto-saving upgrade setter. That setter
saves a re-hashed password through a possibly stale model instance, so a login that
loaded the row before a concurrent reset/change could write the OLD password back.
Upgrades here are a compare-and-swap on the exact hash that was verified.
"""
from django.contrib.auth.hashers import check_password, get_hasher, identify_hasher, make_password
from django.contrib.auth.backends import BaseBackend
from .models import Student
from .boundary import require_auth_role


def upgrade_password_hash(student, raw_password):
    """Re-hash with the preferred hasher only if the stored hash is still the one verified.

    Mirrors Django's must-update rule. The UPDATE matches zero rows if any newer password
    was committed after this instance was loaded, so it can never overwrite it.
    """
    verified = student.password
    try:
        hasher = identify_hasher(verified)
    except ValueError:
        return False
    preferred = get_hasher('default')
    if hasher.algorithm == preferred.algorithm and not preferred.must_update(verified):
        return False
    upgraded = make_password(raw_password)
    changed = Student.objects.using('auth').filter(pk=student.pk, password=verified).update(password=upgraded)
    if changed == 1:
        student.password = upgraded
    return changed == 1


class StudentBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        require_auth_role()
        if (not isinstance(username, str) or not isinstance(password, str)
                or len(username) > 150 or len(password) > 128):
            return None
        try:
            student = Student.objects.using("auth").get(username=username)
        except Student.DoesNotExist:
            Student().set_password(password)  # Dummy hashing work, as in Django ModelBackend.
            return None
        # No setter: verification never writes through this (possibly stale) instance.
        valid_password = check_password(password, student.password)
        if valid_password:
            upgrade_password_hash(student, password)
        if valid_password and student.is_active and student.email_verified_at and student.email:
            return student
        return None

    def get_user(self, user_id):
        require_auth_role()
        from django.core.exceptions import ValidationError
        try:
            return Student.objects.using("auth").get(pk=user_id, is_active=True,
                                                     email_verified_at__isnull=False, email__isnull=False)
        except (Student.DoesNotExist, ValidationError, ValueError):
            return None
