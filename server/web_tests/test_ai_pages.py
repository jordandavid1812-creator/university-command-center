"""AI study assistant stage 3b: pages, consent, the send flow, results, export and dashboard.

Nothing here can reach Gemini or Grok: NoNetworkMixin fails any non-local connection and the
provider connection is replaced with a fake that records exactly what would have been sent.
"""
import json
import os
from unittest.mock import patch
from django.db import connections
from django.test import Client
from django.urls import reverse
from academics import services
from academics.ownership import database_alias
from student_web import ai_consent, ai_providers
from tests.network_guard import NoNetworkMixin
from tests.test_ai_providers import FakeConnection, gemini_reply, grok_reply
from .base import WebsiteCase

KEY = "synthetic-test-key-0123456789"
BOTH = {"UCC_GEMINI_API_KEY": KEY, "UCC_GEMINI_MODEL": "synthetic-model-1",
        "UCC_GROK_API_KEY": KEY, "UCC_GROK_MODEL": "synthetic-model-2"}
NOTES = b"Cells are the basic unit of life. Mitochondria release energy."
SUMMARY = {"points": ["Cells are the basic unit of life.", "<script>alert(1)</script> is shown as text."]}
QUIZ = {"questions": [{"question": f"Question {n}?", "options": ["Alpha", "Beta", "Gamma", "Delta"],
                       "correct": n % 4, "reason": f"Reason {n}."} for n in range(5)]}
CARDS = {"cards": [{"front": f"Term {n}", "back": f"Meaning {n}"} for n in range(5)]}
ANSWER = {"answer": "Section 2 explains it.", "not_covered": False}


class AiCase(NoNetworkMixin, WebsiteCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, BOTH)
        environment.start()
        self.addCleanup(environment.stop)
        self.seed()
        self.material = services.materials.create_with_file(
            self.identity_a, title="Week 1 notes", course_id=self.course_a.pk, original_filename="secret-name.txt",
            file_type="txt", content=NOTES)
        FakeConnection.made = []
        self.replies = {"gemini": gemini_reply(json.dumps(SUMMARY)), "grok": grok_reply(json.dumps(SUMMARY))}
        self.during_call = []
        connect = patch.object(ai_providers, "_connect", self.fake_connect)
        connect.start()
        self.addCleanup(connect.stop)

    def fake_connect(self, provider):
        alias = database_alias()
        # Recorded while "on the network": the plan requires no open database transaction here.
        self.during_call.append(connections[alias].in_atomic_block)
        return FakeConnection(provider, 200, self.replies[provider])

    def url(self, name, *args):
        return reverse(f"student_web:{name}", args=args or [self.material.pk])

    def confirm(self, tool="summary", question="", client=None):
        return (client or self.client_a).post(self.url("ai-confirm"), {"tool": tool, "question": question})

    def token(self, tool="summary", question=""):
        response = self.confirm(tool, question)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.context["send_form"].initial["token"]

    def send(self, token, tool="summary", question="", provider="gemini", client=None):
        return (client or self.client_a).post(self.url("ai-send"), {"token": token, "tool": tool, "question": question,
                                                                     "provider": provider})

    def usage(self):
        return services.ai.usage(self.identity_a)


