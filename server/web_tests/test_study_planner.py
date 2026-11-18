"""Study planner pages: make a plan (topics spread before the exam, revision day kept), tick topics,
add and remove topics, re-plan from today, today's study on the dashboard, owner-only, export."""
import json
from datetime import date, timedelta
from unittest.mock import patch
from django.urls import reverse
from academics import services
from .base import WebsiteCase

TODAY = date(2026, 11, 18)
EXAM = TODAY + timedelta(days=6)  # study 18-22 Nov, revision 23 Nov, exam 24 Nov


class StudyPlannerTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()
        patcher = patch('student_web.views.timezone.localdate', return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make(self, topics="OSI model\nTCP\nUDP\nIP addressing\nRouting", exam=EXAM, review='1', client=None, course=None):
        return (client or self.client_a).post(reverse('student_web:study-plan-create'), {
            'course_id': str((course or self.course_a).pk), 'exam_date': exam.isoformat(), 'review_days': review,
            'topics': topics})

    def plan(self):
        [plan] = services.study_plans.list(self.identity_a)
        return plan

    def test_new_plan_spreads_topics_and_keeps_a_revision_day(self):
        response = self.make()
        plan = self.plan()
        self.assertRedirects(response, reverse('student_web:study-plan', args=[plan.pk]), fetch_redirect_response=False)
        topics = sorted(services.study_topics.list(self.identity_a), key=lambda t: t.position)
        self.assertEqual([t.planned_date for t in topics], [TODAY + timedelta(days=n) for n in range(5)])
        page = self.client_a.get(reverse('student_web:study-plan', args=[plan.pk]))
        self.assertContains(page, '<h1>ONE exam</h1>', html=False)
        self.assertContains(page, '6 days to go')
        self.assertContains(page, '<strong>0 of 5</strong> topics done', html=False)
        self.assertContains(page, '<strong>Revision day.</strong>', html=False)
        self.assertContains(page, '<strong>Exam day.</strong>', html=False)
        self.assertContains(page, 'Today · Wed 18 Nov')

    def test_bad_plans_are_refused(self):
        for values in ({'exam': TODAY}, {'exam': TODAY - timedelta(days=1)}, {'topics': '   \n  '},
                       {'topics': '\n'.join(f'T{n}' for n in range(61))}, {'review': '4'}, {'topics': 'x' * 201}):
            with self.subTest(values=values):
                self.assertEqual(self.make(**values).status_code, 400)
        self.assertEqual(self.make(course=self.course_b).status_code, 400)  # not A's course
        self.assertEqual(services.study_plans.list(self.identity_a), [])

    def test_tick_untick_remove_and_add_topics(self):
        self.make()
        plan = self.plan()
        topic = sorted(services.study_topics.list(self.identity_a), key=lambda t: t.position)[0]
        done = reverse('student_web:study-topic-done', args=[topic.pk])
        self.assertRedirects(self.client_a.post(done, {'version': '1', 'done': 'true'}),
                             reverse('student_web:study-plan', args=[plan.pk]) + f'#topic-{topic.pk}',
                             fetch_redirect_response=False)
        self.assertTrue(services.study_topics.retrieve(self.identity_a, topic.pk).done)
        self.assertEqual(self.client_a.post(done, {'version': '1', 'done': 'false'}).status_code, 409)  # stale tab
        self.assertEqual(self.client_b.post(done, {'version': '2', 'done': 'false'}).status_code, 404)
        self.assertContains(self.client_a.get(reverse('student_web:study-plan', args=[plan.pk])),
                            '<strong>1 of 5</strong> topics done (20%)', html=False)
        add = reverse('student_web:study-topic-add', args=[plan.pk])
        self.client_a.post(add, {'title': '  Subnetting  '})
        added = [t for t in services.study_topics.list(self.identity_a) if t.title == 'Subnetting']
        self.assertEqual([(t.planned_date, t.position) for t in added], [(TODAY + timedelta(days=4), 5)])
        self.assertEqual(self.client_b.post(add, {'title': 'Sneaky'}).status_code, 404)
        remove = reverse('student_web:study-topic-delete', args=[added[0].pk])
        self.assertEqual(self.client_a.post(remove, {'version': '1'}).status_code, 302)
        self.assertEqual(len(services.study_topics.list(self.identity_a)), 5)

    def test_missed_topics_are_overdue_and_replan_spreads_only_unfinished_ones(self):
        self.make()
        plan = self.plan()
        later = TODAY + timedelta(days=2)
        with patch('student_web.views.timezone.localdate', return_value=later):
            page = self.client_a.get(reverse('student_web:study-plan', args=[plan.pk]))
            self.assertContains(page, '2 overdue')
            self.assertContains(page, '<span class="plan-flag">Overdue</span>', count=2, html=False)
            response = self.client_a.post(reverse('student_web:study-plan-replan', args=[plan.pk]), {'version': '1'})
            self.assertEqual(response.status_code, 302)
        dates = [t.planned_date for t in sorted(services.study_topics.list(self.identity_a), key=lambda t: t.position)]
        # Five topics over the three study days left (20-22 Nov; 23 Nov stays for revision): 2, 2, 1.
        self.assertEqual(dates, [later, later, later + timedelta(days=1), later + timedelta(days=1),
                                 later + timedelta(days=2)])
        stale = self.client_a.post(reverse('student_web:study-plan-replan', args=[plan.pk]), {'version': '1'})
        self.assertEqual(stale.status_code, 409)

    def test_dashboard_lists_todays_and_overdue_study_only_for_the_owner(self):
        self.make()
        with patch('student_web.views.timezone.localdate', return_value=TODAY + timedelta(days=1)):
            page = self.client_a.get(reverse('student_web:dashboard'))
        study = page.content.decode().split('id="study-title"')[1].split('</section>')[0]
        self.assertIn('OSI model', study)
        self.assertIn('ONE · overdue', study)
        self.assertIn('TCP', study)
        self.assertNotIn('UDP', study)
        other = self.client_b.get(reverse('student_web:dashboard'))
        self.assertContains(other, 'Nothing to study today.')
        self.assertNotContains(other, 'OSI model')

    def test_list_menu_delete_and_export(self):
        page = self.client_a.get(reverse('student_web:study-plans'))
        self.assertContains(page, 'aria-current="page">Study planner</a>', html=False)
        self.assertContains(page, 'No study plans yet')
        self.make()
        plan = self.plan()
        self.assertContains(self.client_a.get(reverse('student_web:study-plans')), '<strong>0 of 5</strong> topics done',
                            html=False)
        data = json.loads(self.client_a.get(reverse('student_web:data-export')).content)
        self.assertEqual([t['title'] for t in data['study_plans'][0]['topics']],
                         ['OSI model', 'TCP', 'UDP', 'IP addressing', 'Routing'])
        delete = reverse('student_web:plan-delete', args=[plan.pk])
        self.assertContains(self.client_a.get(delete), 'the ONE study plan')
        self.assertEqual(self.client_b.get(delete).status_code, 404)
        self.assertEqual(self.client_a.post(delete, {'version': '1', 'confirm': 'on'}).status_code, 302)
        self.assertEqual(services.study_topics.list(self.identity_a), [])
