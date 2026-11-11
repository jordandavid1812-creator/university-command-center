from decimal import Decimal
from django.test import SimpleTestCase
from django.urls import reverse
from academic_logic import academic_summary, predicted_summary, target_plan
from academics import services
from student_web import data
from .base import WebsiteCase


class ExactEngineTests(SimpleTestCase):
    def test_decimal_credits_are_exact_without_changing_json_results(self):
        exact = [{'code': 'ONE', 'credit_units': Decimal('0.0001'), 'grade': 'A'},
                 {'code': 'TWO', 'credit_units': Decimal('3.1250'), 'grade': 'F'},
                 {'code': 'THREE', 'credit_units': Decimal('2'), 'grade': None}]
        result = academic_summary(exact)
        self.assertEqual(result['units'], Decimal('3.1251'))
        self.assertEqual(result['points'], Decimal('0.0005'))
        self.assertEqual((result['graded'], result['ungraded']), (2, 1))
        self.assertEqual(result['warnings'], [])
        json_style = [{**row, 'credit_units': float(row['credit_units'])} for row in exact]
        self.assertEqual(academic_summary(json_style), result)

    def test_invalid_decimal_and_boolean_records_remain_rejected(self):
        for value in (Decimal('0'), Decimal('NaN'), Decimal('3.00001'), True):
            result = academic_summary([{'code': 'BAD', 'credit_units': value, 'grade': 'A'}])
            self.assertEqual(result['graded'], 0)
            self.assertEqual(len(result['warnings']), 1)


