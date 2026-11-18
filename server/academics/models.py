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

# Timetable: one weekly class (a lecture, tutorial, lab...) of one of the student's courses.
WEEKDAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"),
            (5, "Saturday"), (6, "Sunday")]
CLASS_KINDS = [("lecture", "Lecture"), ("tutorial", "Tutorial"), ("lab", "Practical or lab"), ("other", "Other")]


class ClassSession(ValidatedRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="class_sessions")
    # Deleting a course removes its timetable entries (they mean nothing without it).
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="class_sessions")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    kind = models.CharField(max_length=10, choices=CLASS_KINDS, default="lecture")
    venue = models.CharField(max_length=100, blank=True)
    record_version = models.PositiveBigIntegerField(default=1)

    def clean(self):
        if self.course_id and self.owner_id and not Course.objects.using(self._state.db).filter(
                pk=self.course_id, owner_id=self.owner_id).exists():
            raise ValidationError({"course": "Course must belong to the class owner."})
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "The class must end after it starts (on the same day)."})

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(weekday__gte=0, weekday__lte=6), name="class_weekday_valid"),
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="class_ends_after_start"),
            models.CheckConstraint(condition=models.Q(kind__in=[code for code, _ in CLASS_KINDS]), name="class_kind_valid"),
            models.CheckConstraint(condition=~models.Q(venue__regex=r"^\s|\s$"), name="class_venue_trimmed"),
            models.CheckConstraint(condition=models.Q(record_version__gte=1), name="class_version_positive"),
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


# Search: the text of each stored study file, read once (at upload, or the first time the
# student searches). Never edited; deleting the material deletes it. When a file has no
# readable text, one row records why (`problem`), so it is not read again on every search.
MAX_SEARCH_CHARACTERS = 60000
SEARCH_PROBLEMS = [("", "Text saved"), ("no_text", "No text"), ("encrypted", "Password protected"),
                   ("unreadable", "Unreadable"), ("unsupported", "Not supported")]


class MaterialText(ValidatedRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="material_texts")
    material = models.OneToOneField(StudyMaterial, on_delete=models.CASCADE, related_name="search_text")
    text = models.TextField(blank=True)
    truncated = models.BooleanField(default=False)
    problem = models.CharField(max_length=12, blank=True, choices=SEARCH_PROBLEMS)

    def clean(self):
        if self.material_id and self.owner_id and not StudyMaterial.objects.using(self._state.db).filter(
                pk=self.material_id, owner_id=self.owner_id).exists():
            raise ValidationError({"material": "Material must belong to the text owner."})

    class Meta:
        constraints = [
            models.CheckConstraint(condition=LessThanOrEqual(Length("text"), MAX_SEARCH_CHARACTERS),
                                   name="materialtext_size_limit"),
            models.CheckConstraint(condition=models.Q(problem__in=[code for code, _ in SEARCH_PROBLEMS]),
                                   name="materialtext_problem_valid"),
            # Text, or a reason there is none: never both, never neither.
            models.CheckConstraint(condition=(models.Q(problem="") & GreaterThanOrEqual(Length("text"), 1))
                                   | (~models.Q(problem="") & models.Q(text="") & models.Q(truncated=False)),
                                   name="materialtext_text_or_problem"),
        ]


LEVEL_CHOICES = [("100", "100 level"), ("200", "200 level"), ("300", "300 level"), ("400", "400 level"),
                 ("500", "500 level"), ("600", "600 level"), ("700", "700 level"), ("PG", "Postgraduate")]
MATRIC_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9/._-]{0,31}$"
NO_EDGE_SPACE = r"^\s|\s$"


