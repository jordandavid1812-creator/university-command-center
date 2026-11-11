"""Minimal internal account identity; no registration flow."""
import uuid
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone


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
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    objects = StudentManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [models.CheckConstraint(
            condition=~models.Q(username=""), name="student_username_nonempty")]
