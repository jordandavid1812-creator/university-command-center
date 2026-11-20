"""One Gemini retry (owner's choice): after a quick "busy" reply (5xx) or a dropped connection,
the same service is asked exactly once more after a short pause, then Groq for small texts.
Never after a timeout or a 4xx/bad answer, never twice, still one request. No network."""
from unittest.mock import patch
from student_web import ai_providers, ai_views
from tests.test_ai_providers import FakeConnection
from .test_ai_pages import AiCase


class GeminiRetryTests(AiCase):
    def setUp(self):
        super().setUp()
        self.pauses = []
        sleep = patch.object(ai_views.time, "sleep", self.pauses.append)
        sleep.start()
        self.addCleanup(sleep.stop)
        self.answers = []  # statuses for successive Gemini connections; then 200

    def fake_connect(self, provider):
        status = self.answers.pop(0) if self.answers else 200
        return FakeConnection(provider, status, self.replies[provider])

    def outcome(self, response):
        return self.client_a.get(response["Location"], follow=True)

    def test_a_busy_reply_is_asked_once_more_and_the_result_is_shown(self):
        self.answers = [503]
        page = self.outcome(self.send(self.token()))
        self.assertContains(page, "Cells are the basic unit of life.")
        self.assertNotContains(page, "Request failed")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini", "gemini"])
        self.assertEqual(self.pauses, [ai_views.RETRY_PAUSE_SECONDS])
        self.assertEqual(ai_views.RETRY_PAUSE_SECONDS, 3)
        self.assertEqual(self.usage()["used_today"], 1)

    def test_never_more_than_one_retry(self):
        self.answers = [503, 503, 503]
        page = self.outcome(self.send(self.token()))
        self.assertContains(page, "The AI service was busy")
        self.assertEqual(len(FakeConnection.made), 2)  # no Groq set up in this profile
        self.assertEqual(self.usage()["used_today"], 1)

    def test_no_retry_for_wrong_keys_bad_answers_or_timeouts(self):
        self.answers = [401]
        self.assertContains(self.outcome(self.send(self.token())), "API key")
        self.assertEqual(len(FakeConnection.made), 1)
        calls = []

        def timed_out(provider, *args):
            calls.append(provider)
            raise ai_providers.ProviderError("timeout")

        with patch.object(ai_providers, "ask", timed_out):
            self.send(self.token())
        self.assertEqual(calls, ["gemini"])
        self.assertEqual(self.pauses, [])

    def test_a_dropped_connection_is_retried_once(self):
        calls = []
        original = ai_providers.ask

        def drop_first(provider, *args):
            calls.append(provider)
            if len(calls) == 1:
                raise ai_providers.ProviderError("network")
            return original(provider, *args)

        with patch.object(ai_providers, "ask", drop_first):
            page = self.outcome(self.send(self.token()))
        self.assertContains(page, "Cells are the basic unit of life.")
        self.assertEqual(calls, ["gemini", "gemini"])

    def test_which_failures_are_worth_retrying(self):
        for category, status, expected in (("http_error", 503, True), ("network", None, True),
                                           ("timeout", None, False), ("http_error", 401, False),
                                           ("http_error", 429, False), ("blocked", 200, False),
                                           ("invalid_response", 200, False), ("truncated", 200, False)):
            with self.subTest(category=category, status=status):
                self.assertEqual(ai_providers.worth_retrying(ai_providers.ProviderError(category, status)), expected)
