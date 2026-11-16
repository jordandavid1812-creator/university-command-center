"""The repository safety check refuses tracked API keys and never prints them.

Key-shaped strings are built while the tests run, so no tracked file contains one.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.check_repository_safety import contains_api_key

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check_repository_safety.py"
GOOGLE = "AI" + "za" + "Sy" + "Q" * 33          # "AIza" + 35 key characters
XAI = "xa" + "i-" + "k7" * 20                      # "xai-" + 40 key characters


class KeyShapeTests(unittest.TestCase):
    def test_key_shapes_are_found(self):
        for text in (GOOGLE, XAI, f'UCC_GEMINI_API_KEY="{GOOGLE}"', f"Authorization: Bearer {XAI}\n"):
            with self.subTest(text=text[:12]):
                self.assertTrue(contains_api_key(text.encode()))

    def test_ordinary_text_does_not_match(self):
        for text in ("the `AIza` prefix plus exactly 35 key characters", "the `xai-` prefix plus at least 40",
                     GOOGLE + "Q",                  # 36 characters: not a Google key shape
                     "x" + GOOGLE,                  # part of a longer word
                     "xai-" + "k7" * 10,            # too short for an xAI key
                     "UCC_GEMINI_API_KEY"):
            with self.subTest(text=text[:20]):
                self.assertFalse(contains_api_key(text.encode()))

    def test_the_check_fails_on_a_tracked_key_without_printing_it(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
            subprocess.run(["git", "init", "-q", folder], check=True, env=environment)
            (Path(folder) / "settings_note.txt").write_text(f"key = {GOOGLE}\n", encoding="utf-8")
            (Path(folder) / "readme.txt").write_text("No keys here.\n", encoding="utf-8")
            subprocess.run(["git", "-C", folder, "add", "."], check=True, env=environment)
            result = subprocess.run([sys.executable, str(SCRIPT)], cwd=folder, capture_output=True, text=True,
                                    env=environment)
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 tracked files contain an API-key-shaped string", result.stdout)
        shown = result.stdout + result.stderr
        self.assertNotIn(GOOGLE, shown)
        self.assertNotIn("settings_note", shown)


if __name__ == "__main__":
    unittest.main()