class WebsiteCalculationTests(WebsiteCase):
    def test_weighted_overall_gpa_is_not_mean_of_semester_gpas(self):
        self.seed()
        second = services.semesters.create(self.identity_a, label='Second own term', display_order=1)
        services.courses.create(self.identity_a, semester_id=second.pk, original_code='FAIL', name='Synthetic F', credit_units=1, actual_grade='F')
        services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='WAIT', name='Ungraded', credit_units=6)
        response = self.client_a.get(reverse('student_web:overview'))
        summary = response.context['summary']
        self.assertEqual((summary['gpa'], summary['units'], summary['graded'], summary['ungraded']), (Decimal(3), Decimal(4), 2, 1))
        self.assertEqual([row['gpa'] for row in summary['semesters']], [Decimal(4), Decimal(0)])
        self.assertContains(response, '3.00')
        self.assertContains(response, '0.00')

    def test_duplicate_semester_labels_remain_distinct_engine_groups(self):
        self.seed()
        services.semesters.update(self.identity_a, self.sem_a.pk, version=1, label='Same label')
        second = services.semesters.create(self.identity_a, label='Same label', display_order=1)
        services.courses.create(self.identity_a, semester_id=second.pk, original_code='OTHER', name='Synthetic F', credit_units=1, actual_grade='F')
        summary = self.client_a.get(reverse('student_web:overview')).context['summary']
        self.assertEqual(len(summary['semesters']), 2)
        self.assertEqual([row['label'] for row in summary['semesters']], ['Same label', 'Same label'])
        self.assertNotEqual(summary['semesters'][0]['semester'], summary['semesters'][1]['semester'])
        self.assertEqual(summary['gpa'], 3)

    def test_explicit_display_order_not_course_creation_order(self):
        self.seed()
        services.semesters.update(self.identity_a, self.sem_a.pk, version=1, display_order=20)
        earlier = services.semesters.create(self.identity_a, label='Shown first', display_order=1)
        services.courses.create(self.identity_a, semester_id=earlier.pk, original_code='LATE', name='Created later', credit_units=1, actual_grade='A')
        summary = self.client_a.get(reverse('student_web:overview')).context['summary']
        self.assertEqual(summary['semesters'][0]['label'], 'Shown first')
        self.assertIsNone(self.client_a.get(reverse('student_web:dashboard')).context['current'])

    def test_database_adapter_keeps_decimal_values_and_minimum_credits(self):
        self.seed()
        services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='TINY', name='Exact tiny credits',
                                 credit_units=Decimal('0.0001'), actual_grade='A')
        snapshot = data.snapshot(self.identity_a)
        self.assertTrue(all(isinstance(row['credit_units'], Decimal) for row in snapshot['records']))
        self.assertEqual(snapshot['summary']['points'], Decimal('12.0005'))
        self.assertEqual(snapshot['summary']['units'], Decimal('3.0001'))

    def test_predictor_only_uses_selected_courses_and_never_writes_actuals(self):
        self.seed()
        extra = services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='SKIP', name='Not selected', credit_units=1, actual_grade='F')
        before = [(c.pk, c.actual_grade, c.record_version, c.updated_at) for c in services.courses.list(self.identity_a)]
        response = self.client_a.post(reverse('student_web:predictor'), {'grade_' + self.course_a.pk.hex: 'A', 'grade_' + extra.pk.hex: ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.context['result']['gpa'], response.context['result']['units']), (5, 3))
        self.assertContains(response, 'Hypothetical result')
        after = [(c.pk, c.actual_grade, c.record_version, c.updated_at) for c in services.courses.list(self.identity_a)]
        self.assertEqual(before, after)
        self.assertIsNone(self.client_a.get(reverse('student_web:predictor')).context['result'])
        self.assertFalse(any(str(key).startswith('grade_') for key in self.client_a.session.keys()))

    def test_prediction_requires_a_selection_and_rejects_invalid_grades(self):
        self.seed()
        path = reverse('student_web:predictor')
        self.assertEqual(self.client_a.post(path, {}).status_code, 400)
        self.assertEqual(self.client_a.post(path, {'grade_' + self.course_a.pk.hex: 'G'}).status_code, 400)
        foreign = self.client_a.post(path, {'grade_' + self.course_b.pk.hex: 'A'})
        self.assertEqual(foreign.status_code, 400)

    def test_predictor_semester_filter_and_engine_parity(self):
        self.seed()
        path = reverse('student_web:predictor') + '?semester=' + str(self.sem_a.pk)
        response = self.client_a.post(path, {'grade_' + self.course_a.pk.hex: 'C'})
        records = data.snapshot(self.identity_a)['records']
        expected = predicted_summary(records, {'ONE': 'C'})
        self.assertEqual(response.context['result']['gpa'], expected['gpa'])

    def test_planner_uses_exact_existing_engine_and_all_three_states(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='A')
        path = reverse('student_web:planner')
        response = self.client_a.post(path, {'target': '5.0000', 'remaining': '0.0001'})
        self.assertEqual((response.context['result']['status'], response.context['result']['required']), ('achievable', Decimal(5)))
        guaranteed = self.client_a.post(path, {'target': '3', 'remaining': '2'})
        self.assertEqual((guaranteed.context['result']['status'], guaranteed.context['result']['required']), ('guaranteed', Decimal(0)))
        services.courses.update(self.identity_a, self.course_a.pk, version=2, actual_grade='B')
        impossible = self.client_a.post(path, {'target': '5', 'remaining': '1'})
        self.assertEqual((impossible.context['result']['status'], impossible.context['result']['required']), ('impossible', Decimal(8)))
        expected = target_plan(data.snapshot(self.identity_a)['records'], '5', '1')
        self.assertEqual(impossible.context['result']['required'], expected['required'])

    def test_planner_validates_boundaries_and_does_not_save_inputs(self):
        self.seed()
        before = [(c.actual_grade, c.record_version) for c in services.courses.list(self.identity_a)]
        for target, remaining in (('5.0001', '3'), ('4', '0'), ('NaN', '3'), ('4', '0.00001'), ('4', '1000001')):
            response = self.client_a.post(reverse('student_web:planner'), {'target': target, 'remaining': remaining})
            self.assertEqual(response.status_code, 400)
            self.assertIsNone(response.context['result'])
        self.client_a.post(reverse('student_web:planner'), {'target': '4', 'remaining': '30'})
        self.assertEqual([(c.actual_grade, c.record_version) for c in services.courses.list(self.identity_a)], before)

    def test_planner_handles_new_student_without_inventing_current_gpa(self):
        self.login()
        response = self.client_a.post(reverse('student_web:planner'), {'target': '4', 'remaining': '30'})
        self.assertIsNone(response.context['summary']['gpa'])
        self.assertEqual(response.context['result']['required'], 4)
