"""The local launcher (tools/run_local_web.py): secrets live outside the repository, and `check`
never prints a key. No network: the one HTTPS helper is replaced."""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "tools" / "run_local_web.py"
KEY = "synthetic-launcher-key-0123456789"


def load(home):
    with patch.dict(os.environ, {"UCC_LOCAL_HOME": str(home)}):
        os.environ.pop("UCC_REPO", None)
        spec = importlib.util.spec_from_file_location("run_local_web_under_test", LAUNCHER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_secrets_live_outside_the_repository(self):
        launcher = load(self.home)
        self.assertEqual(launcher.SECRETS, self.home / "local-web-secrets.json")
        self.assertEqual(launcher.REPO.resolve(), REPO)
        with self.assertRaises(SystemExit):
            load(REPO / "tools")  # a secrets folder inside the repository is refused

    @unittest.skipIf(os.name == "nt", "the Windows default (%LOCALAPPDATA%\\UCC) is used on Windows")
    def test_default_private_folder_is_in_the_home_folder(self):
        launcher = load(self.home)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UCC_LOCAL_HOME", None)
            self.assertEqual(launcher.private_folder(), Path.home() / ".local" / "share" / "ucc")

    def test_check_times_one_answer_sends_low_thinking_and_never_prints_the_key(self):
        launcher = load(self.home)
        calls = []

        def fake_call(host, method, path, headers, body=None):
            calls.append((host, method, path, body))
            if method == "GET":
                return 200, {"models": [{"name": "models/gemini-3.6-flash",
                                         "supportedGenerationMethods": ["generateContent"]}]}, 0.2
            return 200, {"candidates": []}, 4.2

        output = io.StringIO()
        with patch.object(launcher, "_call", fake_call), contextlib.redirect_stdout(output), \
                patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UCC_GEMINI_THINKING", None)
            launcher.check_gemini(KEY, "gemini-3.6-flash")
        text = output.getvalue()
        self.assertIn("answered in 4.2 seconds: fast", text)
        self.assertNotIn(KEY, text)
        self.assertEqual(calls[1][3]["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertEqual({host for host, *_ in calls}, {"generativelanguage.googleapis.com"})

    def test_check_grok_reports_slow_answers(self):
        launcher = load(self.home)

        def fake_call(host, method, path, headers, body=None):
            self.assertEqual(host, "api.x.ai")
            return (200, {"data": [{"id": "grok-synthetic"}]}, 0.1) if method == "GET" else (200, {}, 21.0)

        output = io.StringIO()
        with patch.object(launcher, "_call", fake_call), contextlib.redirect_stdout(output):
            launcher.check_grok(KEY, "grok-synthetic")
        self.assertIn("answered in 21.0 seconds: slow (over 15 seconds)", output.getvalue())
        self.assertNotIn(KEY, output.getvalue())

    def test_safety_check_refuses_the_secrets_file_name(self):
        spec = importlib.util.spec_from_file_location("safety_under_test", REPO / "tools" / "check_repository_safety.py")
        safety = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(safety)
        self.assertTrue(safety.private_path("tools/local-web-secrets.json"))


if __name__ == "__main__":
    unittest.main()
