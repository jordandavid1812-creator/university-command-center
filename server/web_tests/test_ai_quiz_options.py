"""Quiz options on the website (owner's choice): pick 5/10/15/20 questions and Easy/Normal/Hard/Exam,
see them before sending, and get exactly that request. No network (fake provider connection)."""
import json
from django.core import signing
from student_web import ai_consent, ai_providers
from tests.test_ai_providers import FakeConnection, gemini_reply
from .test_ai_pages import AiCase


def quiz(n):
    return {"questions": [{"question": f"Question {i}?", "options": ["Alpha", "Beta", "Gamma", "Delta"],
                           "correct": i % 4, "reason": f"Reason {i}."} for i in range(n)]}


class QuizOptionPageTests(AiCase):
    def options_confirm(self, count="15", level="hard"):
        return self.client_a.post(self.url("ai-confirm"), {"tool": "quiz", "question": "", "quiz_count": count,
                                                            "quiz_level": level})

    def send_with(self, token, count="15", level="hard"):
        return self.client_a.post(self.url("ai-send"), {"token": token, "tool": "quiz", "question": "",
                                                         "provider": "gemini", "quiz_count": count, "quiz_level": level})

    def test_tools_page_offers_the_choices_with_sensible_defaults(self):
        page = self.client_a.get(self.url("ai-tools"))
        self.assertContains(page, '<select name="quiz_count">')
        for n in (5, 10, 15, 20):
            self.assertContains(page, f'<option value="{n}"')
        self.assertContains(page, '<option value="10" selected>10</option>', html=True)
        for value in ("easy", "normal", "hard", "exam"):
            self.assertContains(page, f'<option value="{value}"')
        self.assertContains(page, '<option value="normal" selected>Normal</option>', html=True)

    def test_confirm_shows_the_choice_and_carries_it_to_send(self):
        page = self.options_confirm()
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "<dt>Quiz</dt><dd>15 questions · Hard</dd>", html=True)
        self.assertContains(page, 'name="quiz_count" value="15"')
        self.assertContains(page, 'name="quiz_level" value="hard"')
        self.assertEqual(self.usage()["used_today"], 0)  # confirming never sends or counts

    def test_send_asks_for_exactly_that_quiz_and_saves_it(self):
        self.replies["gemini"] = gemini_reply(json.dumps(quiz(15)))
        token = self.options_confirm().context["send_form"].initial["token"]
        response = self.send_with(token)
        self.assertEqual(response.status_code, 302)
        [connection] = FakeConnection.made
        body = connection.requests[0][2]
        system = body["systemInstruction"]["parts"][0]["text"]
        self.assertIn("(exactly 15 questions;", system)
        self.assertIn(ai_providers.QUIZ_LEVELS["hard"], system)
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], ai_providers.BIG_QUIZ_OUTPUT_TOKENS)
        result = self.client_a.get(response["Location"], follow=True)
        self.assertContains(result, "15 questions. Choose an answer for each.")
        self.assertEqual(self.usage()["used_today"], 1)

    def test_changing_the_choice_after_confirming_is_refused(self):
        token = self.options_confirm("10", "easy").context["send_form"].initial["token"]
        for count, level in (("20", "easy"), ("10", "exam"), ("", "")):
            with self.subTest(count=count, level=level):
                response = self.send_with(token, count, level)
                self.assertContains(response, "not valid for this file", status_code=400)
        self.assertEqual(FakeConnection.made, [])
        self.assertEqual(self.usage()["used_today"], 0)

    def test_unknown_choices_are_rejected_before_anything_is_sent(self):
        for count, level in (("7", "hard"), ("15", "impossible")):
            with self.subTest(count=count, level=level):
                self.assertEqual(self.options_confirm(count, level).status_code, 400)
        self.assertEqual(FakeConnection.made, [])

    def test_without_choices_the_original_quiz_is_unchanged(self):
        token = self.token("quiz")
        self.send(token, "quiz")
        system = FakeConnection.made[0].requests[0][2]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("(5 to 10 questions;", system)
        self.assertNotIn("Difficulty", system)

    def test_options_are_ignored_for_other_tools(self):
        page = self.client_a.post(self.url("ai-confirm"), {"tool": "summary", "question": "", "quiz_count": "20",
                                                            "quiz_level": "exam"})
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "<dt>Quiz</dt>")
        token = page.context["send_form"].initial["token"]
        self.assertNotIn("o", signing.loads(token, salt=ai_consent.SALT))  # plain tokens keep their shape


class ConsentOptionTests(AiCase):
    def test_tokens_bind_the_quiz_choice(self):
        token = ai_consent.issue("u1", "m1", "quiz", "", 100, options="15:hard")
        ai_consent.check(token, "u1", "m1", "quiz", "", options="15:hard")
        for options in ("", "15:exam", "20:hard"):
            with self.subTest(options=options), self.assertRaises(ai_consent.ConsentInvalid):
                ai_consent.check(token, "u1", "m1", "quiz", "", options=options)
        plain = ai_consent.issue("u1", "m1", "quiz", "", 100)
        ai_consent.check(plain, "u1", "m1", "quiz", "")
        with self.assertRaises(ai_consent.ConsentInvalid):
            ai_consent.check(plain, "u1", "m1", "quiz", "", options="10:normal")

    def test_the_choices_get_their_own_small_stylesheet_on_ai_pages_only(self):
        from pathlib import Path
        self.assertContains(self.client_a.get(self.url("ai-tools")), "/static/student_web/ai_choices.css")
        self.assertNotContains(self.client_a.get(reverse_dashboard()), "ai_choices.css")
        css = (Path(__file__).resolve().parents[1] / "student_web/static/student_web/ai_choices.css")
        self.assertLessEqual(css.stat().st_size, 4_000)
        text = css.read_text()
        for forbidden in ("@import", "url("):
            self.assertNotIn(forbidden, text)
        self.assertIn("prefers-reduced-motion", text)


def reverse_dashboard():
    from django.urls import reverse
    return reverse("student_web:dashboard")

