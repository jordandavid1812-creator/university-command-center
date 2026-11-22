"""Study streak on the dashboard (owner's choice): worked out from what the student already does
(AI tools, saved mistakes, ticked study topics, completed assignments, uploaded notes). Nothing new
is stored and the dashboard makes no extra database reads. Synthetic data only."""
from datetime import date, timedelta
from django.db import connections
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from academics import queries, services
from student_web.data import study_streak
from .base import WebsiteCase

TODAY = date(2026, 11, 22)


def days(*offsets):
    return {TODAY - timedelta(days=offset) for offset in offsets}


class StreakMathTests(SimpleTestCase):
    def test_counts_back_from_today(self):
        streak = study_streak(days(0, 1, 2, 4), TODAY)
        self.assertEqual((streak['current'], streak['today_done'], streak['best']), (3, True, 3))

    def test_a_streak_stays_alive_until_today_ends(self):
        streak = study_streak(days(1, 2), TODAY)
        self.assertEqual((streak['current'], streak['today_done']), (2, False))

    def test_a_missed_day_ends_it_but_the_best_is_remembered(self):
        streak = study_streak(days(2, 3, 4, 5, 6), TODAY)
        self.assertEqual((streak['current'], streak['best'], streak['any']), (0, 5, True))

    def test_nothing_yet(self):
        streak = study_streak(set(), TODAY)
        self.assertEqual((streak['current'], streak['best'], streak['any'], streak['active_week']), (0, 0, False, 0))

    def test_the_week_row_has_seven_days_ending_today(self):
        week = study_streak(days(0, 3), TODAY)['week']
        self.assertEqual([d['date'] for d in week], [TODAY - timedelta(days=n) for n in range(6, -1, -1)])
        self.assertEqual([d['active'] for d in week], [False, False, False, True, False, False, True])
        self.assertTrue(week[-1]['today'])
        self.assertEqual(study_streak(days(0, 3), TODAY)['active_week'], 2)

    def test_future_days_are_ignored(self):
        self.assertEqual(study_streak({TODAY + timedelta(days=1)}, TODAY)['current'], 0)


class DashboardStreakTests(WebsiteCase):
    def dashboard(self, client=None):
        return (client or self.client_a).get(reverse('student_web:dashboard'))

    def test_a_new_student_is_invited_to_start(self):
        self.login()
        page = self.dashboard()
        self.assertContains(page, 'Start a study streak')
        self.assertContains(page, 'Study days this week: 0 of 7')
        self.assertContains(page, '/static/student_web/getting_started.css')

    def test_completing_an_assignment_today_starts_a_streak_for_that_student_only(self):
        self.seed()
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, completed=True)
        page = self.dashboard()
        self.assertContains(page, '1-day study streak')
        self.assertContains(page, 'You studied today.')
        self.assertContains(page, 'Study days this week: 1 of 7')
        self.assertContains(self.dashboard(self.client_b), 'Start a study streak')

    def test_activity_comes_from_the_dashboards_existing_reads(self):
        self.seed()
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, completed=True)
        with CaptureQueriesContext(connections['runtime']) as captured:
            result = queries.dashboard_reads(self.identity_a, date.today())
        studied, started = result[-2], result[-1]
        self.assertEqual(started, {'materials': False, 'classes': False})
        self.assertEqual(len(studied), 1)
        statements = [query['sql'] for query in captured.captured_queries]
        self.assertEqual(sum('UNION ALL' in sql for sql in statements), 1)  # still one checklist query
        self.assertEqual(sum('FROM "academics_studyai' in sql for sql in statements), 2)  # unchanged
        self.assertEqual(sum('ucc_security.current_student()' in sql for sql in statements), 1)

    def test_the_card_explains_what_counts_and_works_without_javascript(self):
        self.login()
        html = self.dashboard().content.decode()
        self.assertIn('A study day is any day you use an AI study tool', html)
        self.assertIn('<section class="panel study-streak', html)
        self.assertNotIn('<script>', html[html.index('study-streak'):html.index('</section>', html.index('study-streak'))])
