"""Vercel hosting files: the entry point, the exact package lock and what Vercel receives."""
from pathlib import Path
import re
import subprocess
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[1]


def pins(path):
    return dict(re.findall(r'^([a-z0-9_.-]+)==([^\s\;]+)', path.read_text(), re.M | re.I))


class VercelConfigTests(unittest.TestCase):
    def test_pyproject_names_the_entry_point_and_python_312(self):
        data = tomllib.loads((REPO / 'pyproject.toml').read_text())
        self.assertEqual(data['tool']['vercel']['entrypoint'], 'vercel_app:app')
        self.assertEqual(data['project']['requires-python'], '>=3.12,<3.13')
        self.assertIs(data['tool']['uv']['package'], False)
        self.assertEqual((REPO / '.python-version').read_text().strip(), '3.12')
        source = (REPO / 'vercel_app.py').read_text()
        self.assertIn("os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.web_vercel'", source)
        self.assertNotIn('setdefault', source)  # the environment can never pick another profile
        self.assertIn("call_command('check', deploy=True, fail_level='WARNING')", source)
        self.assertLess(source.index("call_command('check'"), source.index('app = get_wsgi_application()'))

    def test_uv_lock_has_exactly_the_reviewed_versions_with_hashes(self):
        lock = tomllib.loads((REPO / 'uv.lock').read_text())
        locked = {p['name']: p['version'] for p in lock['package'] if p['name'] != 'university-command-center-web'}
        reviewed = {name.lower(): version for name, version in pins(REPO / 'requirements-django-lock.txt').items()}
        for name, version in locked.items():
            if name == 'tzdata':  # Windows-only dependency of Django; never installed on Vercel's Linux
                continue
            with self.subTest(package=name):
                self.assertEqual(reviewed.get(name), version)
        self.assertEqual(set(reviewed) - set(locked), {'gunicorn'})  # the server package only
        for package in lock['package']:
            for artifact in package.get('wheels', []) + ([package['sdist']] if 'sdist' in package else []):
                self.assertTrue(artifact['hash'].startswith('sha256:'), package['name'])
        declared = tomllib.loads((REPO / 'pyproject.toml').read_text())['project']['dependencies']
        for requirement in declared:
            name, version = re.fullmatch(r'([A-Za-z0-9_-]+)(?:\[[a-z]+\])?==(\S+)', requirement).groups()
            self.assertEqual(locked[name.lower()], version)

    def test_vercel_receives_only_the_website(self):
        def ignored(path):
            return subprocess.run(['git', '-c', 'core.excludesFile=' + str(REPO / '.vercelignore'), 'check-ignore', '--no-index',
                                   '-q', path], cwd=REPO, capture_output=True).returncode == 0
        for path in ('vercel_app.py', 'pyproject.toml', 'uv.lock', '.python-version', 'academic_logic.py', 'grading_policy.py',
                     'server/manage.py', 'server/config/settings/web_vercel.py', 'server/student_web/pdf_text_child.py',
                     'server/student_web/static/student_web/site.css', 'server/accounts/templates/accounts/form.html'):
            with self.subTest(sent=path):
                self.assertFalse(ignored(path))
        for path in ('tests/test_vercel_config.py', 'tools/run_local_web.py', 'docs/LAUNCH.md', 'deploy/compose.yml',
                     'supabase/migrations/0001_schema.sql', 'server/web_tests/base.py', 'server/auth_tests/base.py',
                     'server/academics/tests/test_models.py', 'requirements.txt', 'main.py', 'web_app.py', 'AGENTS.md',
                     'courses.json', '.env', 'frontend/src/app.ts', '.github/workflows/quality.yml'):
            with self.subTest(kept_back=path):
                self.assertTrue(ignored(path))


if __name__ == '__main__':
    unittest.main()
