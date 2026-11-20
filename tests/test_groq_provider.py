"""Groq as the backup AI for small files: fixed host, OpenAI-style request with low reasoning,
"/" allowed in the model name only for Groq, and the size gate. No network (NoNetwork)."""
import json
import os
import unittest
from unittest.mock import patch
from server.student_web import ai_providers as ai
from tests.test_ai_providers import NoNetwork, FakeConnection, grok_reply, SUMMARY

KEY = "synthetic-test-key-0123456789"
ENV = {"UCC_GEMINI_API_KEY": KEY, "UCC_GEMINI_MODEL": "synthetic-model-1",
       "UCC_GROQ_API_KEY": KEY, "UCC_GROQ_MODEL": "openai/gpt-oss-120b"}


class GroqTests(NoNetwork):
    def test_host_key_and_model_settings(self):
        self.assertEqual(ai.HOSTS["groq"], "api.groq.com")
        self.assertEqual(ai.PUBLIC_CODES["groq"], "backup2")
        with patch.dict(os.environ, ENV, clear=True):
            self.assertEqual(ai.available_providers(), ["gemini", "groq"])
            self.assertEqual(ai.configured("groq"), (KEY, "openai/gpt-oss-120b"))

    def test_a_slash_is_allowed_only_for_groq(self):
        with patch.dict(os.environ, {**ENV, "UCC_GEMINI_MODEL": "openai/gpt-oss-120b"}, clear=True):
            self.assertIsNone(ai.configured("gemini"))  # Gemini's model goes in the URL path
        for model in ("../model", "a/b/c", "/model", "model/", "Openai/x", "a" * 65, "openai/" + "a" * 58):
            with self.subTest(model=model), patch.dict(os.environ, {**ENV, "UCC_GROQ_MODEL": model}, clear=True):
                self.assertIsNone(ai.configured("groq"))

    def test_request_shape_and_reply(self):
        connection = FakeConnection("groq", 200, grok_reply(json.dumps(SUMMARY)))
        with patch.dict(os.environ, ENV, clear=True), patch.object(ai, "_connect", lambda provider: connection):
            self.assertEqual(ai.ask("groq", "summary", "Cells.")["points"], SUMMARY["points"])
        method, path, body, headers = connection.requests[0]
        self.assertEqual((method, path), ("POST", "/openai/v1/chat/completions"))
        self.assertEqual(headers["Authorization"], f"Bearer {KEY}")
        self.assertEqual(body["model"], "openai/gpt-oss-120b")
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["max_completion_tokens"], ai.MAX_OUTPUT_TOKENS["summary"])
        self.assertNotIn(KEY, json.dumps(body))

    def test_other_groq_models_get_no_reasoning_setting(self):
        _, _, body = ai.groq_request("llama-3.3-70b-versatile", KEY, "s", "u", "quiz")
        self.assertNotIn("reasoning_effort", body)

    def test_groq_is_never_a_button_and_only_a_busy_gemini_falls_back_for_small_texts(self):
        limit = ai.CHARACTER_LIMITS["groq"]
        with patch.dict(os.environ, ENV, clear=True):
            self.assertEqual(ai.button_providers(), ["gemini"])
            self.assertEqual(ai.send_buttons(ai.button_providers()), [("main", "Send")])
            self.assertEqual(ai.fallback_for("gemini", limit), "groq")
            self.assertIsNone(ai.fallback_for("gemini", limit + 1))
            self.assertIsNone(ai.fallback_for("groq", 10))  # never a second switch
        with patch.dict(os.environ, {k: v for k, v in ENV.items() if "GEMINI" not in k}, clear=True):
            self.assertEqual(ai.button_providers(), ["groq"])  # the only service set up
        for category, status, busy in (("http_error", 503, True), ("timeout", None, True), ("network", None, True),
                                       ("http_error", 401, False), ("http_error", 429, False), ("blocked", 200, False),
                                       ("invalid_response", 200, False), ("truncated", 200, False)):
            with self.subTest(category=category, status=status):
                self.assertEqual(ai.is_busy(ai.ProviderError(category, status)), busy)

if __name__ == "__main__":
    unittest.main()
