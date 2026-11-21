"""Quiz options (owner's choice): 5/10/15/20 questions at Easy/Normal/Hard/Exam. No network."""
import json
import os
import unittest
from unittest.mock import patch
from server.student_web import ai_providers as ai
from tests.test_ai_providers import NoNetwork

KEY = "synthetic-test-key-0123456789"


def quiz(n):
    return {"questions": [{"question": f"Q{i}?", "options": ["A", "B", "C", "D"], "correct": i % 4,
                           "reason": "Because."} for i in range(n)]}


class QuizOptionTests(NoNetwork):
    def test_options_are_validated(self):
        self.assertIsNone(ai.quiz_options(""))
        self.assertEqual(ai.quiz_options("15:hard"), (15, "hard"))
        for bad in ("7:hard", "15:insane", "15", ":hard", "20:exam:x", "015:hard"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ai.quiz_options(bad)

    def test_prompt_asks_for_the_chosen_count_and_level(self):
        system, user = ai.build_prompt("quiz", "Notes.", options="15:exam")
        self.assertIn("(exactly 15 questions;", system)
        self.assertNotIn("5 to 10 questions", system)
        self.assertIn(ai.QUIZ_LEVELS["exam"], system)
        self.assertIn("Notes.", user)
        legacy, _ = ai.build_prompt("quiz", "Notes.")
        self.assertIn("(5 to 10 questions;", legacy)  # without options nothing changes
        for level, text in ai.QUIZ_LEVELS.items():
            self.assertIn(text, ai.build_prompt("quiz", "x", options=f"10:{level}")[0])
        self.assertEqual(ai.build_prompt("summary", "x", options="")[0], ai.build_prompt("summary", "x")[0])

    def test_results_keep_at_most_the_chosen_number(self):
        self.assertEqual(len(ai.parse_result("quiz", json.dumps(quiz(20)), "20:hard")["questions"]), 20)
        self.assertEqual(len(ai.parse_result("quiz", json.dumps(quiz(12)), "10:normal")["questions"]), 10)
        self.assertEqual(len(ai.parse_result("quiz", json.dumps(quiz(7)), "15:easy")["questions"]), 7)
        for raw, options in ((quiz(21), "20:hard"), (quiz(4), "5:easy")):
            with self.subTest(n=len(raw["questions"])), self.assertRaises(ai.ProviderError):
                ai.parse_result("quiz", json.dumps(raw), options)
        with self.assertRaises(ai.ProviderError):
            ai.parse_result("quiz", json.dumps(quiz(10)), "13:hard")

    def test_saved_quizzes_up_to_twenty_questions_are_shown(self):
        self.assertEqual(len(ai.check_result("quiz", quiz(20))["questions"]), 20)
        with self.assertRaises(ValueError):
            ai.check_result("quiz", quiz(21))

    def test_big_quizzes_never_switch_to_the_smaller_backup(self):
        env = {"UCC_GEMINI_API_KEY": KEY, "UCC_GEMINI_MODEL": "synthetic-model-1",
               "UCC_GROQ_API_KEY": KEY, "UCC_GROQ_MODEL": "openai/gpt-oss-120b"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(ai.fallback_for("gemini", 100, "quiz", "10:hard"), "groq")
            self.assertIsNone(ai.fallback_for("gemini", 100, "quiz", "15:hard"))
            self.assertIsNone(ai.fallback_for("gemini", 100, "quiz", "20:easy"))
            self.assertEqual(ai.fallback_for("gemini", 100, "quiz", ""), "groq")
            self.assertEqual(ai.fallback_for("gemini", 100), "groq")
            _, _, body = ai.groq_request("openai/gpt-oss-120b", KEY, "s", "u", "quiz")
            self.assertEqual(body["max_completion_tokens"], ai.GROQ_MAX_OUTPUT_TOKENS)
        self.assertEqual(ai.MAX_OUTPUT_TOKENS["quiz"], 4096)  # unchanged for 5-10 questions

    def test_only_big_quizzes_ask_for_a_longer_reply(self):
        from tests.test_ai_providers import FakeConnection, gemini_reply
        env = {"UCC_GEMINI_API_KEY": KEY, "UCC_GEMINI_MODEL": "synthetic-model-1"}
        for options, tokens, n in (("", 4096, 5), ("10:hard", 4096, 10), ("15:hard", 8192, 15), ("20:exam", 8192, 20)):
            with self.subTest(options=options), patch.dict(os.environ, env, clear=True):
                FakeConnection.made = []
                with patch.object(ai, "_connect", lambda p: FakeConnection(p, 200, gemini_reply(json.dumps(quiz(n))))):
                    ai.ask("gemini", "quiz", "Notes.", "", options)
                body = FakeConnection.made[0].requests[0][2]
                self.assertEqual(body["generationConfig"]["maxOutputTokens"], tokens)


if __name__ == "__main__":
    unittest.main()
