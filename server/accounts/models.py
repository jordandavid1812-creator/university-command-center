"""Account identity and private, expiring authentication support records."""
import uuid
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone
from django.db.models.functions import Lower, Trim


class StudentManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        student = self.model(username=username, **extra_fields)
        student.set_password(password)  # None creates an unusable password.
        student.full_clean()
        student.save(using=self._db)
        return student


class Student(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True,
                                validators=[UnicodeUsernameValidator()])
    email = models.EmailField(max_length=254, null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    objects = StudentManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(username=""), name="student_username_nonempty"),
            models.UniqueConstraint(Lower("email"), condition=models.Q(email__isnull=False),
                                    name="student_email_unique"),
            models.CheckConstraint(condition=models.Q(email__isnull=True) | (
                ~models.Q(email="") & models.Q(email=Lower(Trim("email")))), name="student_email_normalized"),
        ]


class AccountToken(models.Model):
    """Random selector + SHA-256 secret digest; email contains the secret, DB does not."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="account_tokens")
    purpose = models.CharField(max_length=12, choices=[("verify", "Verify email"), ("reset", "Reset password")])
    digest = models.CharField(max_length=64)
    credential_stamp = models.CharField(max_length=64)
    email_at_issue = models.EmailField(max_length=254)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(purpose__in=["verify", "reset"]), name="account_token_purpose"),
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("created_at")), name="account_token_expiry"),
        ]
        indexes = [models.Index(fields=["student", "purpose"]), models.Index(fields=["expires_at"])]


class AuthThrottle(models.Model):
    """Shared atomic counters keyed by an HMAC, not plaintext identifiers/IPs."""
    bucket = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(db_index=True)
