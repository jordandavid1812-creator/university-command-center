"""Browser checks for a study plan page: done, overdue, revision and exam days stay readable
(4.5:1) in light and dark, it fits phones, and ticking a topic is a plain form (no JavaScript)."""
from datetime import date, timedelta
import os
import sys
from types import SimpleNamespace as NS
import unittest
import uuid

import test_frontend_foundation_browser as foundation
import test_redesign_browser as redesign
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve
from playwright.sync_api import sync_playwright

OUTPUT = redesign.OUTPUT
TODAY = date(2026, 11, 20)


def plan_html():
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from student_web import forms
    from student_web.data import plan_days
    request = RequestFactory().get('/study-planner/x/')
    request.resolver_match = resolve(f'/study-planner/{uuid.UUID(int=1)}/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    plan = NS(pk=uuid.UUID(int=1), exam_date=TODAY + timedelta(days=4), review_days=1, record_version=3,
              course=NS(normalized_code='CSC201', name='Synthetic computer networks'))
    titles = ['OSI model', 'TCP and UDP', 'IP addressing with a long synthetic topic name for wrapping', 'Routing']
    topics = [NS(pk=uuid.UUID(int=10 + n), title=title, position=n, record_version=1, done=n == 0, plan_id=plan.pk,
                 planned_date=TODAY + timedelta(days=n - 2)) for n, title in enumerate(titles)]
    context.update(request=request, csrf_token='synthetic', messages=[], plan=plan, today=TODAY,
                   topic_form=forms.TopicForm(), **plan_days(plan, topics, TODAY))
    return render_to_string('student_web/study_plan.html', context)


class StudyPlannerBrowserTests(unittest.TestCase):
    page = redesign.RedesignBrowserTests.page

    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {'plan': plan_html()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def test_every_kind_of_day_and_topic_is_readable(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('plan', motion='reduce', scheme=scheme)
                redesign.RedesignBrowserTests.assert_scheme(self, page, scheme)
                self.assertEqual(page.locator('.plan-topic.is-done').count(), 1)
                self.assertEqual(page.locator('.plan-topic.is-overdue').count(), 1)
                for selector in ('.plan-topic.is-done .plan-title', '.plan-topic.is-overdue .plan-title', '.plan-flag',
                                 '.plan-day.is-review p', '.plan-day.is-exam p', '.plan-remove-button',
                                 '.plan-topic:not(.is-done) .plan-title'):
                    colours = foundation.FoundationBrowserTests.painted_colors(self, page.locator(selector).first)
                    self.assertGreaterEqual(redesign.contrast(colours), 4.5, (selector, colours))
                done = page.locator('.plan-topic.is-done .plan-box')
                self.assertGreaterEqual(redesign.contrast(foundation.FoundationBrowserTests.painted_colors(self, done)), 4.5)
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'study-plan-{scheme}.png'), full_page=True)

    def test_phones_and_no_javascript(self):
        for width in (320, 390):
            with self.subTest(width=width):
                page = self.page('plan', motion='reduce', width=width)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
        # Each day appears once: 23 Nov is the revision day only, not also an empty study day.
        page = self.page('plan', motion='reduce')
        self.assertEqual(page.locator('.plan-day time[datetime="2026-11-23"]').count(), 1)
        self.assertEqual(page.locator('.plan-day.is-review').count(), 1)
        page = self.page('plan', javascript=False)
        check = page.locator('.plan-check').first
        self.assertEqual(check.evaluate('b => b.form.method'), 'post')
        self.assertEqual(check.evaluate('b => b.form.querySelector("[name=done]").value'), 'false')  # done: untick
        self.assertGreaterEqual(check.bounding_box()['height'], 44)


if __name__ == '__main__':
    unittest.main()
