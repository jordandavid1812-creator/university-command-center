"""Account identity and private, expiring authentication support records."""
import uuid
from datetime import timedelta
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


HEX_DIGEST = r"^[0-9a-f]{64}$"


class TrustedDevice(models.Model):
    """S0-02A: server-side trusted-browser record. Stores digests only, never a raw cookie ID.

    Account binding is the immutable `student` foreign key (UUID); there is no
    username-derived key, so device trust follows exact account identity.

    Dormant: not consulted by login until S0-02B is approved. A device never
    authenticates a student; it can only select throttle limits (see
    docs/security/S1_PROPOSALS.md section A).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="trusted_devices")
    current_digest = models.CharField(max_length=64, unique=True)
    previous_digest = models.CharField(max_length=64, unique=True, null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    last_used_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(current_digest__regex=HEX_DIGEST), name="trusteddevice_hex"),
            models.CheckConstraint(condition=(models.Q(previous_digest__isnull=True) & models.Q(rotated_at__isnull=True))
                                   # Explicit IS NOT NULL: a CHECK accepts UNKNOWN, so without it
                                   # previous_digest=NULL with rotated_at set would pass (Codex P26-03).
                                   | (models.Q(previous_digest__isnull=False) & models.Q(rotated_at__isnull=False)
                                      & models.Q(previous_digest__regex=HEX_DIGEST)
                                      & ~models.Q(previous_digest=models.F("current_digest"))),
                                   name="trusteddevice_rotation"),
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("created_at"))
                                   & models.Q(last_used_at__gte=models.F("created_at"))
                                   & models.Q(expires_at__lte=models.F("last_used_at") + timedelta(days=30)),
                                   name="trusteddevice_expiry"),
        ]
        indexes = [
            models.Index(fields=["student", "last_used_at"], name="trusteddevice_student_lru"),
            models.Index(fields=["expires_at"], name="trusteddevice_expiry_idx"),
        ]


class DeviceGeneration(models.Model):
    """S0-02A: monotonic per-student device-trust generation (review F04).

    Every explicit revocation increments it under the Student lock. Issuance must present
    the generation observed BEFORE password verification, so a login in flight during a
    forget-all can never re-create trust. Rows are never deleted or reset (the auth role
    has no DELETE/TRUNCATE), so the epoch cannot restart.
    """
    student = models.OneToOneField(Student, on_delete=models.CASCADE, primary_key=True,
                                   related_name="device_generation")
    generation = models.PositiveBigIntegerField(default=0)


LOGIN_LIMIT_KINDS = [("account_fail", "Account failures"), ("account_trusted_fail", "Account trusted failures"),
                     ("account_success", "Account successes"), ("device_fail", "Device failures"),
                     ("ip_ceiling", "Source ceiling")]


class LoginLimit(models.Model):
    """S0-02A: account/device login counters keyed by HMAC. Schema only; used from S0-02B."""
    bucket = models.CharField(max_length=64, primary_key=True)
    kind = models.CharField(max_length=24, choices=LOGIN_LIMIT_KINDS)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(bucket__regex=HEX_DIGEST), name="loginlimit_bucket_hex"),
            models.CheckConstraint(condition=models.Q(kind__in=[kind for kind, _ in LOGIN_LIMIT_KINDS]), name="loginlimit_kind"),
        ]
