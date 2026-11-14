"""Database records, separate from legacy JSON adapters and calculations."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Length, Trim, Upper
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual
from academic_logic import GRADE_POINTS, checked_grade
from .fields import ExactCreditField
from .validators import validate_credits


class Timestamped(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ValidatedRecord(Timestamped):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # QuerySet.update/bulk_create bypass this: database constraints remain
        # essential. Use the services for version-checked transactional edits.
        self.full_clean()
        return super().save(*args, **kwargs)


class Semester(ValidatedRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="semesters")
    label = models.CharField(max_length=120)
    display_order = models.PositiveIntegerField(default=0)
    record_version = models.PositiveBigIntegerField(default=1)

    class Meta:
        ordering = ["display_order", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["id", "owner"], name="semester_id_owner_unique"),
            models.CheckConstraint(condition=models.Q(record_version__gte=1), name="semester_version_positive"),
            models.CheckConstraint(condition=~models.Q(label__regex=r"^\s*$"),
                                   name="semester_label_nonempty"),
        ]


class Course(ValidatedRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="courses")
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="courses")
    original_code = models.CharField(max_length=64, validators=[RegexValidator(
        r"^[ A-Za-z0-9_./-]+$", "Use ASCII letters, digits, spaces or _ . / - in course codes.")])
    normalized_code = models.CharField(max_length=64, editable=False)
    name = models.CharField(max_length=200)
    credit_units = ExactCreditField(max_digits=11, decimal_places=4, validators=[validate_credits])
    actual_grade = models.CharField(max_length=1, null=True, blank=True,
                                   choices=[(g, g) for g in GRADE_POINTS])
    record_version = models.PositiveBigIntegerField(default=1)

    def clean_fields(self, exclude=None):
        if isinstance(self.original_code, str):
            self.normalized_code = self.original_code.strip(" ").upper()
        if self.actual_grade is not None:
            try:
                self.actual_grade = checked_grade(self.actual_grade)
            except ValueError as error:
                raise ValidationError({"actual_grade": str(error)}) from error
        super().clean_fields(exclude=exclude)

    def clean(self):
        if self.semester_id and self.owner_id and not Semester.objects.using(self._state.db).filter(
                pk=self.semester_id, owner_id=self.owner_id).exists():
            raise ValidationError({"semester": "Semester must belong to the course owner."})

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "normalized_code"], name="course_owner_code_unique"),
            models.UniqueConstraint(fields=["id", "owner"], name="course_id_owner_unique"),
            models.CheckConstraint(condition=models.Q(original_code__regex=r"^[ A-Za-z0-9_./-]+$"),
                                   name="course_code_ascii"),
            models.CheckConstraint(condition=~models.Q(normalized_code="") & models.Q(
                normalized_code=Upper(Trim("original_code"))), name="course_code_normalized"),
            models.CheckConstraint(condition=~models.Q(name__regex=r"^\s*$"), name="course_name_nonempty"),
            models.CheckConstraint(condition=models.Q(credit_units__gte="0.0001", credit_units__lte="1000000"),
                                   name="course_credits_range"),
            models.CheckConstraint(condition=LessThanOrEqual(
                models.Func(models.F("credit_units"), function="scale", output_field=models.IntegerField()),
                models.Value(4)), name="course_credits_scale"),
            models.CheckConstraint(condition=models.Q(actual_grade__isnull=True) | models.Q(
                actual_grade__in=list(GRADE_POINTS)), name="course_grade_valid"),
            models.CheckConstraint(condition=models.Q(record_version__gte=1), name="course_version_positive"),
        ]


class Assignment(ValidatedRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="assignments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="assignments")
    title = models.CharField(max_length=240)
    due_date = models.DateField()
    completed = models.BooleanField(default=False)
    record_version = models.PositiveBigIntegerField(default=1)

    def clean(self):
        if self.course_id and self.owner_id and not Course.objects.using(self._state.db).filter(
                pk=self.course_id, owner_id=self.owner_id).exists():
            raise ValidationError({"course": "Course must belong to the assignment owner."})

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(title__regex=r"^\s*$"), name="assignment_title_nonempty"),
            models.CheckConstraint(condition=models.Q(record_version__gte=1), name="assignment_version_positive"),
        ]

MAX_MATERIAL_BYTES = 10 * 1024 * 1024  # Keep in step with student_web/upload_validation.py.


class StudyMaterial(ValidatedRecord):
    """Details of one uploaded study file. Its bytes are stored separately in MaterialFile."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="study_materials")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="study_materials")
    title = models.CharField(max_length=200)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=3, choices=[("pdf", "PDF"), ("txt", "Text")])
    size_bytes = models.PositiveIntegerField()
    record_version = models.PositiveBigIntegerField(default=1)

    def clean(self):
        if self.course_id and self.owner_id and not Course.objects.using(self._state.db).filter(
                pk=self.course_id, owner_id=self.owner_id).exists():
            raise ValidationError({"course": "Course must belong to the material owner."})

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(title__regex=r"^\s*$"),
                                   name="material_title_nonempty"),
            models.UniqueConstraint(fields=["id", "owner"], name="material_id_owner_unique"),
            models.CheckConstraint(condition=~models.Q(original_filename__regex=r"^\s*$")
                                   & ~models.Q(original_filename__regex=r"[/\\]"),
                                   name="material_filename_simple"),
            models.CheckConstraint(condition=models.Q(file_type__in=["pdf", "txt"]),
                                   name="material_file_type_valid"),
            models.CheckConstraint(condition=models.Q(size_bytes__gte=1, size_bytes__lte=MAX_MATERIAL_BYTES),
                                   name="material_size_range"),
            models.CheckConstraint(condition=models.Q(record_version__gte=1),
                                   name="material_version_positive"),
        ]


class MaterialFile(ValidatedRecord):
    """The stored bytes of one study material. Never edited; delete the material to remove it."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="material_files")
    material = models.OneToOneField(StudyMaterial, on_delete=models.CASCADE, related_name="stored_file")
    content = models.BinaryField()
    sha256 = models.CharField(max_length=64)

    def clean(self):
        if self.material_id and self.owner_id and not StudyMaterial.objects.using(self._state.db).filter(
                pk=self.material_id, owner_id=self.owner_id).exists():
            raise ValidationError({"material": "Material must belong to the file owner."})

    class Meta:
        constraints = [
            models.CheckConstraint(condition=GreaterThanOrEqual(Length("content"), 1),
                                   name="materialfile_not_empty"),
            models.CheckConstraint(condition=LessThanOrEqual(Length("content"), MAX_MATERIAL_BYTES),
                                   name="materialfile_size_limit"),
            models.CheckConstraint(condition=models.Q(sha256__regex=r"^[0-9a-f]{64}$"),
                                   name="materialfile_sha256_hex"),
        ]
