"""Year-long caching for style sheets, scripts and icons on Vercel (owner's choice, for speed).
Every URL carries the deployment stamp, so a new deployment always reaches students."""
import json
import os
from unittest.mock import patch
from django.test import SimpleTestCase
from config import static_cache
from .test_vercel_profile import run

SHA = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'


class StampTests(SimpleTestCase):
    def test_stamp_comes_from_vercel_and_is_bounded(self):
        self.assertEqual(static_cache.deployment_stamp({'VERCEL_GIT_COMMIT_SHA': SHA}), SHA[:12])
        self.assertEqual(static_cache.deployment_stamp({'VERCEL_DEPLOYMENT_ID': 'dpl_7vhiyDZ35Pr54'}), 'dpl_7vhiyDZ3')
        for bad in ({}, {'VERCEL_GIT_COMMIT_SHA': ''}, {'VERCEL_GIT_COMMIT_SHA': 'x"><script>'},
                    {'VERCEL_GIT_COMMIT_SHA': 'abc'}):
            with self.subTest(env=bad):
                self.assertEqual(static_cache.deployment_stamp(bad), '')

    def test_headers_only_change_when_versioned(self):
        for stamp, expected in ((SHA, 'public, max-age=31536000, s-maxage=31536000, immutable'), ('', None)):
            with self.subTest(stamp=bool(stamp)), patch.dict(os.environ, {'VERCEL_GIT_COMMIT_SHA': stamp,
                                                                         'VERCEL_DEPLOYMENT_ID': ''}):
                headers = {}
                static_cache.add_cache_headers(headers, '/x/site.css', '/static/student_web/site.css')
                self.assertEqual(headers.get('Cache-Control'), expected)


class VercelProfileStaticTests(SimpleTestCase):
    databases = {'default', 'runtime', 'auth'}

    def test_static_urls_carry_the_stamp_and_are_cached_for_a_year(self):
        code = '''import json
from django.templatetags.static import static
from django.test import Client
from django.conf import settings
c = Client(HTTP_HOST=settings.ALLOWED_HOSTS[0])
r = c.get(static("student_web/site.css"), secure=True)
print(json.dumps([static("student_web/site.css"), r.status_code, r.get("Cache-Control")]))'''
        result = run(code, env_updates={'VERCEL_GIT_COMMIT_SHA': SHA})
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        url, status, cache = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(url, f'/static/student_web/site.css?v={SHA[:12]}')
        self.assertEqual(status, 200)
        self.assertEqual(cache, 'public, max-age=31536000, s-maxage=31536000, immutable')

    def test_without_a_stamp_nothing_changes(self):
        code = 'import json\nfrom django.templatetags.static import static\nprint(json.dumps(static("student_web/site.css")))'
        result = run(code, env_updates={'VERCEL_GIT_COMMIT_SHA': None, 'VERCEL_DEPLOYMENT_ID': None})
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), '/static/student_web/site.css')