class ToolsAndConfirmTests(AiCase):
    def test_tools_page_is_owner_only_and_needs_a_stored_file(self):
        page = self.client_a.get(self.url("ai-tools"))
        for button in ("Create summary", "Create quiz", "Create flashcards", "Ask about this file"):
            self.assertContains(page, button)
        self.assertContains(page, "0 of 50")
        self.assertEqual(self.client_b.get(self.url("ai-tools")).status_code, 404)
        self.assertRedirects(Client().get(self.url("ai-tools")), reverse("accounts:login"), fetch_redirect_response=False)
        details_only = services.materials.create(self.identity_a, course_id=self.course_a.pk, title="Old",
                                                 original_filename="old.txt", file_type="txt", size_bytes=3)
        self.assertEqual(self.client_a.get(self.url("ai-tools", details_only.pk)).status_code, 404)
        self.assertContains(self.client_a.get(reverse("student_web:material-list")), "Study tools for Week 1 notes")

    def test_confirm_shows_what_is_sent_and_never_sends_or_counts(self):
        page = self.confirm("answer", "What do mitochondria do?")
        self.assertContains(page, "All 62 characters")
        self.assertContains(page, "“What do mitochondria do?”")
        self.assertContains(page, "Sent text cannot be recalled.")
        self.assertContains(page, '<h2 id="warning-heading">Before you send</h2>')
        # Consent warnings can never be folded away (the site's mobile menu is its own <details>).
        self.assertContains(page, '<section class="notice warning ai-warning"')
        self.assertNotContains(page, '<details class="notice')
        self.assertContains(page, "<dt>Not sent</dt>")
        self.assertContains(page, '<button class="button" type="submit">Send</button>', html=False)
        self.assertContains(page, '<button class="button" type="submit">Send with the backup service</button>', html=False)
        self.assertNotContains(page, "secret-name.txt")
        self.assertEqual((FakeConnection.made, self.usage()["used_today"]), ([], 0))

    def test_get_never_sends(self):
        for name in ("ai-confirm", "ai-send"):
            self.assertEqual(self.client_a.get(self.url(name)).status_code, 405)
        self.assertEqual(FakeConnection.made, [])

    def test_question_rules(self):
        self.assertContains(self.confirm("answer", ""), "Type the question you want answered.", status_code=400)
        self.assertContains(self.confirm("quiz", "Why?"), "Questions are only used with", status_code=400)
        self.assertEqual(self.confirm("essay").status_code, 400)

    def test_only_configured_providers_are_offered(self):
        with patch.dict(os.environ, {"UCC_GROK_API_KEY": "", "UCC_GROK_MODEL": ""}):
            page = self.confirm()
            self.assertContains(page, '<button class="button" type="submit">Send</button>', html=False)
            self.assertNotContains(page, "backup service")
            token = page.context["send_form"].initial["token"]
            self.assertEqual(self.send(token, provider="grok").status_code, 400)
        self.assertEqual((FakeConnection.made, self.usage()["used_today"]), ([], 0))
        with patch.dict(os.environ, {"UCC_GEMINI_API_KEY": "", "UCC_GROK_API_KEY": ""}):
            self.assertContains(self.confirm(), "No AI service is set up yet")


