"""AI speed: Gemini 3 "thinking" is kept low, and "Ask a question" sends only the parts of the
file that match the question. No network: requests are only built and inspected."""
import os
import unittest
from unittest.mock import patch

from server.student_web import ai_providers, text_extraction
from server.student_web.text_extraction import ExtractedText, FOCUS_CHARACTERS, focus_on_question


def body_for(model, **env):
    with patch.dict(os.environ, env):
        return ai_providers.gemini_request(model, "synthetic-key", "system", "user", "answer")[2]


class ThinkingTests(unittest.TestCase):
    def test_gemini_3_models_think_at_a_low_level_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ai_providers.THINKING_VARIABLE, None)
            config = ai_providers.gemini_request("gemini-3.6-flash", "k", "s", "u", "quiz")[2]["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertEqual((config["maxOutputTokens"], config["responseMimeType"]), (4096, "application/json"))

    def test_owner_can_choose_the_level_or_send_none(self):
        self.assertEqual(body_for("gemini-3.6-flash", UCC_GEMINI_THINKING="minimal")["generationConfig"]["thinkingConfig"],
                         {"thinkingLevel": "minimal"})
        for value in ("default", "fast", "LOW", "low; drop", " low"):
            with self.subTest(value=value):
                config = body_for("gemini-3.6-flash", UCC_GEMINI_THINKING=value)["generationConfig"]
                self.assertNotIn("thinkingConfig", config)  # only exact lower-case level names are used

    def test_other_models_never_get_a_thinking_setting(self):
        for model in ("gemini-2.5-flash", "synthetic-model-1", "gemini-pro"):
            with self.subTest(model=model):
                self.assertNotIn("thinkingConfig", body_for(model)["generationConfig"])
        grok = ai_providers.grok_request("grok-model", "k", "s", "u", "answer")[2]
        self.assertNotIn("reasoning_effort", grok)


FILLER = "General studies notes about reading, writing and communication skills. " * 1000
TCP = "TCP is the Transmission Control Protocol. TCP resends lost packets over a reliable connection. "


class FocusTests(unittest.TestCase):
    def long_file(self):
        text = FILLER[:30000] + TCP * 3 + FILLER[:26000] + "Network layer and IP addresses. " * 5
        return ExtractedText(text=text[:60000], truncated=True, pages_read=40, pages_total=212)

    def test_only_matching_parts_with_context_are_sent(self):
        extracted = self.long_file()
        focused = focus_on_question(extracted, "What is TCP?")
        self.assertTrue(focused.matched)
        self.assertIn("Transmission Control Protocol", focused.text)
        self.assertLess(focused.characters, 6000)  # the match and its neighbours, not 60,000
        self.assertTrue(focused.text in extracted.text or "[...]" in focused.text)
        self.assertEqual(focus_on_question(extracted, "What is TCP?"), focused)  # same every time
        self.assertEqual(text_extraction.describe(focused),
                         f"The {focused.characters:,} characters that best match your question, picked from "
                         f"the first {extracted.characters:,} characters (pages 1–40 of 212)")

    def test_short_acronyms_and_order(self):
        focused = focus_on_question(self.long_file(), "Compare TCP and IP")
        self.assertIn("IP addresses", focused.text)
        self.assertLess(focused.text.index("Transmission"), focused.text.index("IP addresses"))  # file order
        self.assertLessEqual(focused.characters, FOCUS_CHARACTERS + 50)

    def test_no_match_sends_the_start_and_says_so(self):
        focused = focus_on_question(self.long_file(), "Explain photosynthesis")
        self.assertFalse(focused.matched)
        self.assertEqual(focused.text, self.long_file().text[:FOCUS_CHARACTERS])
        self.assertIn("no part matched your question's words", text_extraction.describe(focused))

    def test_short_files_are_sent_whole(self):
        short = ExtractedText(text="TCP notes " * 100, truncated=False)
        self.assertIs(focus_on_question(short, "TCP"), short)


if __name__ == "__main__":
    unittest.main()


class RememberedPdfTests(unittest.TestCase):
    """The confirm page and Send read the same PDF: the second read comes from memory."""

    def setUp(self):
        text_extraction._recent.clear()
        self.addCleanup(text_extraction._recent.clear)
        self.reads = []

        def fake_pdf(content):
            self.reads.append(content)
            return ExtractedText(text=f"text of {len(content)} bytes", truncated=False, pages_read=1, pages_total=1)
        patcher = patch.object(text_extraction, "_from_pdf", fake_pdf)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_same_bytes_are_read_once_and_different_bytes_again(self):
        first = text_extraction.extract_text_remembered("pdf", b"%PDF synthetic one")
        again = text_extraction.extract_text_remembered("pdf", b"%PDF synthetic one")
        other = text_extraction.extract_text_remembered("pdf", b"%PDF synthetic other")
        self.assertIs(first, again)
        self.assertEqual(len(self.reads), 2)
        self.assertNotEqual(first, other)
        # The plain reader is unchanged: it never uses the memory.
        text_extraction.extract_text("pdf", b"%PDF synthetic one")
        self.assertEqual(len(self.reads), 3)

    def test_memory_expires_and_holds_only_a_few_files(self):
        with patch.object(text_extraction.time, "monotonic", return_value=1000.0):
            text_extraction.extract_text_remembered("pdf", b"%PDF synthetic one")
        with patch.object(text_extraction.time, "monotonic", return_value=1000.0 + 15 * 60 + 1):
            text_extraction.extract_text_remembered("pdf", b"%PDF synthetic one")
        self.assertEqual(len(self.reads), 2)  # read again after 15 minutes
        for number in range(6):
            text_extraction.extract_text_remembered("pdf", f"%PDF synthetic {number}".encode())
        self.assertLessEqual(len(text_extraction._recent), 4)

    def test_text_files_and_failures_are_never_remembered(self):
        text_extraction.extract_text_remembered("txt", b"Plain notes")
        self.assertEqual(len(text_extraction._recent), 0)
        with patch.object(text_extraction, "_from_pdf", side_effect=text_extraction.ExtractionFailed("no_text")):
            with self.assertRaises(text_extraction.ExtractionFailed):
                text_extraction.extract_text_remembered("pdf", b"%PDF synthetic broken")
        self.assertEqual(len(text_extraction._recent), 0)
