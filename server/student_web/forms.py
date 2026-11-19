import re
import uuid
from decimal import Decimal
from django import forms
from django.conf import settings
from grading_policy import LEGACY_POLICY
from academic_logic import CLASS_NAMES, checked_bands, checked_credits, checked_target, checked_grade, GRADE_POINTS
from academics.models import CLASS_KINDS, GRADING_SCALES, LEVEL_CHOICES, MATRIC_PATTERN, WEEKDAYS, Course
from academics.queries import MAX_PREDICTION_COURSES, WorkspaceLimit
from .upload_validation import (MAX_UPLOAD_BYTES, describe_size, validate_pdf_content, validate_text_content,
                                validate_upload_metadata)


def upload_cap():
    """This deployment's per-file limit (10 MiB, or 4 MB on Vercel)."""
    return min(getattr(settings, 'UCC_MAX_UPLOAD_BYTES', MAX_UPLOAD_BYTES), MAX_UPLOAD_BYTES)

def grade_help(policy):
    """'A=5, B=4, C=3, D=2, E=1, F=0' for the student's scale."""
    return ', '.join(f'{grade}={points}' for grade, points in policy.grade_points.items())


def scaled_decimal(form, name, policy, help_text):
    """Give a 0-to-maximum field the student's scale (the 5-point field is left exactly as it was)."""
    if policy is LEGACY_POLICY:
        return
    old = form.fields[name]
    form.fields[name] = forms.DecimalField(label=old.label, min_value=0, max_value=policy.maximum, max_digits=5,
                                           decimal_places=4, initial=old.initial, help_text=help_text)


class StrictForm(forms.Form):
    def __getitem__(self, name):
        field = super().__getitem__(name)
        if not field.field.required and not field.field.widget.is_hidden:
            label = field.field.label or field.label
            if not label.endswith(' (optional)'):
                field.field.label = label + ' (optional)'
                field.label = field.field.label
        return field

    def clean(self):
        values = super().clean()
        if self.is_bound and set(self.data) - set(self.fields) - {'csrfmiddlewaretoken'}:
            raise forms.ValidationError('Some submitted fields are not accepted. Reload the page and try again.')
        return values


class SemesterForm(StrictForm):
    label = forms.CharField(max_length=120, label='Semester label', help_text='For example, Year 1 · First semester. Labels do not set chronological order.')
    display_order = forms.IntegerField(min_value=0, max_value=2147483647, initial=0, help_text='Lower numbers appear first. This does not mark a semester as current.')