class SendTests(AiCase):
    def test_one_click_sends_once_saves_and_shows_the_result(self):
        response = self.send(self.token())
        [ledger] = services.ai.results_for(self.identity_a, self.material.pk)
        self.assertRedirects(response, self.url("ai-request", ledger.request_id), fetch_redirect_response=False)
        result_page = self.client_a.get(self.url("ai-request", ledger.request_id), follow=True)
        self.assertContains(result_page, "Cells are the basic unit of life.")
        self.assertContains(result_page, "&lt;script&gt;alert(1)&lt;/script&gt; is shown as text.")
        self.assertNotContains(result_page, "<script>alert(1)</script>")
        self.assertContains(result_page, "AI-generated: check it against your notes")
        self.assertEqual(len(FakeConnection.made), 1)
        self.assertEqual(self.during_call, [False])
        self.assertEqual(self.usage()["used_today"], 1)

    def test_only_the_text_and_question_are_sent(self):
        services.profiles.create(self.identity_a, display_name="Ada Synthetic", matric_number="SYN/2026/1234")
        self.replies["grok"] = grok_reply(json.dumps(ANSWER))
        self.send(self.token("answer", "What do mitochondria do?"), "answer", "What do mitochondria do?", "grok")
        [(_, _, body, _)] = FakeConnection.made[0].requests
        sent = json.dumps(body)
        self.assertIn(NOTES.decode()[:40], sent)
        self.assertIn("What do mitochondria do?", sent)
        for private in ("alpha", "alpha@example.invalid", "secret-name.txt", "Ada Synthetic", "SYN/2026/1234",
                        "Week 1 notes"):
            self.assertNotIn(private, sent)

    def test_refresh_or_double_click_sends_once(self):
        token = self.token()
        first, second = self.send(token), self.send(token)
        self.assertEqual(first["Location"], second["Location"])
        self.assertEqual((len(FakeConnection.made), self.usage()["used_today"]), (1, 1))

    def test_bad_tokens_never_send(self):
        token = self.token()
        other = services.materials.create_with_file(self.identity_a, title="Other", course_id=self.course_a.pk,
                                                    original_filename="o.txt", file_type="txt", content=b"Other text")
        cases = {
            "forged": ("x" + token[1:], "summary", "", self.material.pk, self.client_a),
            "other tool": (token, "quiz", "", self.material.pk, self.client_a),
            "other material": (token, "summary", "", other.pk, self.client_a),
        }
        for name, (value, tool, question, material, client) in cases.items():
            with self.subTest(name):
                response = client.post(reverse("student_web:ai-send", args=[material]),
                                       {"token": value, "tool": tool, "question": question, "provider": "gemini"})
                self.assertEqual(response.status_code, 400)
        # Another student cannot use it, even on their own material.
        own_b = services.materials.create_with_file(self.identity_b, title="B", course_id=self.course_b.pk,
                                                    original_filename="b.txt", file_type="txt", content=b"B text")
        response = self.client_b.post(reverse("student_web:ai-send", args=[own_b.pk]),
                                      {"token": token, "tool": "summary", "question": "", "provider": "gemini"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.send(token, client=self.client_b).status_code, 404)
        self.assertEqual((FakeConnection.made, self.usage()["used_today"]), ([], 0))

    def test_expired_token_sends_nothing_but_still_finds_a_finished_request(self):
        token = self.token()
        with patch.object(ai_consent, "MAX_AGE_SECONDS", -1):
            self.assertContains(self.send(token), "Confirmations last 10 minutes", status_code=400)
        self.assertEqual(FakeConnection.made, [])
        finished = self.send(token)
        with patch.object(ai_consent, "MAX_AGE_SECONDS", -1):
            self.assertEqual(self.send(token)["Location"], finished["Location"])
        self.assertEqual(len(FakeConnection.made), 1)

    def test_missing_csrf_never_sends(self):
        token = self.token()
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client_a.cookies
        response = strict.post(self.url("ai-send"), {"token": token, "tool": "summary", "question": "",
                                                     "provider": "gemini"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(FakeConnection.made, [])

    def test_failures_are_recorded_and_shown_without_retry_or_fallback(self):
        self.replies["gemini"] = gemini_reply(json.dumps(SUMMARY), reason="MAX_TOKENS")
        response = self.send(self.token())
        page = self.client_a.get(response["Location"])
        self.assertContains(page, "Request failed")
        self.assertContains(page, "cut off before it finished")
        self.assertEqual([c.provider for c in FakeConnection.made], ["gemini"])
        self.assertEqual(services.ai.results_for(self.identity_a, self.material.pk), [])
        self.assertEqual(self.usage()["used_today"], 1)

    def test_every_outcome_after_reserving_is_recorded_and_redirected(self):
        with patch.object(ai_providers, "ask", side_effect=RuntimeError("unexpected")):
            response = self.send(self.token())
        self.assertEqual(response.status_code, 302)
        page = self.client_a.get(response["Location"])
        self.assertContains(page, "could not be completed")
        from django.db import DatabaseError
        with patch.object(services.ai, "succeed", side_effect=DatabaseError("synthetic")):
            response = self.send(self.token())
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client_a.get(response["Location"]), "could not be saved")
        self.assertEqual(self.usage()["used_today"], 2)

    def test_http_errors_show_whether_the_key_or_the_provider_is_at_fault(self):
        for status, status_class, hint in ((401, "4xx", "API key or model name"), (503, "5xx", "problem on its side")):
            with self.subTest(status=status):
                with patch.object(ai_providers, "_connect", lambda provider, s=status: FakeConnection(provider, s, {})):
                    response = self.send(self.token())
                self.assertContains(self.client_a.get(response["Location"]), hint)
                ledger_id = response["Location"].rstrip("/").rsplit("/", 1)[-1]
                ledger = services.ai.get_request(self.identity_a, ledger_id)
                self.assertEqual((ledger.error_category, ledger.status_class), ("http_error", status_class))

    def test_questions_with_control_characters_are_refused(self):
        self.assertContains(self.confirm("answer", "Why\x07 this?"), "hidden control characters", status_code=400)

    def test_daily_limit_hides_send_and_refuses(self):
        token = self.token()
        with patch.object(services, "AI_REQUESTS_PER_DAY", 0):
            self.assertContains(self.send(token), "used all 50 AI requests", status_code=429)
        self.assertEqual(FakeConnection.made, [])
        with patch.object(services, "AI_REQUESTS_PER_DAY", 1):
            self.send(self.token())
        page = self.confirm()
        self.assertContains(page, "1 of 50")
        with patch("student_web.ai_views.services.ai.usage", return_value={"used_today": 50, "daily_limit": 50,
                                                                             "results": 1, "max_results": 500}):
            self.assertNotContains(self.confirm(), '<button class="button" type="submit">Send</button>', html=False)

    def test_session_ending_during_the_call_discards_the_answer(self):
        def connect_and_sign_out(provider):
            self.client_a.logout()
            return FakeConnection(provider, 200, self.replies[provider])
        with patch.object(ai_providers, "_connect", connect_and_sign_out):
            response = self.send(self.token())
        self.assertContains(response, "Please sign in again", status_code=403)
        self.login(self.client_a)
        identity = self.identity(self.client_a)
        self.assertEqual(services.ai.results_for(identity, self.material.pk), [])
        self.assertEqual(services.ai.usage(identity)["used_today"], 1)


class RequestAndResultTests(AiCase):
    def make(self, tool, data, question=""):
        self.replies["gemini"] = gemini_reply(json.dumps(data))
        response = self.send(self.token(tool, question), tool, question)
        return self.client_a.get(response["Location"], follow=True)

    def test_request_page_states(self):
        from datetime import timedelta
        from django.utils import timezone
        ledger, _ = services.ai.reserve(self.identity_a, tool="summary", provider="gemini", model="synthetic-model-1",
                                        characters_sent=10, truncated=False, consent_token_hash="a" * 64)
        page = self.client_a.get(self.url("ai-request", ledger.pk))
        self.assertContains(page, "Working on it")
        self.assertContains(page, 'http-equiv="refresh"')
        later = timezone.now() + timedelta(minutes=3)
        with patch("student_web.ai_views.timezone.now", return_value=later):
            self.assertContains(self.client_a.get(self.url("ai-request", ledger.pk)), "Request interrupted")
        self.assertEqual(self.client_b.get(self.url("ai-request", ledger.pk)).status_code, 404)

    def test_each_tool_renders_and_works_without_javascript(self):
        quiz = self.make("quiz", QUIZ)
        self.assertContains(quiz, 'data-ai-quiz')
        self.assertContains(quiz, "<summary>Show answer</summary>", count=5)
        self.assertContains(quiz, 'data-correct="1"')
        cards = self.make("flashcards", CARDS)
        self.assertContains(cards, "Term 4")
        self.assertContains(cards, "Meaning 4")
        answer = self.make("answer", ANSWER, "Where is it explained?")
        self.assertContains(answer, "Section 2 explains it.")
        self.assertContains(answer, "You asked")
        self.assertContains(answer, "<p>Where is it explained?</p>", html=False)
        for page in (quiz, cards, answer):
            self.assertContains(page, "student_web/ai.js")
            self.assertContains(page, "Download as text")

    def test_study_materials_is_highlighted_on_every_ai_page(self):
        page = self.make("summary", SUMMARY)
        saved = page.context["saved"]
        active = '<a class="nav-link active" href="/materials/" aria-current="page">'
        for url in (self.url("ai-tools"), self.url("ai-result", saved.pk), self.url("ai-request", saved.request_id)):
            response = self.client_a.get(url, follow=True)
            with self.subTest(url=url):
                self.assertContains(response, active)
                self.assertNotContains(response, '<a class="nav-link active" href="/"')

    def test_tools_page_has_one_form_per_tool_and_a_separate_question_form(self):
        page = self.client_a.get(self.url("ai-tools")).content.decode()
        for tool in ("summary", "quiz", "flashcards"):
            self.assertIn(f'<input type="hidden" name="tool" value="{tool}"><input type="hidden" name="question" value="">', page)
        self.assertIn('<input type="hidden" name="tool" value="answer"><label for="ai-question">', page)
        self.assertNotIn('type="radio"', page)
        # A refused question keeps its text, and its error is linked to the box (summary link,
        # inline message, aria-invalid and aria-describedby).
        response = self.confirm("answer", "Why\x07 this?")
        self.assertContains(response, "Why\x07 this?</textarea>", status_code=400)
        self.assertContains(response, '<a href="#ai-question">Your question: Remove the hidden control characters',
                            status_code=400)
        self.assertContains(response, '<ul class="errorlist" id="ai-question-error">', status_code=400)
        self.assertContains(response, 'aria-describedby="ai-question-error ai-question-help" aria-invalid="true"',
                            status_code=400)
        fresh = self.client_a.get(self.url("ai-tools")).content.decode()
        self.assertIn('aria-describedby="ai-question-help">', fresh)
        self.assertNotIn('aria-invalid', fresh)

    def test_download_delete_and_owner_only_access(self):
        page = self.make("quiz", QUIZ)
        saved = page.context["saved"]
        download = self.client_a.get(self.url("ai-result-download", saved.pk))
        self.assertEqual(download["Content-Type"], "text/plain; charset=utf-8")
        self.assertTrue(download["Content-Disposition"].startswith("attachment;"))
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertIn("Answer: B. Reason 1.", download.content.decode())
        for name in ("ai-result", "ai-result-download", "ai-result-delete"):
            self.assertEqual(self.client_b.get(self.url(name, saved.pk)).status_code, 404)
        self.assertEqual(self.client_a.post(self.url("ai-result-delete", saved.pk), {}).status_code, 400)
        self.assertRedirects(self.client_a.post(self.url("ai-result-delete", saved.pk), {"confirm": "on"}),
                             self.url("ai-tools"), fetch_redirect_response=False)
        self.assertEqual(self.client_a.get(self.url("ai-result", saved.pk)).status_code, 404)
        self.assertContains(self.client_a.get(self.url("ai-request", saved.request_id)), "Result deleted")
        self.assertEqual(self.usage()["used_today"], 1)

    def test_an_invalid_saved_result_is_not_displayed(self):
        page = self.make("summary", SUMMARY)
        saved = page.context["saved"]
        with patch.object(ai_providers, "check_result", side_effect=ValueError):
            self.assertContains(self.client_a.get(self.url("ai-result", saved.pk)), "can no longer be displayed")

    def test_deleting_the_material_removes_results_but_not_the_count(self):
        self.make("summary", SUMMARY)
        material = services.materials.retrieve(self.identity_a, self.material.pk)
        services.materials.delete(self.identity_a, material.pk, version=material.record_version)
        self.assertEqual(self.usage(), {"used_today": 1, "daily_limit": 50, "results": 0, "max_results": 500})


class AuditTests(AiCase):
    def test_dashboard_ai_panel_adds_exactly_two_queries_in_the_same_transaction(self):
        from datetime import date
        from django.test.utils import CaptureQueriesContext
        from academics import queries
        with CaptureQueriesContext(connections[database_alias()]) as captured:
            queries.dashboard_reads(self.identity_a, date(2026, 11, 16))
        statements = [query["sql"] for query in captured.captured_queries]
        ai_reads = [sql for sql in statements if 'FROM "academics_studyai' in sql]
        self.assertEqual(len(ai_reads), 2, ai_reads)
        self.assertEqual(sum("ucc_security.current_student()" in sql for sql in statements), 1)

    def test_export_refuses_with_413_when_the_ai_sections_are_too_large(self):
        from academics import queries
        self.send(self.token())
        for limit in ("MAX_EXPORT_AI_REQUESTS", "MAX_AI_RESULTS_PER_STUDENT"):
            with self.subTest(limit=limit), patch.object(queries, limit, 0):
                response = self.client_a.get(reverse("student_web:data-export"))
                self.assertEqual(response.status_code, 413)
                self.assertNotIn("Content-Disposition", response)

    def test_ai_assets_stay_small_and_never_use_browser_storage_or_html_insertion(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "student_web/static/student_web"
        script = (root / "ai.js").read_text()
        self.assertLessEqual((root / "ai.js").stat().st_size, 20_000)
        self.assertLessEqual((root / "ai.css").stat().st_size, 9_500)
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "fetch(", "XMLHttpRequest",
                          "innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function"):
            self.assertNotIn(forbidden, script)
        css = (root / "ai.css").read_text()
        self.assertNotIn("@import", css)
        self.assertNotIn("url(", css)


class DashboardAndExportTests(AiCase):
    def test_dashboard_panel_and_export(self):
        self.send(self.token())
        dashboard = self.client_a.get(reverse("student_web:dashboard"))
        self.assertContains(dashboard, "AI study tools")
        self.assertContains(dashboard, "<strong>1 of 50</strong>", html=False)
        self.assertContains(dashboard, "Summary")
        self.assertNotContains(self.client_b.get(reverse("student_web:dashboard")), "Week 1 notes</span>")
        data = json.loads(self.client_a.get(reverse("student_web:data-export")).content)
        self.assertEqual([r["tool"] for r in data["ai_results"]], ["summary"])
        self.assertEqual([(r["provider"], r["status"]) for r in data["ai_requests"]], [("gemini", "succeeded")])
        self.assertNotIn("consent_token_hash", json.dumps(data))
        self.assertEqual(json.loads(self.client_b.get(reverse("student_web:data-export")).content)["ai_results"], [])
