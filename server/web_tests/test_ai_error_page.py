"""The AI request page after a failure: a provider-side (5xx) failure says the service was busy
(not "check the API key"), and every "counts towards" line shows this site's real daily limit.
Synthetic data; no network (NoNetworkMixin)."""
import hashlib
from django.test import override_settings
from django.urls import reverse
from academics import services
from tests.network_guard import NoNetworkMixin
from .base import WebsiteCase


class AiErrorPageTests(NoNetworkMixin, WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()

    def failed(self, category, status_class=''):
        ledger, _ = services.ai.reserve(self.identity_a, tool='flashcards', provider='gemini',
                                        model='synthetic-model-1', characters_sent=100, truncated=False,
                                        consent_token_hash=hashlib.sha256(category.encode() + status_class.encode()).hexdigest())
        services.ai.fail(self.identity_a, ledger.pk, category, status_class)
        return self.client_a.get(reverse('student_web:ai-request', args=[ledger.pk]))

    def test_a_provider_side_failure_says_busy_and_not_check_the_key(self):
        page = self.failed('http_error', '5xx')
        self.assertContains(page, 'The AI service was busy or had a problem on its side')
        self.assertContains(page, 'try again in a few minutes')
        self.assertNotContains(page, 'check the API key')
        self.assertNotContains(page, 'a 5xx reply')

    def test_a_rejected_request_still_points_at_the_key_or_model(self):
        page = self.failed('http_error', '4xx')
        self.assertContains(page, 'check the API key and model name')
        self.assertContains(page, 'a 4xx reply')

    @override_settings(UCC_AI_REQUESTS_PER_DAY=10)
    def test_the_page_shows_the_real_daily_limit(self):
        page = self.failed('timeout')
        self.assertContains(page, "This request still counts towards today's 10.")
        self.assertNotContains(page, "today's 50")

    def test_the_local_limit_stays_50(self):
        self.assertContains(self.failed('network'), "today's 50")