class StudentProfile(ValidatedRecord):
    """Optional profile details. Visible and editable only by their owner; one per student."""
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name="academic_profile")
    display_name = models.CharField(max_length=80, blank=True)
    institution = models.CharField(max_length=150, blank=True)
    programme = models.CharField(max_length=150, blank=True)
    level = models.CharField(max_length=3, blank=True, choices=LEVEL_CHOICES)
    matric_number = models.CharField(max_length=32, blank=True, validators=[
        RegexValidator(MATRIC_PATTERN, "Use letters, digits and / . _ - only.")])
    # The student's own class-of-degree bands (lowest CGPA for each class). All five empty means
    # "use the common guide" (academic_logic.DEFAULT_CLASS_BANDS). A guide only, never a ruling.
    first_class_min = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    second_upper_min = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    second_lower_min = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    third_class_min = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    pass_min = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    record_version = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(level__in=[""] + [code for code, _ in LEVEL_CHOICES]),
                                   name="profile_level_valid"),
            models.CheckConstraint(condition=models.Q(matric_number="") | models.Q(matric_number__regex=MATRIC_PATTERN),
                                   name="profile_matric_format"),
            models.CheckConstraint(condition=~models.Q(display_name__regex=NO_EDGE_SPACE)
                                   & ~models.Q(institution__regex=NO_EDGE_SPACE)
                                   & ~models.Q(programme__regex=NO_EDGE_SPACE),
                                   name="profile_text_trimmed"),
            models.CheckConstraint(condition=models.Q(record_version__gte=1), name="profile_version_positive"),
            # Bands: all empty, or all set, within 0-5 and strictly falling from First to Pass.
            models.CheckConstraint(
                condition=models.Q(first_class_min__isnull=True, second_upper_min__isnull=True,
                                   second_lower_min__isnull=True, third_class_min__isnull=True,
                                   pass_min__isnull=True)
                # "isnull=False" matters: a comparison with an empty value is unknown, and a CHECK lets unknown pass.
                | models.Q(first_class_min__isnull=False, second_upper_min__isnull=False,
                           second_lower_min__isnull=False, third_class_min__isnull=False, pass_min__isnull=False,
                           first_class_min__lte=5, pass_min__gte=0,
                           first_class_min__gt=models.F("second_upper_min"),
                           second_upper_min__gt=models.F("second_lower_min"),
                           second_lower_min__gt=models.F("third_class_min"),
                           third_class_min__gt=models.F("pass_min")),
                name="profile_class_bands_valid"),
        ]


# AI study assistant records (docs/AI_STUDY_ASSISTANT_PLAN.md, stage 1). Fixed value lists:
# adding a value later needs a migration, so keep these in step with the plan.
AI_TOOLS = [("summary", "Summary"), ("quiz", "Quiz"), ("flashcards", "Flashcards"), ("answer", "Ask a question")]
AI_PROVIDERS = [("gemini", "Gemini"), ("grok", "Grok")]
AI_STATUSES = [("sent", "In progress"), ("succeeded", "Succeeded"), ("failed", "Failed"),
               ("interrupted", "Interrupted")]
AI_ERROR_CATEGORIES = [("network", "Network"), ("timeout", "Timeout"), ("redirect", "Redirect"),
                       ("http_error", "Provider error"), ("too_large", "Response too large"),
                       ("invalid_response", "Invalid response"), ("blocked", "Blocked by provider"),
                       ("truncated", "Response cut off"), ("save", "Could not save")]
AI_MODEL_PATTERN = r"^[a-z0-9][a-z0-9.\-]{0,63}$"
MAX_AI_TEXT_CHARACTERS = 60000
MAX_AI_QUESTION_CHARACTERS = 500
MAX_AI_RESULT_BYTES = 64 * 1024


