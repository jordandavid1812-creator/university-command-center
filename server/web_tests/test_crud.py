from decimal import Decimal
import uuid
from django.urls import reverse
from django.utils import timezone
from academics import services
from .base import WebsiteCase


class WebsiteCrudTests(WebsiteCase):
    def test_semester_create_edit_order_and_delete(self):
        self.login()
        response = self.client_a.post(reverse('student_web:semester-create'), {'label': 'Synthetic new term', 'display_order': 4})
        self.assertEqual(response.status_code, 302)
        record = services.semesters.list(self.identity(self.client_a))[0]
        response = self.client_a.post(reverse('student_web:semester-edit', args=[record.pk]),
                                     {'label': 'Edited term', 'display_order': 0, 'version': 1})
        self.assertEqual(response.status_code, 302)
        record = services.semesters.retrieve(self.identity(self.client_a), record.pk)
        self.assertEqual((record.label, record.display_order, record.record_version), ('Edited term', 0, 2))
        self.assertEqual(self.client_a.get(reverse('student_web:semester-delete', args=[record.pk])).status_code, 200)
        self.assertEqual(len(services.semesters.list(self.identity(self.client_a))), 1)
        deleted = self.client_a.post(reverse('student_web:semester-delete', args=[record.pk]), {'version': 2, 'confirm': 'on'})
        self.assertEqual(deleted.status_code, 302)
        self.assertEqual(services.semesters.list(self.identity(self.client_a)), [])

    def course_fields(self, **changes):
        values = {'name': 'Synthetic new course', 'original_code': 'NEW101', 'credit_units': '3.1250',
                  'semester_id': str(self.sem_a.pk), 'actual_grade': ''}
        values.update(changes)
        return values

    def test_course_create_exact_credits_actual_grade_edit_code_and_semester(self):
        self.seed()
        self.assertEqual(self.client_a.post(reverse('student_web:course-create'), self.course_fields()).status_code, 302)
        record = next(c for c in services.courses.list(self.identity_a) if c.normalized_code == 'NEW101')
        self.assertEqual(record.credit_units, Decimal('3.1250'))
        self.assertIsNone(record.actual_grade)
        term = services.semesters.create(self.identity_a, label='Another own semester')
        response = self.client_a.post(reverse('student_web:course-edit', args=[record.pk]),
            self.course_fields(name='Edited course', original_code=' new102 ', credit_units='0.0001',
                               semester_id=str(term.pk), actual_grade='F', version=1))
        self.assertEqual(response.status_code, 302)
        record = services.courses.retrieve(self.identity_a, record.pk)
        self.assertEqual((record.normalized_code, record.actual_grade, record.credit_units, record.semester_id),
                         ('NEW102', 'F', Decimal('0.0001'), term.pk))
        self.assertEqual(self.client_a.post(reverse('student_web:course-delete', args=[record.pk]),
                                           {'version': 2, 'confirm': 'on'}).status_code, 302)

    def test_course_code_change_preserves_assignment_uuid_link(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:course-edit', args=[self.course_a.pk]),
                                     self.course_fields(original_code='CHANGED', actual_grade='B', version=1))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(services.assignments.retrieve(self.identity_a, self.task_a.pk).course_id, self.course_a.pk)
        self.assertContains(self.client_a.get(reverse('student_web:assignment-list')), 'CHANGED')

    def test_course_can_be_returned_to_genuinely_ungraded(self):
        self.seed()
        self.client_a.post(reverse('student_web:course-edit', args=[self.course_a.pk]),
                           self.course_fields(original_code='ONE', actual_grade='', version=1))
        self.assertIsNone(services.courses.retrieve(self.identity_a, self.course_a.pk).actual_grade)
        self.assertIsNone(self.client_a.get(reverse('student_web:overview')).context['summary']['gpa'])

    def test_duplicate_codes_are_clear_but_another_owner_can_use_same_code(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:course-create'), self.course_fields(original_code=' one '))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'already have a course with this code', status_code=400)
        self.assertEqual(len(services.courses.list(self.identity_a)), 1)
        self.assertEqual(len(services.courses.list(self.identity_b)), 1)

    def test_invalid_fields_are_labelled_and_preserve_submitted_values(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:course-create'),
                                     self.course_fields(name='Keep this text', credit_units='3.00001'))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Keep this text', status_code=400)
        self.assertContains(response, 'aria-invalid="true"', status_code=400)
        self.assertContains(response, 'id_credit_units_error', status_code=400)
        self.assertContains(response, 'id="error-summary"', status_code=400)
        for value in ('0', '-1', '1000000.0001', 'NaN', 'Infinity'):
            self.assertEqual(self.client_a.post(reverse('student_web:course-create'), self.course_fields(credit_units=value)).status_code, 400)

    def test_protected_deletes_have_understandable_errors(self):
        self.seed()
        for kind, record, message in (('semester', self.sem_a, 'still contains courses'),
                                       ('course', self.course_a, 'still has assignments')):
            response = self.client_a.post(reverse('student_web:' + kind + '-delete', args=[record.pk]),
                                          {'version': 1, 'confirm': 'on'})
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, message, status_code=400)

    def test_deletion_requires_explicit_confirmation(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:assignment-delete', args=[self.task_a.pk]), {'version': 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(services.assignments.retrieve(self.identity_a, self.task_a.pk).pk, self.task_a.pk)

    def test_assignment_create_edit_complete_pending_and_remove(self):
        self.seed()
        values = {'title': 'New assignment', 'course_id': self.course_a.pk,
                  'due_date': timezone.localdate().isoformat()}
        self.assertEqual(self.client_a.post(reverse('student_web:assignment-create'), values).status_code, 302)
        record = next(item for item in services.assignments.list(self.identity_a) if item.title == 'New assignment')
        values.update(title='Edited assignment', version=1)
        self.assertEqual(self.client_a.post(reverse('student_web:assignment-edit', args=[record.pk]), values).status_code, 302)
        self.assertEqual(self.client_a.post(reverse('student_web:assignment-status', args=[record.pk]),
                                           {'version': 2, 'completed': 'true'}).status_code, 302)
        self.assertTrue(services.assignments.retrieve(self.identity_a, record.pk).completed)
        self.assertEqual(self.client_a.post(reverse('student_web:assignment-status', args=[record.pk]),
                                           {'version': 3, 'completed': 'false'}).status_code, 302)
        self.assertFalse(services.assignments.retrieve(self.identity_a, record.pk).completed)
        self.assertEqual(self.client_a.post(reverse('student_web:assignment-delete', args=[record.pk]),
                                           {'version': 4, 'confirm': 'on'}).status_code, 302)

    def test_assignment_invalid_date_and_unknown_status_are_rejected(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:assignment-create'),
                                      {'title': 'Bad date', 'course_id': self.course_a.pk, 'due_date': '2026-02-30'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_a.post(reverse('student_web:assignment-status', args=[self.task_a.pk]),
                                           {'version': 1, 'completed': 'maybe'}).status_code, 400)

    def test_stale_edit_retains_user_input_and_does_not_overwrite(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, name='Saved in another tab')
        response = self.client_a.post(reverse('student_web:course-edit', args=[self.course_a.pk]),
                                     self.course_fields(name='Unsaved user input', version=1))
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'Unsaved user input', status_code=409)
        self.assertContains(response, 'Reload latest version', status_code=409)
        self.assertEqual(services.courses.retrieve(self.identity_a, self.course_a.pk).name, 'Saved in another tab')

    def test_stale_delete_and_status_do_not_silently_apply(self):
        self.seed()
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, title='Updated title')
        for name, values in (('assignment-delete', {'version': 1, 'confirm': 'on'}),
                              ('assignment-status', {'version': 1, 'completed': 'true'})):
            response = self.client_a.post(reverse('student_web:' + name, args=[self.task_a.pk]), values)
            self.assertEqual(response.status_code, 409)
        self.assertFalse(services.assignments.retrieve(self.identity_a, self.task_a.pk).completed)

    def test_semester_validation_and_course_required_grade_policy(self):
        self.login()
        self.assertEqual(self.client_a.post(reverse('student_web:semester-create'), {'label': ' ', 'display_order': -1}).status_code, 400)
        self.seed()
        self.assertEqual(self.client_a.post(reverse('student_web:course-create'), self.course_fields(actual_grade='G')).status_code, 400)
