import uuid
from decimal import Decimal
from django import forms
from academic_logic import checked_credits, checked_target, checked_grade, GRADE_POINTS
from academics.models import Course
from academics.queries import MAX_PREDICTION_COURSES, WorkspaceLimit
from .upload_validation import MAX_UPLOAD_BYTES, validate_pdf_content, validate_text_content, validate_upload_metadata

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

    def __init__(self, *args, semesters, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['semester_id'].choices = [('', 'Choose a semester')] + [(str(s.pk), f'{i}. {s.label}') for i, s in enumerate(semesters, 1)]

    def clean_credit_units(self):
        try:
            return checked_credits(self.cleaned_data['credit_units'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error

    def clean_actual_grade(self):
        return checked_grade(self.cleaned_data['actual_grade'])


class AssignmentForm(StrictForm):
    title = forms.CharField(max_length=240, label='Assignment title')
    course_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Course', help_text='Only your courses are available. The assignment stays linked if its course code changes.')
    due_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'), input_formats=['%Y-%m-%d'],
                               help_text='Deadlines use the Africa/Lagos calendar date. Overdue tasks stay in your records.')
    completed = forms.BooleanField(required=False, label='This assignment is complete')

    def __init__(self, *args, courses, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course_id'].choices = [('', 'Choose a course')] + [(str(c.pk), f'{c.normalized_code} · {c.name}') for c in courses]

class MaterialUploadForm(StrictForm):
    title = forms.CharField(max_length=200, label='Material title', help_text='For example, Week 3 lecture notes.')
    course_id = forms.TypedChoiceField(coerce=uuid.UUID, label='Course', help_text='Only your courses are available.')
    file = forms.FileField(max_length=255, label='File',
                           help_text='PDF or UTF-8 TXT, up to 10 MiB. The file is checked, then stored privately for you.')

    def __init__(self, *args, courses, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course_id'].choices = [('', 'Choose a course')] + [(str(c.pk), f'{c.normalized_code} · {c.name}') for c in courses]
        self.file_facts = None
        self.file_content = None

    def clean(self):
        values = super().clean()
        upload = values.get('file')
        if upload is None:
            return values
        try:
            extension = validate_upload_metadata(upload.name, upload.size)
            upload.seek(0)
            content = upload.read(MAX_UPLOAD_BYTES + 1)
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


class DeleteForm(StrictForm):
    version = forms.IntegerField(min_value=1, max_value=2**63 - 2, widget=forms.HiddenInput())
    confirm = forms.BooleanField(label='I confirm I want to delete this record')


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
    def __init__(self, *args, courses, **kwargs):
        if len(courses) > MAX_PREDICTION_COURSES:
            raise WorkspaceLimit('The predictor supports 200 courses at a time. Choose a semester to narrow the selection.')
        super().__init__(*args, **kwargs)
        for course in courses:
            self.fields['grade_' + course.pk.hex] = forms.ChoiceField(
                required=False, label=f'{course.normalized_code} · {course.name}',
                help_text=f'{course.credit_units.normalize():f} credits · hypothetical only',
                choices=[('', 'Do not include')] + [(g, g) for g in GRADE_POINTS])

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

    def clean_target(self):
        try:
            return checked_target(self.cleaned_data['target'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error

    def clean_remaining(self):
        try:
            return checked_credits(self.cleaned_data['remaining'])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error
