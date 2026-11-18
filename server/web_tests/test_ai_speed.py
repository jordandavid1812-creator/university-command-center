"""'Ask a question' sends only the matching parts of a long file, and the confirm page says so.
The confirm page and the send step pick exactly the same text (the consent token checks its size)."""
import json
from academics import services
from tests.test_ai_providers import FakeConnection, gemini_reply
from .test_ai_pages import AiCase

FILLER = "General studies notes about reading, writing and communication skills. " * 1000
TCP = "TCP is the Transmission Control Protocol. TCP resends lost packets over a reliable connection. "
LONG = (FILLER[:30000] + TCP * 3 + FILLER[:30000]).encode()


class FocusedQuestionTests(AiCase):
    def setUp(self):
        super().setUp()
        self.material = services.materials.create_with_file(
            self.identity_a, title="Long notes", course_id=self.course_a.pk, original_filename="long.txt",
            file_type="txt", content=LONG)
        self.replies["gemini"] = gemini_reply(json.dumps({"answer": "TCP is a protocol.", "not_covered": False}))

    def test_confirm_describes_and_send_sends_only_the_matching_parts(self):
        page = self.confirm("answer", "What is TCP?")
        self.assertContains(page, "characters that best match your question, picked from the first 60,000")
        sent = self.send(self.token("answer", "What is TCP?"), "answer", "What is TCP?")
        self.assertEqual(sent.status_code, 302)
        body = FakeConnection.made[-1].requests[0][2]
        user_text = body["contents"][0]["parts"][0]["text"]
        self.assertIn("Transmission Control Protocol", user_text)
        self.assertLess(len(user_text), 8000)  # not the 60,000 characters it used to send
        # The record of the request shows exactly how much was sent, and that it was not the whole file.
        from django.urls import reverse
        export = json.loads(self.client_a.get(reverse("student_web:data-export")).content)
        record = export["ai_requests"][0]
        self.assertEqual((record["status"], record["truncated"]), ("succeeded", True))
        self.assertLess(record["characters_sent"], 8000)
        self.assertEqual(self.usage()["used_today"], 1)

    def test_other_tools_still_use_the_whole_extract(self):
        page = self.confirm("summary")
        self.assertContains(page, "The first 60,000 of")
        self.assertNotContains(page, "best match your question")
