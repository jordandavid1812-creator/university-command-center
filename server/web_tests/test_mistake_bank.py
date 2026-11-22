"""Mistake bank (owner's choice): save the quiz questions you got wrong, see them with the right
answer, practise them as a quiz built from your own saved quizzes (no AI), remove them. Synthetic
data only; no network (the provider connection is faked, and practice never calls it)."""
import json
from unittest.mock import patch
from django.urls import reverse
from academics import models, services
from tests.test_ai_providers import FakeConnection, gemini_reply, grok_reply
from .test_ai_pages import QUIZ, AiCase


class MistakeBankTests(AiCase):
    def setUp(self):
        super().setUp()
        self.replies = {"gemini": gemini_reply(json.dumps(QUIZ)), "grok": grok_reply(json.dumps(QUIZ))}
        self.send(self.token("quiz"), "quiz")
        self.quiz = services.ai.results_for(self.identity_a, self.material.pk)[0]
        FakeConnection.made = []

    def save(self, numbers, result=None, client=None):
        return (client or self.client_a).post(reverse("student_web:mistakes-save", args=[(result or self.quiz).pk]),
                                              {"question": [str(n) for n in numbers]})

    def test_the_quiz_page_offers_a_save_form_with_one_box_per_question(self):
        page = self.client_a.get(reverse("student_web:ai-result", args=[self.quiz.pk]))
        self.assertContains(page, "Save the ones you got wrong")
        self.assertContains(page, f'action="{reverse("student_web:mistakes-save", args=[self.quiz.pk])}"')
        self.assertEqual(page.content.decode().count('name="question" value='), 5)
        self.assertContains(page, "csrfmiddlewaretoken")

    def test_saving_lists_the_questions_with_the_right_answer_and_reason(self):
        response = self.save([2, 4])
        self.assertRedirects(response, reverse("student_web:mistakes"), fetch_redirect_response=False)
        page = self.client_a.get(reverse("student_web:mistakes"))
        self.assertContains(page, "Saved 2 questions to your Mistake bank.")
        self.assertContains(page, "Question 1?")  # question number 2 is index 1
        self.assertContains(page, "Question 3?")
        self.assertNotContains(page, "Question 0?")
        self.assertContains(page, "<strong>Answer:</strong> Beta", html=False)  # correct index 1
        self.assertContains(page, "Reason 3.")
        self.assertContains(page, "Week 1 notes")
        self.assertContains(page, "2 questions saved")

    def test_saving_twice_keeps_one_copy(self):
        self.save([1, 2])
        self.save([2, 3])
        self.assertEqual(len(services.mistakes.list(self.identity_a)), 3)
        self.save([3])
        page = self.client_a.get(reverse("student_web:mistakes"))
        self.assertContains(page, "Those questions are already in your Mistake bank.")

    def test_bad_question_numbers_are_refused_and_nothing_is_saved(self):
        for numbers in ([], [0], [6], ["x"], [99]):
            with self.subTest(numbers=numbers):
                response = self.save(numbers)
                self.assertIn(response.status_code, (302, 400))
        self.assertEqual(services.mistakes.list(self.identity_a), [])

    def test_only_your_own_quizzes_can_be_saved_and_only_quizzes(self):
        response = self.save([1], client=self.client_b)
        self.assertEqual(response.status_code, 404)
        self.replies = {"gemini": gemini_reply(json.dumps({"points": ["One point."]})),
                        "grok": grok_reply(json.dumps({"points": ["One point."]}))}
        self.send(self.token("summary"), "summary")
        summary = [r for r in services.ai.results_for(self.identity_a, self.material.pk) if r.tool == "summary"][0]
        self.assertEqual(self.save([1], result=summary).status_code, 404)
        self.assertEqual(self.client_a.get(reverse("student_web:mistakes-save", args=[self.quiz.pk])).status_code, 405)
        self.assertEqual(services.mistakes.list(self.identity_b), [])

    def test_each_student_sees_only_their_own_mistakes(self):
        self.save([1])
        page = self.client_b.get(reverse("student_web:mistakes"))
        self.assertContains(page, "No mistakes saved yet")
        self.assertNotContains(page, "Question 0?")
        mistake = services.mistakes.list(self.identity_a)[0]
        response = self.client_b.post(reverse("student_web:mistake-remove", args=[mistake.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(services.mistakes.list(self.identity_a)), 1)

    def test_practice_is_an_interactive_quiz_of_your_mistakes_with_no_ai_call(self):
        self.save([1, 3, 5])
        page = self.client_a.get(reverse("student_web:mistakes-practice"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-ai-quiz")
        self.assertEqual(page.content.decode().count('class="ai-question"'), 3)
        for text in ("Question 0?", "Question 2?", "Question 4?"):
            self.assertContains(page, text)
        self.assertContains(page, "/static/student_web/ai.js")
        self.assertEqual(FakeConnection.made, [])  # nothing was sent to an AI service
        self.assertEqual(self.usage()["used_today"], 1)  # only the original quiz counted

    def test_practice_with_an_empty_bank_goes_back_to_the_bank(self):
        self.assertRedirects(self.client_a.get(reverse("student_web:mistakes-practice")), reverse("student_web:mistakes"))

    def test_remove_and_empty_the_bank(self):
        self.save([1, 2, 3])
        first = services.mistakes.list(self.identity_a)[0]
        self.assertRedirects(self.client_a.post(reverse("student_web:mistake-remove", args=[first.pk])),
                             reverse("student_web:mistakes"))
        self.assertEqual(len(services.mistakes.list(self.identity_a)), 2)
        self.client_a.post(reverse("student_web:mistakes-clear"), {})  # not confirmed
        self.assertEqual(len(services.mistakes.list(self.identity_a)), 2)
        self.client_a.post(reverse("student_web:mistakes-clear"), {"confirm": "yes"})
        self.assertEqual(services.mistakes.list(self.identity_a), [])

    def test_deleting_the_quiz_removes_its_mistakes(self):
        self.save([1, 2])
        self.client_a.post(reverse("student_web:ai-result-delete", args=[self.quiz.pk]), {"confirm": "yes"})
        if services.ai.results_for(self.identity_a, self.material.pk):
            services.ai.delete_result(self.identity_a, self.quiz.pk)
        self.assertEqual(services.mistakes.list(self.identity_a), [])

    def test_the_bank_has_a_limit(self):
        with patch.object(services, "MAX_MISTAKES_PER_STUDENT", 2), patch.object(models, "MAX_MISTAKES_PER_STUDENT", 2):
            self.save([1, 2])
            response = self.save([3])
            self.assertRedirects(response, reverse("student_web:ai-result", args=[self.quiz.pk]),
                                 fetch_redirect_response=False)
        self.assertEqual(len(services.mistakes.list(self.identity_a)), 2)

    def test_download_my_data_includes_the_saved_questions(self):
        self.save([2])
        exported = json.loads(self.client_a.get(reverse("student_web:data-export")).content)
        self.assertEqual([(m["ai_result_id"], m["question_number"]) for m in exported["quiz_mistakes"]],
                         [(str(self.quiz.pk), 2)])

    def test_study_materials_links_to_the_bank(self):
        self.assertContains(self.client_a.get(reverse("student_web:material-list")),
                            f'href="{reverse("student_web:mistakes")}"')

    def test_assets_stay_small(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "student_web/static/student_web"
        self.assertLessEqual((root / "ai.js").stat().st_size, 20_000)
        self.assertLessEqual((root / "ai_choices.css").stat().st_size, 4_000)
