"""UI2 synthetic real-template checks; runtime behavior is tested on PostgreSQL."""
import argparse
from datetime import date, timedelta
from decimal import Decimal
from importlib.metadata import version
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import uuid
import test_frontend_foundation_browser as foundation
from academic_logic import academic_summary
from student_web.data import present
from student_web.forms import SemesterFilter
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve
from playwright.sync_api import sync_playwright

ROOT = foundation.REPO
TODAY = date(2026, 11, 12)
SCENES = ('empty', 'semester-only', 'ungraded', 'zero', 'graded', 'mixed', 'overdue', 'long')


def html_for(scene):
    request = RequestFactory().get('/')
    request.resolver_match = resolve('/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='SyntheticStudentLongName1234567' if scene == 'long' else 'Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    semesters = [] if scene == 'empty' else [NS(pk=uuid.UUID(int=1), label='Synthetic semester', display_order=1)]
    courses = []
    if scene not in ('empty', 'semester-only'):
        grades = {'zero': ['F'], 'graded': ['A', 'B'], 'mixed': ['A', 'F', None]}.get(scene, [None])
        if scene == 'graded':
            semesters.append(NS(pk=uuid.UUID(int=2), label='Second synthetic semester', display_order=2))
        for index, grade in enumerate(grades):
            semester = semesters[index % len(semesters)]
            courses.append(NS(pk=uuid.UUID(int=20+index), semester_id=semester.pk, semester=semester,
                              normalized_code='SYN-'+str(index+1), name='Synthetic course',
                              credit_units=Decimal(3), actual_grade=grade))
    records = [dict(code=c.normalized_code, name=c.name, credit_units=c.credit_units,
                    grade=c.actual_grade, semester=str(c.semester_id)) for c in courses]
    summary = present(academic_summary(records), {str(s.pk): s for s in semesters})
    tasks = []
    if courses and scene != 'zero':
        for index in range(2 if scene == 'overdue' else 5):
            tasks.append(NS(pk=uuid.UUID(int=100+index), course=courses[0], completed=False,
                            title=('Synthetic long assignment ' + 'x'*160) if scene == 'long' else f'Synthetic assignment {index+1}',
                            due_date=TODAY+timedelta(days=-(index+1) if scene == 'overdue' else index)))
    totals = dict(total=len(tasks), pending=len(tasks), completed=0,
                  overdue=sum(t.due_date < TODAY for t in tasks))
    selector = SemesterFilter({'semester': str(semesters[0].pk)} if courses else {}, semesters=semesters)
    selector.is_valid()
    selected = selector.cleaned_data.get('semester')
    current = next((r for r in summary['semesters'] if r['semester'] == selected), None)
    context.update(request=request, csrf_token='synthetic-token', messages=[], semesters=semesters, courses=courses,
                   summary=summary, selector=selector, totals=totals,
                   upcoming=[t for t in tasks if t.due_date >= TODAY][:5], today=TODAY,
                   current=current, current_selected=bool(selected))
    html = render_to_string('student_web/dashboard.html', context)
    for name in ('site.css', 'dashboard.css'):
        html = html.replace(f'<link rel="stylesheet" href="/static/student_web/{name}">',
                            '<style>'+(ROOT/'server/student_web/static/student_web'/name).read_text()+'</style>')
    return html.replace('<script defer src="/static/student_web/site.js"></script>',
                        '<script>'+(ROOT/'server/student_web/static/student_web/site.js').read_text()+'</script>')


class DashboardBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        executable = os.environ.get('UCC_CHROMIUM_EXECUTABLE')
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=executable)
        cls.scenes = {s: html_for(s) for s in SCENES}
        print('Browser:', cls.browser.version, 'Playwright:', version('playwright'))
        if OUTPUT:
            (OUTPUT/'browser-metadata.json').write_text(json.dumps(dict(browser=cls.browser.version,
              executable=executable or 'Playwright-managed Chromium', playwright=version('playwright'),
              django=foundation.django.get_version(), fixtures='synthetic static records, real academic_summary; no live sessions'), indent=2)+'\n')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, scene='graded', width=1440, height=1000, text=100, javascript=True):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, java_script_enabled=javascript)
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        page = context.new_page()
        page.set_content(self.scenes[scene].replace('</head>', f'<style>html {{font-size:{text}%}}</style></head>'))
        return page

    def test_required_widths_states_and_evidence(self):
        for scene in SCENES:
            for width in (320, 360, 390, 768, 820, 1024, 1280, 1440):
                with self.subTest(scene=scene, width=width):
                    page = self.page(scene, width)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    self.assertEqual(page.locator('h1').count(), 1)
                    if width <= 1100:
                        selectors = ['#actual-cgpa-title', '#upcoming-title', '#selected-title', '#performance-title']
                        tops = [page.locator(s).bounding_box()['y'] for s in selectors]
                        self.assertEqual(tops, sorted(tops))
                    if OUTPUT and scene in ('empty', 'ungraded', 'zero', 'graded', 'overdue', 'long') and width in (390, 1440):
                        page.screenshot(path=str(OUTPUT/f'{scene}-{width}.png'), full_page=True)
                    page.close()

    def test_prerequisites_actual_values_and_deadline_states(self):
        for scene, path in (('empty','/semesters/new/'), ('semester-only','/courses/new/'), ('ungraded','/assignments/new/')):
            page = self.page(scene)
            self.assertEqual(page.locator('.dashboard-welcome .button:not(.secondary)').get_attribute('href'), path)
            if scene == 'empty':
                self.assertEqual(page.locator('a[href="/courses/new/"],a[href="/assignments/new/"]').count(), 0)
            if scene == 'semester-only':
                self.assertEqual(page.locator('a[href="/assignments/new/"]').count(), 0)
        for scene, value in (('zero','0.00'), ('ungraded','Not graded'), ('graded','4.50'), ('mixed','2.50')):
            page = self.page(scene)
            self.assertEqual(page.locator('#actual-cgpa-value').inner_text(), value)
        page = self.page('overdue', width=390)
        self.assertTrue(page.locator('.dashboard-attention').is_visible())
        self.assertLess(page.locator('.dashboard-attention').bounding_box()['y'], page.locator('#actual-cgpa-title').bounding_box()['y'])
        self.assertIn('No upcoming deadlines', page.locator('.dashboard-deadlines').inner_text())
        self.assertNotIn('All caught up', page.locator('main').inner_text())

    def test_enlarged_text_short_height_and_400_percent_equivalent_reflow(self):
        for scene in ('empty', 'graded', 'long'):
            for width, height, text in ((1280,500,200), (1440,900,200), (320,200,100)):
                page = self.page(scene, width, height, text, javascript=False)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                h = page.locator('h1').bounding_box()
                self.assertGreater(h['width'], 200)
                # Last primary task remains keyboard reachable, even in the 320x200 reflow viewport.
                target = page.locator('.dashboard-welcome .button:not(.secondary)')
                page.locator('.skip-link').focus()
                for _ in range(16):
                    page.keyboard.press('Tab')
                    if target.evaluate('(e)=>e===document.activeElement'):
                        break
                else:
                    self.fail('Primary action is not keyboard reachable')
                r = target.bounding_box()
                self.assertGreaterEqual(r['y'], 0)
                self.assertLessEqual(r['y']+r['height'], height)
                if OUTPUT and scene == 'long' and width == 1280:
                    page.screenshot(path=str(OUTPUT/'long-1280x500-text-200.png'))

    def test_mobile_header_actions_stay_next_to_the_intro(self):
        for width in (320,360,390,768,820,1024):
            for scene in ('empty','graded','long'):
                page=self.page(scene,width)
                gap=page.locator('.dashboard-welcome').evaluate("""e=>{
                    const intro=e.querySelector('div:first-child > p:last-child').getBoundingClientRect();
                    const actions=e.querySelector('.action-row').getBoundingClientRect();
                    return {gap:actions.top-intro.bottom,limit:2*parseFloat(getComputedStyle(document.documentElement).fontSize)};
                }""")
                self.assertLessEqual(gap['gap'],gap['limit'])
                page.close()

    def test_native_get_selection_and_table_keyboard_without_js(self):
        page = self.page('graded', width=390, javascript=False)
        region = page.get_by_role('region', name='Semester performance')
        self.assertEqual(region.locator('tbody tr').count(), 2)
        region.focus()
        page.keyboard.press('ArrowRight')
        page.wait_for_function('document.querySelector(".table-scroll").scrollLeft > 0')
        captured = []
        def respond(route):
            if 'semester=' in route.request.url:
                captured.append((route.request.method,route.request.url))
                route.fulfill(status=200, content_type='text/html', body='<p>Synthetic selection received</p>')
            else:
                route.fulfill(status=200, content_type='text/html', body=self.scenes['graded'])
        page.route('https://ucc.example.invalid/**', respond)
        page.goto('https://ucc.example.invalid/')
        page.locator('[name=semester]').select_option('00000000-0000-0000-0000-000000000002')
        page.get_by_role('button', name='Show semester GPA').click()
        page.get_by_text('Synthetic selection received').wait_for()
        self.assertEqual(captured[0][0], 'GET')
        self.assertIn('semester=00000000-0000-0000-0000-000000000002', captured[0][1])

    def test_actual_surfaces_text_controls_and_focus_contrast(self):
        def lum(color):
            values = [float(v)/255 for v in re.findall(r'[\d.]+', color)[:3]]
            values = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(values,(.2126,.7152,.0722)))
        def ratio(a,b):
            lo,hi=sorted((lum(a),lum(b)))
            return (hi+.05)/(lo+.05)
        page=self.page('overdue')
        for selector in ('#actual-cgpa-value','.dashboard-note','.dashboard-attention','.dashboard-quick-actions a'):
            locator=page.locator(selector).first
            colors=foundation.FoundationBrowserTests.painted_colors(self,locator)
            self.assertGreaterEqual(ratio(*colors),4.5)
        populated=self.page('graded')
        colors=foundation.FoundationBrowserTests.painted_colors(self,populated.locator('.dashboard-task-list span').first)
        self.assertGreaterEqual(ratio(*colors),4.5)
        colors=foundation.FoundationBrowserTests.painted_colors(self,page.locator('select'),'borderTopColor')
        self.assertGreaterEqual(ratio(*colors),3)
        focus=page.locator('html').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--color-focus").trim()')
        focus='rgb('+','.join(str(int(focus[i:i+2],16)) for i in (1,3,5))+')'
        for selector in ('.dashboard-summary','.dashboard-attention','.dashboard-welcome'):
            bg=foundation.FoundationBrowserTests.painted_colors(self,page.locator(selector))[1]
            self.assertGreaterEqual(ratio(focus,bg),3)

    def test_glass_fallback_forced_colors_and_reduced_motion(self):
        page = self.page('overdue')
        fallback = self.scenes['overdue'].replace('@supports(backdrop-filter:blur(1px))', '@supports(ucc-unsupported:yes)')
        page.set_content(fallback)
        self.assertEqual(page.locator('.dashboard-welcome').evaluate('(e)=>getComputedStyle(e).backgroundColor'), 'rgb(255, 255, 255)')
        page.emulate_media(forced_colors='active', reduced_motion='reduce')
        self.assertEqual(page.locator('.dashboard-welcome').evaluate('(e)=>getComputedStyle(e).backdropFilter'), 'none')
        page.locator('.dashboard-attention').focus()
        self.assertEqual(page.locator(':focus').evaluate('(e)=>getComputedStyle(e).outlineStyle'), 'solid')
        self.assertEqual(page.locator('.button').first.evaluate('(e)=>getComputedStyle(e).transitionDuration'), '0s')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots-dir',type=Path)
    args,rest=parser.parse_known_args()
    OUTPUT=args.screenshots_dir
    if OUTPUT: OUTPUT.mkdir(parents=True,exist_ok=True)
    unittest.main(argv=[sys.argv[0],*rest])
