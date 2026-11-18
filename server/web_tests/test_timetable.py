"""Timetable: add, edit and delete weekly classes through the shared record pages; the weekly view
with clash warnings; today's classes on the dashboard; owner-only; included in the data export."""
import json
from datetime import date, datetime, time
from unittest.mock import patch
from django.urls import reverse
from django.utils import timezone
from academics import services
from .base import WebsiteCase

WEDNESDAY = date(2026, 11, 18)


class TimetableTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.create_url = reverse('student_web:session-create')

    def add(self, weekday=2, start='08:00', end='10:00', kind='lecture', venue='LT1', client=None, course=None):
        return (client or self.client_a).post(self.create_url, {
            'course_id': str((course or self.course_a).pk), 'weekday': str(weekday), 'start_time': start,
            'end_time': end, 'kind': kind, 'venue': venue})

    def test_add_a_class_and_see_it_on_its_day(self):
        self.assertContains(self.client_a.get(self.create_url), '<h1>Add class</h1>', html=False)
        response = self.add()
        self.assertRedirects(response, reverse('student_web:timetable'), fetch_redirect_response=False)
        page = self.client_a.get(reverse('student_web:timetable'))
        self.assertContains(page, 'Class saved.')
        self.assertContains(page, '<h2>Wednesday', html=False)
        self.assertContains(page, '<time>08:00</time>–<time>10:00</time>', html=False)
        self.assertContains(page, 'Lecture · LT1')
        self.assertContains(page, '<strong>ONE</strong>', html=False)

    def test_bad_classes_are_refused(self):
        for values, field in (({'start': '10:00', 'end': '09:00'}, 'end_time'), ({'weekday': 7}, 'weekday'),
                              ({'kind': 'party'}, 'kind'), ({'start': '25:00'}, 'start_time')):
            with self.subTest(values=values):
                response = self.add(**values)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, f'href="#id_{field}"', status_code=400)
        other = self.add(course=self.course_b)  # B's course is not one of A's choices
        self.assertEqual(other.status_code, 400)
        self.assertEqual(services.class_sessions.list(self.identity_a), [])

    def test_overlapping_classes_are_marked(self):
        self.add(start='08:00', end='10:00')
        self.add(start='09:30', end='11:00', kind='tutorial')
        self.add(start='11:00', end='12:00', kind='lab')  # starts when the last ends: no clash
        page = self.client_a.get(reverse('student_web:timetable'))
        self.assertContains(page, '1 class overlaps another class on the same day.')
        self.assertContains(page, 'has-clash', count=1)

    def test_edit_and_delete_with_version_checks_and_owner_only(self):
        self.add()
        [item] = services.class_sessions.list(self.identity_a)
        edit = reverse('student_web:session-edit', args=[item.pk])
        self.assertContains(self.client_a.get(edit), 'value="08:00"')
        response = self.client_a.post(edit, {'course_id': str(self.course_a.pk), 'weekday': '4', 'start_time': '14:00',
                                             'end_time': '15:30', 'kind': 'tutorial', 'venue': 'Room 2', 'version': '1'})
        self.assertEqual(response.status_code, 302)
        item = services.class_sessions.retrieve(self.identity_a, item.pk)
        self.assertEqual((item.weekday, item.start_time, item.venue), (4, time(14), 'Room 2'))
        stale = self.client_a.post(edit, {'course_id': str(self.course_a.pk), 'weekday': '4', 'start_time': '14:00',
                                          'end_time': '15:30', 'kind': 'tutorial', 'venue': '', 'version': '1'})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client_b.get(edit).status_code, 404)
        delete = reverse('student_web:session-delete', args=[item.pk])
        self.assertContains(self.client_a.get(delete), 'ONE on Friday at 14:00')
        self.assertEqual(self.client_b.post(delete, {'version': '2', 'confirm': 'on'}).status_code, 404)
        self.assertEqual(self.client_a.post(delete, {'version': '2', 'confirm': 'on'}).status_code, 302)
        self.assertEqual(services.class_sessions.list(self.identity_a), [])

    def test_dashboard_shows_todays_classes_with_the_next_one_marked(self):
        self.add(weekday=2, start='08:00', end='09:00', venue='Early room')
        self.add(weekday=2, start='11:00', end='12:00', venue='Late room')
        self.add(weekday=3, start='08:00', end='09:00', venue='Thursday room')
        lagos = timezone.get_current_timezone()
        with patch('student_web.views.timezone.localdate', return_value=WEDNESDAY), \
                patch('student_web.views.timezone.localtime', return_value=datetime(2026, 11, 18, 10, 0, tzinfo=lagos)):
            page = self.client_a.get(reverse('student_web:dashboard'))
        today = page.content.decode().split('id="today-title"')[1].split('</section>')[0]
        self.assertIn('Early room', today)
        self.assertIn('Late room', today)
        self.assertNotIn('Thursday room', today)
        self.assertIn('class="is-over"', today)
        self.assertIn('<li class="is-next"><p class="timetable-time"><time>11:00</time>–<time>12:00</time> · Next', today)
        other = self.client_b.get(reverse('student_web:dashboard'))
        self.assertContains(other, 'No classes today.')
        self.assertNotContains(other, 'Early room')

    def test_menu_empty_state_and_export(self):
        page = self.client_a.get(reverse('student_web:timetable'))
        self.assertContains(page, 'aria-current="page">Timetable</a>', html=False)
        self.assertContains(page, 'No classes yet')
        self.add(venue='Export room')
        data = json.loads(self.client_a.get(reverse('student_web:data-export')).content)
        self.assertEqual([(c['day'], c['start'], c['end'], c['type'], c['venue']) for c in data['timetable']],
                         [('Wednesday', '08:00', '10:00', 'lecture', 'Export room')])
        self.assertEqual(json.loads(self.client_b.get(reverse('student_web:data-export')).content)['timetable'], [])
