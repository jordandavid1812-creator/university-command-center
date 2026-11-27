"""Launch step E: what students see at the AI limits on the public site (10 each, 200 for the site)."""
from django.test import override_settings
from tests.test_ai_providers import FakeConnection
from .test_ai_pages import AiCase


@override_settings(UCC_AI_REQUESTS_PER_DAY=10, UCC_AI_SITE_REQUESTS_PER_DAY=200)
class AiLimitPageTests(AiCase):
    def test_pages_show_ten_requests_a_day(self):
        self.assertContains(self.confirm(), "0 of 10")

    def test_eleventh_request_gets_a_clear_refusal_and_nothing_is_sent(self):
        with override_settings(UCC_AI_REQUESTS_PER_DAY=1):
            self.send(self.token())
            calls = len(FakeConnection.made)
            response = self.send(self.token())
        self.assertContains(response, "used all 1 AI requests for today", status_code=429)
        self.assertEqual(len(FakeConnection.made), calls)

    def test_site_limit_gets_its_own_message_and_nothing_is_sent(self):
        # Per-student limit high, site limit 1: the second request is refused by the site limit.
        with override_settings(UCC_AI_SITE_REQUESTS_PER_DAY=1):
            self.send(self.token())
            calls = len(FakeConnection.made)
            response = self.send(self.token())
        self.assertContains(response, "limit for the whole site", status_code=429)
        self.assertEqual(len(FakeConnection.made), calls)
