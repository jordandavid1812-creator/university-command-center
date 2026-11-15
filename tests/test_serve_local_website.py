"""The local website starter only serves development profiles on 127.0.0.1."""
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "tools" / "serve_local_website.py"
SPEC = importlib.util.spec_from_file_location("serve_local_website", PATH)
starter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(starter)


class TestServeLocalWebsite(unittest.TestCase):
    def refused(self, argv):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            starter.options(argv)

    def test_defaults_are_loopback_port_8000_and_the_website_profile(self):
        values = starter.options([])
        self.assertEqual((starter.HOST, values.port, values.settings),
                         ("127.0.0.1", 8000, "config.settings.web_development"))

    def test_only_local_development_profiles_are_accepted(self):
        self.assertEqual(starter.options(["--settings", "config.settings.auth_development"]).settings,
                         "config.settings.auth_development")
        for settings in ("config.settings.production", "config.settings.auth_migration", "config.settings.test"):
            with self.subTest(settings=settings):
                self.refused(["--settings", settings])

    def test_there_is_no_way_to_listen_beyond_this_computer(self):
        self.refused(["--host", "0.0.0.0"])
        for port in ("80", "0", "70000"):
            with self.subTest(port=port):
                self.refused(["--port", port])

    def test_main_runs_system_checks_then_serves_only_on_loopback(self):
        from unittest import mock
        calls = []
        django = mock.MagicMock()
        django.setup.side_effect = lambda: calls.append("setup")
        management = mock.MagicMock()
        management.call_command.side_effect = lambda name: calls.append(("check", name))
        basehttp = mock.MagicMock()
        basehttp.run.side_effect = lambda host, port, app, threading: calls.append(("run", host, port))
        modules = {"django": django, "django.core": mock.MagicMock(), "django.core.management": management,
                   "django.core.servers": mock.MagicMock(), "django.core.servers.basehttp": basehttp,
                   "django.core.wsgi": mock.MagicMock()}
        with mock.patch.dict(sys.modules, modules), mock.patch.dict("os.environ"), \
                mock.patch.object(sys, "path", list(sys.path)), contextlib.redirect_stdout(io.StringIO()):
            starter.main(["--port", "8001"])
        self.assertEqual(calls, ["setup", ("check", "check"), ("run", "127.0.0.1", 8001)])

    def test_importing_does_not_start_django(self):
        self.assertNotIn("django.core.servers.basehttp", sys.modules)


if __name__ == "__main__":
    unittest.main()
