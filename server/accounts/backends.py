"""Django authentication with explicit private-account routing and generic failures."""
from django.contrib.auth.backends import BaseBackend
from .models import Student
from .boundary import require_auth_role


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
        valid_password = student.check_password(password)
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
