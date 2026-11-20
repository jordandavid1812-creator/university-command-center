"""Groq as the automatic backup (owner's choice): one Send button; when Gemini is busy the same
request goes to Groq, still as one counted request with answered_by recorded; never for big texts,
wrong keys or bad answers; never a second switch. No network (fake connections)."""
import hashlib
import json
import os
from unittest.mock import patch
from django.db import connections, DatabaseError
from academics import services
from student_web import ai_providers
from tests.test_ai_providers import FakeConnection, gemini_reply, grok_reply
from .test_ai_pages import AiCase, SUMMARY, KEY

WITH_GROQ = {"UCC_GEMINI_API_KEY": KEY, "UCC_GEMINI_MODEL": "synthetic-model-1",
             "UCC_GROQ_API_KEY": KEY, "UCC_GROQ_MODEL": "openai/gpt-oss-120b"}


class GroqAutomaticBackupTests(AiCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, WITH_GROQ, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("UCC_GROK_API_KEY", "UCC_GROK_MODEL"):
            os.environ.pop(name, None)  # restored by the outer patch.dict
        self.replies["groq"] = grok_reply(json.dumps(SUMMARY))
        self.statuses = {}

    def fake_connect(self, provider):
        self.during_call.append(connections["default"].in_atomic_block)
        return FakeConnection(provider, self.statuses.get(provider, 200), self.replies[provider])

    def limit(self, size):
        patcher = patch.dict(ai_providers.CHARACTER_LIMITS, {"groq": size})
        patcher.start()
        self.addCleanup(patcher.stop)

    def ledger(self, response):
        return services.ai.get_request(self.identity_a, response["Location"].rstrip("/").rsplit("/", 1)[-1])

    def test_confirm_page_has_one_send_button_and_never_names_the_backup(self):
        page = self.confirm()
        self.assertContains(page, 'name="provider" value="main"')
        self.assertNotContains(page, 'value="backup2"')
        self.assertNotContains(page, "backup service</button>")
        self.assertNotContains(page, "Groq")
        self.assertContains(page, "a backup AI service")  # the "Before you send" notes say it may happen

    def test_busy_gemini_switches_to_groq_and_shows_the_result(self):
        self.statuses["gemini"] = 503
        response = self.send(self.token())
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini", "groq"])
        page = self.client_a.get(response["Location"], follow=True)
        self.assertContains(page, "Cells are the basic unit of life.")
        self.assertNotContains(page, "Request failed")
        self.assertNotContains(page, "Groq")  # pages never name the provider
        ledger = self.ledger(response)
        self.assertEqual((ledger.provider, ledger.status, ledger.answered_by, ledger.answered_by_model),
                         ("gemini", "succeeded", "groq", "openai/gpt-oss-120b"))
        self.assertEqual(self.usage()["used_today"], 1)  # one click, counted once
        self.assertEqual(self.during_call, [False, False])  # no database transaction open on the network
        sent = FakeConnection.made[1].requests[0]
        self.assertEqual(sent[1], "/openai/v1/chat/completions")
        self.assertEqual(sent[2]["model"], "openai/gpt-oss-120b")

    def test_timeouts_and_network_failures_switch_too(self):
        for category in ("timeout", "network"):
            with self.subTest(category=category):
                FakeConnection.made = []
                original = ai_providers.ask

                def ask(provider, *args, _original=original, _category=category):
                    if provider == "gemini":
                        raise ai_providers.ProviderError(_category)
                    return _original(provider, *args)

                with patch.object(ai_providers, "ask", ask):
                    response = self.send(self.token())
                self.assertContains(self.client_a.get(response["Location"], follow=True), "Cells are the basic unit")

    def test_no_switch_for_wrong_key_bad_answers_or_big_texts(self):
        self.statuses["gemini"] = 401
        self.assertContains(self.client_a.get(self.send(self.token())["Location"]), "API key")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini"])
        FakeConnection.made = []
        self.statuses["gemini"] = 200
        self.replies["gemini"] = gemini_reply("not json")
        self.assertContains(self.client_a.get(self.send(self.token())["Location"]), "not in the expected format")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini"])
        FakeConnection.made = []
        self.limit(10)  # the synthetic notes are longer than this
        self.statuses["gemini"] = 503
        page = self.client_a.get(self.send(self.token())["Location"])
        self.assertContains(page, "The AI service was busy")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini"])

    def test_if_the_backup_also_fails_the_student_sees_one_failure_and_it_counts_once(self):
        self.statuses["gemini"] = 503
        self.statuses["groq"] = 503
        page = self.client_a.get(self.send(self.token())["Location"])
        self.assertContains(page, "The AI service was busy")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini", "groq"])  # never a third call
        self.assertEqual(self.usage()["used_today"], 1)

    def test_groq_cannot_be_chosen_directly(self):
        response = self.send(self.token(), provider="backup2")
        self.assertContains(response, "cannot take this request", status_code=400)
        self.assertEqual(FakeConnection.made, [])
        self.assertEqual(self.usage()["used_today"], 0)

    def test_if_the_switch_cannot_be_recorded_nothing_goes_to_groq(self):
        self.statuses["gemini"] = 503
        with patch.object(services.ai, "switch_to", side_effect=DatabaseError("synthetic")):
            page = self.client_a.get(self.send(self.token())["Location"])
        self.assertContains(page, "The AI service was busy")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini"])


class SwitchRecordTests(AiCase):
    def reserve(self, label):
        request, _ = services.ai.reserve(self.identity_a, tool="summary", provider="gemini",
                                         model="synthetic-model-1", characters_sent=10, truncated=False,
                                         consent_token_hash=hashlib.sha256(label.encode()).hexdigest())
        return request

    def test_only_an_in_progress_request_of_the_student_can_switch_once(self):
        request = self.reserve("a")
        for provider, model in (("grok", "openai/gpt-oss-120b"), ("groq", "Bad Model"), ("groq", "")):
            with self.subTest(provider=provider, model=model), self.assertRaises(services.InvalidRecord):
                services.ai.switch_to(self.identity_a, request.pk, provider, model)
        with self.assertRaises(services.RecordNotFound):
            services.ai.switch_to(self.identity_b, request.pk, "groq", "openai/gpt-oss-120b")
        services.ai.switch_to(self.identity_a, request.pk, "groq", "openai/gpt-oss-120b")
        with self.assertRaises(services.AiRequestClosed):  # never a second switch
            services.ai.switch_to(self.identity_a, request.pk, "groq", "openai/gpt-oss-120b")
        services.ai.fail(self.identity_a, request.pk, "timeout")
        finished = self.reserve("b")
        services.ai.fail(self.identity_a, finished.pk, "timeout")
        with self.assertRaises(services.AiRequestClosed):  # never after the request has ended
            services.ai.switch_to(self.identity_a, finished.pk, "groq", "openai/gpt-oss-120b")
