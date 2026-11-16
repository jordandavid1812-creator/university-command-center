"""AI study assistant stage 2: text from TXT and PDF study files, PDFs only in a limited child process."""
import os
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase
from student_web import text_extraction
from student_web.pdf_text_child import PYPDF_LIMITS, clean_text
from student_web.text_extraction import ExtractionFailed, describe, extract_text


def pdf(pages, differences=None, trailer_extra="", streams=None):
    """A small synthetic PDF. `pages` are text strings (one line each, split into Tj lines).

    `differences` maps the font's byte codes to glyph names (for non-Latin text);
    `streams` replaces the page content streams with raw (dictionary, bytes) pairs.
    """
    encoding = (f"/Encoding << /Type /Encoding /Differences [{differences}] >>" if differences
                else "/Encoding /WinAnsiEncoding")
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica {encoding} >>"]
    kids = []
    for index, text in enumerate(pages):
        if streams:
            dictionary, body = streams[index]
        else:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines = [escaped[start:start + 80] for start in range(0, len(escaped), 80)] or [""]
            body = ("BT /F1 10 Tf 12 TL 40 800 Td " + " ".join(f"({line}) Tj T*" for line in lines)
                    + " ET").encode("latin-1")
            dictionary = ""
        objects.append(f"<< {dictionary} /Length {len(body)} >>\nstream\n".encode("latin-1") + body
                       + b"\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >>"
                       f" /Contents {len(objects)} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.7\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + (body if isinstance(body, bytes) else body.encode("latin-1")) + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R {trailer_extra}>>\nstartxref\n{start}\n%%EOF\n".encode()
    return bytes(out)


class FakeChild:
    """Replace the PDF child with a small script for one test."""
    def __init__(self, test, source):
        directory = tempfile.TemporaryDirectory()
        test.addCleanup(directory.cleanup)
        path = Path(directory.name) / "child.py"
        path.write_text(source, encoding="utf-8")
        patcher = patch.object(text_extraction, "CHILD_SCRIPT", path)
        patcher.start()
        test.addCleanup(patcher.stop)


class TextFileTests(SimpleTestCase):
    def test_text_is_cleaned_and_counted(self):
        extracted = extract_text("txt", "Notes\r\nline two\x00\x07\tend\rμ∑".encode("utf-8"))
        self.assertEqual(extracted.text, "Notes\nline two\tend\nμ∑")
        self.assertFalse(extracted.truncated)
        self.assertEqual(describe(extracted), "All 21 characters")

    def test_long_text_is_cut_at_60000_and_says_so(self):
        extracted = extract_text("txt", b"a" * 95000)
        self.assertEqual((extracted.characters, extracted.truncated, extracted.total_characters), (60000, True, 95000))
        self.assertEqual(describe(extracted), "The first 60,000 of 95,000 characters")

    def test_empty_invalid_or_unknown_files_are_refused(self):
        for file_type, content, reason in (("txt", b" \n\t\x00", "no_text"), ("txt", b"\xff\xfe", "unreadable"),
                                           ("txt", b"", "unreadable"), ("doc", b"text", "unsupported"),
                                           ("txt", "text", "unreadable")):
            with self.subTest(reason=reason, content=content):
                with self.assertRaises(ExtractionFailed) as refused:
                    extract_text(file_type, content)
                self.assertEqual(refused.exception.reason, reason)

    def test_cleaning_removes_lone_surrogates_and_controls_but_keeps_text(self):
        self.assertEqual(clean_text("a\ud800b\udfffc\x85d\x7fe​f"), "abcde​f")


class PdfTests(SimpleTestCase):
    def test_text_is_extracted_in_the_child(self):
        extracted = extract_text("pdf", pdf(["Week 1 synthetic notes"]))
        self.assertIn("Week 1 synthetic notes", extracted.text)
        self.assertEqual((extracted.pages_read, extracted.pages_total, extracted.truncated), (1, 1, False))
        self.assertEqual(describe(extracted), f"All {extracted.characters} characters (all 1 page)")

    def test_non_latin_text_survives_on_every_platform(self):
        # Codes 65-68 are drawn as alpha, beta, pi and summation.
        extracted = extract_text("pdf", pdf(["ABCD"], differences="65 /alpha /beta /pi /summation"))
        self.assertIn("αβπ∑", extracted.text)

    def test_long_documents_stop_at_60000_characters(self):
        extracted = extract_text("pdf", pdf(["x" * 40000, "y" * 40000, "z" * 100]))
        self.assertEqual((extracted.characters, extracted.truncated, extracted.pages_read, extracted.pages_total),
                         (60000, True, 2, 3))
        self.assertEqual(describe(extracted), "The first 60,000 characters (pages 1–2 of 3)")

    def test_page_limit_is_300(self):
        extracted = extract_text("pdf", pdf([f"Page {number}" for number in range(301)]))
        self.assertEqual((extracted.pages_read, extracted.pages_total, extracted.truncated), (300, 301, True))
        self.assertIn("pages 1–300 of 301", describe(extracted))

    def test_scans_encrypted_and_broken_files_are_refused(self):
        cases = {
            "no_text": pdf([""]),
            "encrypted": pdf(["Secret"], trailer_extra="/Encrypt << /Filter /Standard /V 1 /R 2 /O <00> /U <00> /P -4 >> "
                                                       "/ID [<00> <00>] "),
            "unreadable": b"%PDF-1.7\nthis is not really a PDF\n%%EOF\n",
        }
        for reason, content in cases.items():
            with self.subTest(reason=reason):
                with self.assertRaises(ExtractionFailed) as refused:
                    extract_text("pdf", content)
                self.assertEqual(refused.exception.reason, reason)

    def test_decompression_bomb_is_stopped_by_the_low_pypdf_limit(self):
        # 25 MB of spaces (valid content, no text) compresses to about 25 KB. pypdf's default
        # limit (75 MB) lets it through as a page without text; the child's 20 MB limit makes it
        # unreadable.
        bomb = zlib.compress(b" " * 25_000_000, 9)
        with self.assertRaises(ExtractionFailed) as refused:
            extract_text("pdf", pdf([""], streams=[("/Filter /FlateDecode", bomb)]))
        self.assertEqual(refused.exception.reason, "unreadable")
        self.assertIsNone(PYPDF_LIMITS["jbig2dec_binary"])

    def test_pypdf_messages_never_reach_stderr(self):
        broken = pdf(["Recovered text"]).replace(b"startxref\n", b"startxref\n9")  # wrong pointer: pypdf warns
        result = subprocess.run([sys.executable, "-I", str(text_extraction.CHILD_SCRIPT)], input=broken,
                                capture_output=True, env=text_extraction.child_environment(), timeout=30)
        self.assertEqual(result.stderr, b"")
        self.assertIn(result.returncode, (0, 5))


class ChildBoundaryTests(SimpleTestCase):
    def test_the_child_sees_none_of_the_websites_secrets(self):
        FakeChild(self, "import json, os, sys\n"
                        "sys.stdout.buffer.write(b'{\"pages_read\": 1, \"pages_total\": 1, \"truncated\": false}\\n'"
                        " + json.dumps(sorted(os.environ)).encode())\n")
        with patch.dict(os.environ, {"UCC_GEMINI_API_KEY": "synthetic", "PGPASSWORD": "synthetic",
                                     "DJANGO_SECRET_KEY": "synthetic"}):
            extracted = extract_text("pdf", b"%PDF-1.7 synthetic")
        names = [name for name in extracted.text.strip("[]").replace('"', "").split(", ") if name]
        self.assertFalse([name for name in names if name.startswith(("UCC_", "PG", "DJANGO_"))], names)
        self.assertEqual(text_extraction.child_environment(), {} if os.name != "nt" else
                         {"SYSTEMROOT": os.environ["SYSTEMROOT"]})

    def test_a_slow_child_is_stopped_at_the_time_limit(self):
        FakeChild(self, "import time\ntime.sleep(60)\n")
        started = time.monotonic()
        with patch.object(text_extraction, "TIME_LIMIT_SECONDS", 1), self.assertRaises(ExtractionFailed) as refused:
            extract_text("pdf", b"%PDF-1.7 synthetic")
        self.assertEqual(refused.exception.reason, "unreadable")
        self.assertLess(time.monotonic() - started, 10)

    def test_oversized_output_is_abandoned(self):
        FakeChild(self, "import sys\nsys.stdout.buffer.write(b'x' * (3 * 1024 * 1024))\n")
        with self.assertRaises(ExtractionFailed) as refused:
            extract_text("pdf", b"%PDF-1.7 synthetic")
        self.assertEqual(refused.exception.reason, "unreadable")

    def test_metadata_and_text_are_checked_strictly(self):
        good = '{"pages_read": 1, "pages_total": 2, "truncated": false}'
        for name, output in {
            "no newline": good.encode(),
            "extra key": b'{"pages_read": 1, "pages_total": 2, "truncated": false, "x": 1}\nText',
            "bool as number": b'{"pages_read": true, "pages_total": 2, "truncated": false}\nText',
            "read beyond total": b'{"pages_read": 3, "pages_total": 2, "truncated": false}\nText',
            "not JSON": b"pages 1 of 2\nText",
            "invalid UTF-8": good.encode() + b"\nText \xff",
            "huge total": b'{"pages_read": 1, "pages_total": 100001, "truncated": false}\nText',
        }.items():
            with self.subTest(name):
                FakeChild(self, f"import sys\nsys.stdout.buffer.write({output!r})\n")
                with self.assertRaises(ExtractionFailed) as refused:
                    extract_text("pdf", b"%PDF-1.7 synthetic")
                self.assertEqual(refused.exception.reason, "unreadable")

    def test_the_parent_recleans_and_caps_the_childs_text(self):
        FakeChild(self, "import sys\nsys.stdout.buffer.write(b'{\"pages_read\": 1, \"pages_total\": 1, "
                        "\"truncated\": false}\\n' + b'\\x00' + b'a' * 70000)\n")
        extracted = extract_text("pdf", b"%PDF-1.7 synthetic")
        self.assertEqual((extracted.characters, extracted.truncated, extracted.text[0]), (60000, True, "a"))

    def test_child_exit_codes(self):
        for code, reason in ((3, "encrypted"), (4, "no_text"), (5, "unreadable"), (1, "unreadable")):
            with self.subTest(code=code):
                FakeChild(self, f"import sys\nsys.exit({code})\n")
                with self.assertRaises(ExtractionFailed) as refused:
                    extract_text("pdf", b"%PDF-1.7 synthetic")
                self.assertEqual(refused.exception.reason, reason)

    def test_a_third_simultaneous_pdf_gets_the_busy_message_at_once(self):
        self.assertTrue(text_extraction._SLOTS.acquire(blocking=False))
        self.assertTrue(text_extraction._SLOTS.acquire(blocking=False))
        try:
            started = time.monotonic()
            with self.assertRaises(ExtractionFailed) as refused:
                extract_text("pdf", pdf(["Text"]))
            self.assertEqual(refused.exception.reason, "busy")
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(extract_text("txt", b"Text files need no slot").text, "Text files need no slot")
        finally:
            text_extraction._SLOTS.release()
            text_extraction._SLOTS.release()

    def test_oversized_input_is_refused_before_starting_a_child(self):
        with patch.object(subprocess, "Popen") as popen, self.assertRaises(ExtractionFailed):
            extract_text("pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024))
        popen.assert_not_called()

    def test_only_the_child_imports_pypdf(self):
        import re
        server = Path(text_extraction.__file__).resolve().parents[1]
        importers = sorted(str(path.relative_to(server)) for path in server.rglob("*.py")
                           if "web_tests" not in path.parts
                           and re.search(r"^\s*(import|from)\s+pypdf\b", path.read_text(encoding="utf-8"), re.M))
        self.assertEqual(importers, [str(Path("student_web") / "pdf_text_child.py")])