class CourseForm(StrictForm):
    name = forms.CharField(max_length=200, label='Course name')
    original_code = forms.CharField(max_length=64, label='Course code', validators=Course._meta.get_field('original_code').validators,
                                    help_text='Unique across your semesters. Letters, numbers, spaces and _ . / - are supported.')
    credit_units = forms.DecimalField(max_digits=11, decimal_places=4, min_value=Decimal('0.0001'), max_value=Decimal('1000000'),
                                      help_text='0.0001–1,000,000 credits, with at most four decimal places.')
    semester_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Semester', help_text='Only your semesters are available. Create one first if this list is empty.')
    actual_grade = forms.ChoiceField(required=False, choices=[('', 'Ungraded')] + [(g, g) for g in GRADE_POINTS],
                                    help_text='A=5, B=4, C=3, D=2, E=1, F=0. Ungraded is excluded from GPA.')

    def __init__(self, *args, semesters, policy=LEGACY_POLICY, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = policy
        if policy is not LEGACY_POLICY:
            self.fields['actual_grade'].choices = [('', 'Ungraded')] + [(g, g) for g in policy.grade_points]
            self.fields['actual_grade'].help_text = grade_help(policy) + '. Ungraded is excluded from GPA.'
        self.fields['semester_id'].choices = [('', 'Choose a semester')] + [(str(s.pk), f'{i}. {s.label}') for i, s in enumerate(semesters, 1)]

    def clean_credit_units(self):
        try:
            return checked_credits(self.cleaned_data['credit_units'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error

    def clean_actual_grade(self):
        return checked_grade(self.cleaned_data['actual_grade'], policy=self.policy)


class AssignmentForm(StrictForm):
    title = forms.CharField(max_length=240, label='Assignment title')
    course_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Course', help_text='Only your courses are available. The assignment stays linked if its course code changes.')
    due_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'), input_formats=['%Y-%m-%d'],
                               help_text='Deadlines use the Africa/Lagos calendar date. Overdue tasks stay in your records.')
    completed = forms.BooleanField(required=False, label='This assignment is complete')

    def __init__(self, *args, courses, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course_id'].choices = [('', 'Choose a course')] + [(str(c.pk), f'{c.normalized_code} · {c.name}') for c in courses]

class ClassSessionForm(StrictForm):
    """One weekly class on the timetable."""
    course_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Course', help_text='Only your courses are available.')
    weekday = forms.TypedChoiceField(coerce=int, label='Day', choices=[(str(n), name) for n, name in WEEKDAYS])
    start_time = forms.TimeField(label='Starts', widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
                                 input_formats=['%H:%M'], help_text='24-hour time, for example 08:00.')
    end_time = forms.TimeField(label='Ends', widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
                               input_formats=['%H:%M'], help_text='Must be after the start, on the same day.')
    kind = forms.ChoiceField(label='Type', choices=CLASS_KINDS, initial='lecture')
    venue = forms.CharField(max_length=100, required=False, label='Venue', help_text='For example, LT2 or Online.')

    def __init__(self, *args, courses, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course_id'].choices = [('', 'Choose a course')] + [(str(c.pk), f'{c.normalized_code} · {c.name}') for c in courses]

    def clean(self):
        values = super().clean()
        start, end = values.get('start_time'), values.get('end_time')
        if start and end and end <= start:
            self.add_error('end_time', 'The class must end after it starts (on the same day).')
        return values


class StudyPlanForm(StrictForm):
    """A new study plan: a course's exam date, revision days and the topics, one per line."""
    course_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Course', help_text='Only your courses are available.')
    exam_date = forms.DateField(label='Exam date', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                                input_formats=['%Y-%m-%d'], help_text='Must be after today (Africa/Lagos date).')
    review_days = forms.TypedChoiceField(coerce=int, label='Revision days before the exam', initial='1',
                                         choices=[('0', 'None'), ('1', '1 day'), ('2', '2 days'), ('3', '3 days')],
                                         help_text='These last days are kept free for revising everything.')
    topics = forms.CharField(label='Topics', widget=forms.Textarea(attrs={'rows': 8}), max_length=20000,
                             help_text='One topic per line, in the order you want to study them. Up to 60.')

    def __init__(self, *args, courses, today, **kwargs):
        super().__init__(*args, **kwargs)
        self.today = today
        self.fields['course_id'].choices = [('', 'Choose a course')] + [(str(c.pk), f'{c.normalized_code} · {c.name}') for c in courses]

    def clean_exam_date(self):
        exam = self.cleaned_data['exam_date']
        if exam <= self.today:
            raise forms.ValidationError('Choose an exam date after today.')
        if (exam - self.today).days > 366:
            raise forms.ValidationError('Choose an exam date within the next year.')
        return exam

    def clean_topics(self):
        from .study_plan import MAX_TOPICS, topic_lines
        text = self.cleaned_data['topics']
        if re.search('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]', text):
            raise forms.ValidationError('Remove the hidden control characters from your topics.')
        lines = topic_lines(text)
        if not lines:
            raise forms.ValidationError('Type at least one topic.')
        if len(lines) > MAX_TOPICS:
            raise forms.ValidationError(f'Use at most {MAX_TOPICS} topics ({len(lines)} were typed).')
        if any(len(line) > 200 for line in lines):
            raise forms.ValidationError('Keep each topic to 200 characters or fewer.')
        return lines


class TopicForm(StrictForm):
    title = forms.CharField(max_length=200, label='Add a topic', help_text='It goes on the last study day; use '
                            '"Re-plan from today" to share topics out again.')

    def clean_title(self):
        title = ' '.join(self.cleaned_data['title'].split())
        if not title:
            raise forms.ValidationError('Type a topic.')
        if re.search('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]', title):
            raise forms.ValidationError('Remove the hidden control characters from the topic.')
        return title


class VersionForm(StrictForm):
    version = forms.IntegerField(min_value=1, max_value=2**63 - 2, widget=forms.HiddenInput())


class TopicDoneForm(VersionForm):
    done = forms.TypedChoiceField(coerce=lambda value: value == 'true', choices=[('true', 'Done'), ('false', 'Not done')],
                                  widget=forms.HiddenInput())


class MaterialUploadForm(StrictForm):
    title = forms.CharField(max_length=200, label='Material title', help_text='For example, Week 3 lecture notes.')
    course_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Course', help_text='Only your courses are available.')
    file = forms.FileField(max_length=255, label='File',
                           help_text='PDF or UTF-8 TXT, up to 10 MiB. The file is checked, then stored privately for you.')

    def __init__(self, *args, courses, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course_id'].choices = [('', 'Choose a course')] + [(str(c.pk), f'{c.normalized_code} · {c.name}') for c in courses]
        self.fields['file'].help_text = (f'PDF or UTF-8 TXT, up to {describe_size(upload_cap())}. '
                                         'The file is checked, then stored privately for you.')
        self.file_facts = None
        self.file_content = None

    def clean(self):
        values = super().clean()
        upload = values.get('file')
        if upload is None:
            return values
        try:
            limit = upload_cap()
            extension = validate_upload_metadata(upload.name, upload.size, limit)
            upload.seek(0)
            content = upload.read(limit + 1)
            validate_upload_metadata(upload.name, len(content), limit)
            if extension == '.pdf':
                validate_pdf_content(content)
            else:
                validate_text_content(content)
        except ValueError as error:
            self.add_error('file', str(error))
            return values
        self.file_facts = {'original_filename': upload.name, 'file_type': extension[1:], 'size_bytes': len(content)}
        self.file_content = content
        return values


def versioned(form):
    form.fields['version'] = forms.IntegerField(min_value=1, max_value=2**63 - 2, widget=forms.HiddenInput())
    return form


class AccountDeleteForm(StrictForm):
    """Launch step F: delete the whole account. The password and a typed word guard against mistakes."""
    password = forms.CharField(label='Your password', strip=False, max_length=128,
                               widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    confirm = forms.CharField(label='Type DELETE to confirm', max_length=10,
                              help_text='In capital letters. This cannot be undone.',
                              widget=forms.TextInput(attrs={'autocomplete': 'off', 'spellcheck': 'false',
                                                            'autocapitalize': 'characters'}))

    def clean_confirm(self):
        if self.cleaned_data['confirm'].strip() != 'DELETE':
            raise forms.ValidationError('Type DELETE in capital letters to confirm.')
        return 'DELETE'


class EmailChangeForm(StrictForm):
    """Launch step F, part 2: ask for a code at the new address. The password guards the account."""
    password = forms.CharField(label='Your password', strip=False, max_length=128,
                               widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    new_email = forms.EmailField(label='New email address', max_length=254,
                                 widget=forms.EmailInput(attrs={'autocomplete': 'email'}))

    def clean_new_email(self):
        value = self.cleaned_data['new_email'].strip().lower()
        if not value.isascii():
            raise forms.ValidationError('Use an ASCII email address.')
        return value


class EmailChangeCodeForm(StrictForm):
    code = forms.CharField(label='6-digit code', max_length=12,
                           help_text='From the email we sent to your new address. It works for 10 minutes.',
                           widget=forms.TextInput(attrs={'autocomplete': 'one-time-code', 'inputmode': 'numeric',
                                                         'spellcheck': 'false'}))


class DeleteForm(StrictForm):
    version = forms.IntegerField(min_value=1, max_value=2**63 - 2, widget=forms.HiddenInput())
    confirm = forms.BooleanField(label='I confirm I want to delete this record')


class ProfileForm(StrictForm):
    display_name = forms.CharField(max_length=80, required=False, label='Display name',
                                   help_text='How the app greets you. Leave blank to use your username.')
    institution = forms.CharField(max_length=150, required=False, label='University or institution')
    programme = forms.CharField(max_length=150, required=False, label='Programme',
                                help_text='For example, B.Sc. Computer Science.')
    level = forms.ChoiceField(required=False, label='Current level', choices=[('', 'Not set')] + LEVEL_CHOICES)
    matric_number = forms.RegexField(MATRIC_PATTERN, max_length=32, required=False, label='Matric / student ID number',
                                     help_text='Only you can see this. Letters, digits and / . _ - only.',
                                     error_messages={'invalid': 'Use letters, digits and / . _ - only.'})

    def clean(self):
        values = super().clean()
        for name in ('display_name', 'institution', 'programme'):
            if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in values.get(name) or ''):
                self.add_error(name, 'Remove unsupported control characters.')
        return values


class GradingScaleForm(StrictForm):
    """Settings: the 4- or 5-point scale. `version` is the profile's (empty when there is none yet)."""
    scale = forms.ChoiceField(label='Grade scale', choices=GRADING_SCALES)
    version = forms.IntegerField(required=False, min_value=1, max_value=2**63 - 2, widget=forms.HiddenInput())


class DisplayForm(StrictForm):
    theme = forms.ChoiceField(label='Display', widget=forms.RadioSelect, choices=[
        ('system', 'System (follow this device)'), ('light', 'Light'), ('dark', 'Dark')])


class StatusForm(StrictForm):
    version = forms.IntegerField(min_value=1, max_value=2**63 - 2, widget=forms.HiddenInput())
    completed = forms.ChoiceField(choices=[('true', 'Complete'), ('false', 'Pending')])


class PageForm(StrictForm):
    page = forms.IntegerField(min_value=1, max_value=10000, required=False, widget=forms.HiddenInput())


class SemesterFilter(PageForm):
    semester = forms.ChoiceField(required=False, label='Semester')

    def __init__(self, *args, semesters, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['semester'].choices = [('', 'All semesters')] + [(str(s.pk), f'{i}. {s.label}') for i, s in enumerate(semesters, 1)]


class CourseFilter(SemesterFilter):
    q = forms.CharField(required=False, max_length=80, label='Search courses',
                        help_text='Search course code or name. Up to 80 characters.',
                        widget=forms.TextInput(attrs={'type': 'search'}))


class AssignmentFilter(PageForm):
    q = forms.CharField(required=False, max_length=80, label='Search assignments',
                        help_text='Search title, course code or course name. Up to 80 characters.',
                        widget=forms.TextInput(attrs={'type': 'search'}))
    status = forms.ChoiceField(required=False, choices=[('all', 'All assignments'), ('pending', 'Pending'),
                    ('completed', 'Completed'), ('upcoming', 'Upcoming'), ('overdue', 'Overdue')])
    sort = forms.ChoiceField(required=False, label='Sort by deadline', choices=[('due', 'Earliest first'), ('latest', 'Latest first')])


class PredictorForm(StrictForm):
    def __init__(self, *args, courses, policy=LEGACY_POLICY, **kwargs):
        if len(courses) > MAX_PREDICTION_COURSES:
            raise WorkspaceLimit('The predictor supports 200 courses at a time. Choose a semester to narrow the selection.')
        super().__init__(*args, **kwargs)
        for course in courses:
            self.fields['grade_' + course.pk.hex] = forms.ChoiceField(
                required=False, label=f'{course.normalized_code} · {course.name}',
                help_text=f'{course.credit_units.normalize():f} credits · hypothetical only',
                choices=[('', 'Do not include')] + [(g, g) for g in policy.grade_points])

    def clean(self):
        values = super().clean()
        if not any(values.values()):
            raise forms.ValidationError('Select at least one course and choose its hypothetical grade.')
        return values


class PlannerForm(StrictForm):
    target = forms.DecimalField(label='Target final CGPA', min_value=0, max_value=5, max_digits=5, decimal_places=4,
                                initial='4.0000', help_text='0–5, with at most four decimal places.')
    remaining = forms.DecimalField(label='Remaining credit units', min_value=Decimal('0.0001'), max_value=Decimal('1000000'),
                                   max_digits=11, decimal_places=4, initial='30',
                                   help_text='Include all remaining credits, including currently ungraded courses. No graduation policy is inferred.')

    def __init__(self, *args, policy=LEGACY_POLICY, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = policy
        scaled_decimal(self, 'target', policy, f'0–{policy.maximum}, with at most four decimal places.')

    def clean_target(self):
        try:
            return checked_target(self.cleaned_data['target'], policy=self.policy)
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error

    def clean_remaining(self):
        try:
            return checked_credits(self.cleaned_data['remaining'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error


class ClassBandsForm(StrictForm):
    """The student's own class-of-degree bands: the lowest CGPA for each class."""
    FIELDS = ("first_class_min", "second_upper_min", "second_lower_min", "third_class_min", "pass_min")

    def __init__(self, *args, policy=LEGACY_POLICY, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = policy
        for name, label in zip(self.FIELDS, CLASS_NAMES):
            self.fields[name] = forms.DecimalField(label=f'{label}: lowest CGPA', min_value=0, max_value=policy.maximum,
                                                   max_digits=5, decimal_places=4,
                                                   help_text=f'0–{policy.maximum}, at most four decimal places.')

    def clean(self):
        values = super().clean()
        if not self.errors:
            try:
                bands = checked_bands([values[name] for name in self.FIELDS], policy=self.policy)
            except ValueError as error:
                raise forms.ValidationError(str(error)) from error
            values.update(zip(self.FIELDS, bands))
        return values


class AimForm(StrictForm):
    """Planner shortcut: ?aim=0..4 fills the target with that class's lowest CGPA."""
    aim = forms.TypedChoiceField(choices=[(str(i), name) for i, name in enumerate(CLASS_NAMES)], coerce=int)


class ProjectionForm(StrictForm):
    """Graduation predictor: the student supplies the remaining credits and an expected average."""
    expected = forms.DecimalField(label='Expected average for your remaining credits', min_value=0, max_value=5,
                                  max_digits=5, decimal_places=4, initial='4.0000',
                                  help_text='The GPA you expect to average from now on: 0–5, at most four decimal places.')
    remaining = forms.DecimalField(label='Remaining credit units', min_value=Decimal('0.0001'), max_value=Decimal('1000000'),
                                   max_digits=11, decimal_places=4, initial='30',
                                   help_text='Include all remaining credits, including currently ungraded courses.')

    def __init__(self, *args, policy=LEGACY_POLICY, **kwargs):
        kwargs.setdefault('auto_id', 'projection_%s')  # unique IDs beside the target form
        super().__init__(*args, **kwargs)
        self.policy = policy
        scaled_decimal(self, 'expected', policy, 'The GPA you expect to average from now on: '
                       f'0–{policy.maximum}, at most four decimal places.')

    def clean_expected(self):
        try:
            return checked_target(self.cleaned_data['expected'], policy=self.policy)
        except ValueError as error:
            raise forms.ValidationError(str(error).replace('Target CGPA', 'The expected average')) from error

    def clean_remaining(self):
        try:
            return checked_credits(self.cleaned_data['remaining'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error


AI_TOOL_CHOICES = [("summary", "Summary"), ("quiz", "Quiz"), ("flashcards", "Flashcards"),
                   ("answer", "Ask a question")]


class MaterialSearchForm(StrictForm):
    """Words to find in the student's own study files: taken literally, any letter case."""
    q = forms.CharField(label='Search your study files', min_length=2, max_length=100,
                        help_text='2 to 100 characters. Finds these exact words in any letter case.')

    def clean_q(self):
        words = ' '.join(self.cleaned_data['q'].split())
        if re.search('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]', words):
            raise forms.ValidationError('Remove the hidden control characters from your search.')
        if len(words) < 2:
            raise forms.ValidationError('Type at least 2 characters.')
        return words


class AiToolForm(StrictForm):
    """Choose a tool (and a question for "Ask a question"). Posting this never sends anything."""
    tool = forms.ChoiceField(choices=AI_TOOL_CHOICES, widget=forms.RadioSelect, label='Study tool')
    question = forms.CharField(max_length=500, required=False, label='Your question',
                               widget=forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
                               help_text='Only for "Ask a question". Up to 500 characters.')
    # Sent only by the buttons on the confirm page that hide or show the "Before you send" notes.
    notes = forms.ChoiceField(choices=[('', ''), ('hide', 'Hide'), ('show', 'Show')], required=False,
                              widget=forms.HiddenInput())

    def clean(self):
        values = super().clean()
        tool, question = values.get('tool'), (values.get('question') or '').strip()
        if re.search('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]', question):
            self.add_error('question', 'Remove the hidden control characters from your question.')
        elif tool == 'answer' and not question:
            self.add_error('question', 'Type the question you want answered.')
        elif tool and tool != 'answer' and question:
            self.add_error('question', 'Questions are only used with "Ask a question". Clear this box or '
                                       'choose that tool.')
        values['question'] = question
        return values


class AiSendForm(AiToolForm):
    """The confirm page's Send form: the same choice, the consent token and the provider."""
    token = forms.CharField(max_length=400, widget=forms.HiddenInput())
    provider = forms.ChoiceField(choices=[])

    def __init__(self, *args, providers, **kwargs):
        from .ai_providers import PUBLIC_CODES
        super().__init__(*args, **kwargs)
        # The page posts a neutral code ("main" or "backup"); the internal name is also accepted.
        self.fields['provider'].choices = ([(PUBLIC_CODES[code], code) for code in providers]
                                           + [(code, code) for code in providers])
        for name in ('tool', 'question'):
            self.fields[name].widget = forms.HiddenInput()

    def clean_provider(self):
        from .ai_providers import INTERNAL_CODES
        value = self.cleaned_data['provider']
        return INTERNAL_CODES.get(value, value)


class ConfirmDeleteForm(StrictForm):
    confirm = forms.BooleanField(label='I confirm I want to delete this result')