class StudyAiRequest(ValidatedRecord):
    """The usage ledger: one row per request sent to a provider. Never deleted by the website.

    It has no link to the study material, so deleting a material cannot reset the daily count.
    It keeps no file name, file text, question or response.
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ai_requests")
    tool = models.CharField(max_length=10, choices=AI_TOOLS)
    provider = models.CharField(max_length=6, choices=AI_PROVIDERS)
    model = models.CharField(max_length=64, validators=[RegexValidator(AI_MODEL_PATTERN)])
    status = models.CharField(max_length=11, choices=AI_STATUSES, default="sent")
    characters_sent = models.PositiveIntegerField()
    truncated = models.BooleanField()
    consent_token_hash = models.CharField(max_length=64)
    error_category = models.CharField(max_length=16, blank=True, choices=AI_ERROR_CATEGORIES)
    # For a failed reply: "4xx" usually means a wrong key or model, "5xx" a provider problem.
    status_class = models.CharField(max_length=3, blank=True, default="", db_default="",
                                    choices=[("3xx", "3xx"), ("4xx", "4xx"), ("5xx", "5xx")])

    class Meta:
        indexes = [models.Index(fields=["owner", "created_at"], name="airequest_owner_created")]
        constraints = [
            models.UniqueConstraint(fields=["id", "owner"], name="airequest_id_owner_unique"),
            # Lets a result's key include the tool, so a result always matches its request's tool.
            models.UniqueConstraint(fields=["id", "owner", "tool"], name="airequest_id_owner_tool_unique"),
            models.UniqueConstraint(fields=["owner", "consent_token_hash"], name="airequest_token_once"),
            # At most one request in flight per student.
            models.UniqueConstraint(fields=["owner"], condition=models.Q(status="sent"),
                                    name="airequest_one_in_flight"),
            models.CheckConstraint(condition=models.Q(tool__in=[code for code, _ in AI_TOOLS]),
                                   name="airequest_tool_valid"),
            models.CheckConstraint(condition=models.Q(provider__in=[code for code, _ in AI_PROVIDERS]),
                                   name="airequest_provider_valid"),
            models.CheckConstraint(condition=models.Q(status__in=[code for code, _ in AI_STATUSES]),
                                   name="airequest_status_valid"),
            models.CheckConstraint(condition=models.Q(model__regex=AI_MODEL_PATTERN),
                                   name="airequest_model_valid"),
            models.CheckConstraint(condition=models.Q(consent_token_hash__regex=r"^[0-9a-f]{64}$"),
                                   name="airequest_token_hash_hex"),
            models.CheckConstraint(condition=models.Q(characters_sent__gte=1,
                                                      characters_sent__lte=MAX_AI_TEXT_CHARACTERS),
                                   name="airequest_characters_range"),
            # An error category exactly when the request failed.
            models.CheckConstraint(condition=(models.Q(status="failed", error_category__in=[
                                       code for code, _ in AI_ERROR_CATEGORIES])
                                   | (~models.Q(status="failed") & models.Q(error_category=""))),
                                   name="airequest_category_valid"),
            # A status class only on a failed request, and only one of the three classes.
            models.CheckConstraint(condition=models.Q(status_class="")
                                   | models.Q(status="failed", status_class__in=["3xx", "4xx", "5xx"]),
                                   name="airequest_status_class_valid"),
        ]


class StudyAiResult(ValidatedRecord):
    """A saved, checked AI output. Never edited; deleted with its material or by the student."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ai_results")
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name="ai_results")
    request = models.OneToOneField(StudyAiRequest, on_delete=models.PROTECT, related_name="result")
    tool = models.CharField(max_length=10, choices=AI_TOOLS)
    question = models.CharField(max_length=MAX_AI_QUESTION_CHARACTERS, blank=True)
    result = models.JSONField()
    shape_version = models.PositiveSmallIntegerField()

    def clean(self):
        alias = self._state.db
        if self.material_id and self.owner_id and not StudyMaterial.objects.using(alias).filter(
                pk=self.material_id, owner_id=self.owner_id).exists():
            raise ValidationError({"material": "Material must belong to the result owner."})
        if self.request_id and self.owner_id and not StudyAiRequest.objects.using(alias).filter(
                pk=self.request_id, owner_id=self.owner_id, tool=self.tool).exists():
            raise ValidationError({"request": "Request must belong to the result owner and match its tool."})

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(tool__in=[code for code, _ in AI_TOOLS]),
                                   name="airesult_tool_valid"),
            # Only "Ask a question" has a question, and it must not be blank.
            models.CheckConstraint(condition=(models.Q(tool="answer") & ~models.Q(question__regex=r"^\s*$"))
                                   | (~models.Q(tool="answer") & models.Q(question="")),
                                   name="airesult_question_matches_tool"),
            models.CheckConstraint(condition=models.Q(shape_version__gte=1), name="airesult_shape_version_positive"),
        ]
