"""Deadline reminders: the dashboard's "Due this week" section and the counts for the optional
pop-up (numbers only, never titles). Synthetic records; "today" is fixed for the test."""
import json
import re
from datetime import date, timedelta
from unittest.mock import patch
from django.urls import reverse
from academics import services
from student_web.data import due_this_week
from .base import WebsiteCase

TODAY = date(2026, 11, 18)  # a Wednesday


class ReminderTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()  # task_a: due 2026-11-11 (overdue on TODAY)
        add = lambda title, days, done=False: services.assignments.create(
            self.identity_a, course_id=self.course_a.pk, title=title, due_date=TODAY + timedelta(days=days),
            completed=done)
        add('Synthetic due today', 0)
        add('Synthetic due tomorrow one', 1)
        add('Synthetic due tomorrow two', 1)
        add('Synthetic due in six days', 6)
        add('Synthetic due in seven days', 7)  # outside the week
        add('Synthetic done today', 0, done=True)  # completed: never listed
        other = services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='TWO',
                                        name='Synthetic second course', credit_units=2)
        services.assignments.create(self.identity_a, course_id=other.pk, title='Synthetic two tomorrow',
                                    due_date=TODAY + timedelta(days=1))

    def dashboard(self, client=None):
        with patch('student_web.views.timezone.localdate', return_value=TODAY):
            return (client or self.client_a).get(reverse('student_web:dashboard'))

    def test_due_this_week_shows_each_day_with_counts_and_courses(self):
        page = self.dashboard()
        html = page.content.decode()
        self.assertContains(page, '<h2 id="week-title">Due this week</h2>', html=False)
        self.assertContains(page, '5 pending assignments due in the next 7 days')
        week = html.split('id="week-title"')[1].split('</section>')[0]
        self.assertIn('<time datetime="2026-11-18">Today</time>', week)
        self.assertIn('<time datetime="2026-11-19">Tomorrow</time>', week)
        self.assertIn('<time datetime="2026-11-20">Fri 20 Nov</time>', week)
        days = week.split('<li class="week-day')[1:]
        self.assertEqual(len(days), 7)
        self.assertIn('1 due<span>ONE</span>', days[0])
        self.assertIn('3 due<span>ONE, TWO</span>', days[1])
        self.assertIn('Nothing due', days[2])
        self.assertIn('1 due<span>ONE</span>', days[6])
        # Titles stay in "Upcoming deadlines"; nothing past the week, completed or overdue is counted.
        for absent in ('Synthetic due in six days', 'Synthetic due in seven days', 'Synthetic done today',
                       'Synthetic A task'):
            self.assertNotIn(absent, week)

    def test_pop_up_counts_hold_numbers_only(self):
        page = self.dashboard()
        counts = json.loads(page.content.decode().split('id="ucc-due-soon" type="application/json">')[1]
                            .split('</script>')[0])
        self.assertEqual(counts, {'date': '2026-11-18', 'today': 1, 'tomorrow': 3, 'week': 5})

    def test_other_students_never_see_these(self):
        page = self.dashboard(self.client_b)
        self.assertNotContains(page, 'Synthetic due today')
        self.assertContains(page, 'Nothing due in the next 7 days.')

    def test_settings_explains_the_pop_ups_without_javascript(self):
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, '<h2 id="reminders-heading">Deadline pop-ups</h2>', html=False)
        self.assertContains(page, 'never titles')
        self.assertContains(page, 'data-reminders hidden')
        self.assertContains(page, 'Pop-ups need JavaScript in this browser.')


class ReminderScriptTests(WebsiteCase):
    def test_script_is_small_local_and_stores_no_records(self):
        from pathlib import Path
        static = Path(__file__).resolve().parents[1] / 'student_web/static/student_web'
        script = (static / 'reminders.js').read_text()
        self.assertLessEqual(len(script.encode()), 5_000)
        self.assertIn('Source: frontend/src/reminders.ts', script)
        for forbidden in ('fetch(', 'XMLHttpRequest', 'innerHTML', 'document.cookie', 'http://', 'https://'):
            self.assertNotIn(forbidden, script)
        # Browser storage is written in one place, with one of two keys: a preference and a date.
        self.assertEqual(script.count('localStorage.setItem'), 1)
        self.assertEqual(re.findall(r"const (PREFERENCE|LAST_SHOWN) = '([a-z-]+)'", script),
                         [('PREFERENCE', 'ucc-reminders'), ('LAST_SHOWN', 'ucc-reminded-on')])
        self.assertEqual(len(re.findall(r'write\((PREFERENCE|LAST_SHOWN),', script)), 3)
        self.assertEqual(len(re.findall(r'write\(', script)), 3 + 1)  # three uses and the definition
        self.assertLessEqual(len((static / 'week.css').read_bytes()), 2_500)
        self.assertIn("'reminders.js'", (static / 'site.js').read_text())


class WeekShapeTests(WebsiteCase):
    def test_more_than_fifty_is_flagged_not_hidden(self):
        course = type('Course', (), {'normalized_code': 'SYN'})()
        items = [type('Task', (), {'due_date': TODAY, 'title': f'T{n}', 'course': course})() for n in range(51)]
        week = due_this_week(items, TODAY)
        self.assertEqual((week['total'], week['more'], len(week['days'][0]['items'])), (50, True, 50))
        self.assertEqual([day['label'] for day in week['days']][:3], ['Today', 'Tomorrow', 'Fri 20 Nov'])
