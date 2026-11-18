"""Text for the AI study assistant from one stored study file (stage 2). No network, no database.

TXT files are already checked UTF-8 and are cleaned here. PDFs are parsed only in a
separate child process (pdf_text_child.py) with no secrets in its environment, a hard
time limit and an output cap; its output is checked strictly before any text is used.
"""
import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from .pdf_text_child import (EXIT_ENCRYPTED, EXIT_NO_TEXT, EXIT_TEXT, MAX_CHARACTERS, MAX_INPUT_BYTES, MAX_PAGES,
                             clean_text)

CHILD_SCRIPT = Path(__file__).with_name("pdf_text_child.py")
TIME_LIMIT_SECONDS = 20
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 200
MAX_TOTAL_PAGES = 100_000
# At most two PDF extractions at once per website process; a third is told to try again.
_SLOTS = threading.BoundedSemaphore(2)

MESSAGES = {
    "encrypted": "This PDF is password-protected, so its text cannot be read.",
    "no_text": "This file has no selectable text (it may be a scan), so there is nothing to send.",
    "unreadable": "This file could not be read.",
    "busy": "Busy reading other files. Try again in a moment.",
    "unsupported": "Only PDF and TXT study files can be used.",
}


class ExtractionFailed(Exception):
    """Nothing was extracted. `reason` is a key of MESSAGES; `message` is safe to show."""
    def __init__(self, reason):
        super().__init__(MESSAGES[reason])
        self.reason = reason
        self.message = MESSAGES[reason]


@dataclass(frozen=True)
class ExtractedText:
    text: str
    truncated: bool
    pages_read: int | None = None       # PDF only
    pages_total: int | None = None      # PDF only
    total_characters: int | None = None  # TXT only (the whole cleaned file)
    picked_from: int | None = None      # "Ask a question": characters the matching parts were picked from
    matched: bool | None = None         # ... and whether any part matched the question's words

    @property
    def characters(self):
        return len(self.text)


def extract_text(file_type, content):
    """Return ExtractedText for one stored file, or raise ExtractionFailed."""
    if type(content) is not bytes or not content or len(content) > MAX_INPUT_BYTES:
        raise ExtractionFailed("unreadable")
    if file_type == "txt":
        return _from_txt(content)
    if file_type == "pdf":
        if not _SLOTS.acquire(blocking=False):
            raise ExtractionFailed("busy")
        try:
            return _from_pdf(content)
        finally:
            _SLOTS.release()
    raise ExtractionFailed("unsupported")


def _from_txt(content):
    try:
        # utf-8-sig drops a leading byte-order mark, as the upload check accepts one.
        text = clean_text(content.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise ExtractionFailed("unreadable") from None
    if not text.strip():
        raise ExtractionFailed("no_text")
    return ExtractedText(text=text[:MAX_CHARACTERS], truncated=len(text) > MAX_CHARACTERS,
                         total_characters=len(text))


def child_environment():
    """Nothing from the website's environment, so the child never sees keys or passwords.
    Windows needs SYSTEMROOT for Python to start."""
    environment = {}
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return environment


def _run_child(content):
    """Run the child; return (exit code, stdout bytes), or None if it could not start,
    ran too long or wrote too much. Any setup failure is a refusal, never a crash."""
    if not sys.executable:  # some servers do not set it; never fall back to a shell or PATH
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="ucc-pdf-", ignore_cleanup_errors=True) as workdir:
            return _run_child_in(workdir, content)
    except (OSError, RuntimeError, ValueError):  # no process slots, file descriptors, threads or disk
        return None


def _run_child_in(workdir, content):
    output, state = [], {"size": 0, "too_large": False}
    process = subprocess.Popen(
        [sys.executable, "-I", str(CHILD_SCRIPT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=child_environment(), cwd=workdir, close_fds=True, shell=False)
    code, threads = None, []
    try:
        def feed():
            try:
                process.stdin.write(content)
            except OSError:  # the child stopped reading (for example it was killed)
                pass
            finally:
                try:
                    process.stdin.close()
                except OSError:
                    pass

        def drain():
            while True:
                chunk = process.stdout.read1(65536)
                if not chunk:
                    return
                state["size"] += len(chunk)
                if state["size"] > MAX_OUTPUT_BYTES:
                    state["too_large"] = True
                    process.kill()
                    return
                output.append(chunk)

        for target in (feed, drain):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            threads.append(thread)
        try:
            code = process.wait(timeout=TIME_LIMIT_SECONDS)
        except subprocess.TimeoutExpired:
            code = None
    finally:
        # Whatever happened above, the child never outlives this call. Once it has ended,
        # its pipes reach end-of-file, so the helper threads finish before the pipes close.
        if process.poll() is None:
            process.kill()
            process.wait()
        for thread in threads:
            thread.join(5)
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except OSError:
                pass
    if code is None or state["too_large"]:
        return None
    return code, b"".join(output)


def _metadata(line):
    if len(line) > MAX_METADATA_BYTES:
        raise ValueError
    data = json.loads(line.decode("ascii"))
    if not isinstance(data, dict) or set(data) != {"pages_read", "pages_total", "truncated"}:
        raise ValueError
    read, total, truncated = data["pages_read"], data["pages_total"], data["truncated"]
    if (type(read) is not int or type(total) is not int or type(truncated) is not bool
            or not 1 <= read <= min(total, MAX_PAGES) or total > MAX_TOTAL_PAGES
            or (not truncated and read != total)):  # "not cut short" must mean every page was read
        raise ValueError
    return read, total, truncated


def _from_pdf(content):
    result = _run_child(content)
    if result is None:
        raise ExtractionFailed("unreadable")
    code, output = result
    if code == EXIT_ENCRYPTED:
        raise ExtractionFailed("encrypted")
    if code == EXIT_NO_TEXT:
        raise ExtractionFailed("no_text")
    if code != EXIT_TEXT:
        raise ExtractionFailed("unreadable")
    line, separator, body = output.partition(b"\n")
    try:
        if not separator:
            raise ValueError
        pages_read, pages_total, truncated = _metadata(line)
        text = clean_text(body.decode("utf-8"))  # strict: invalid UTF-8 is refused
    except (ValueError, UnicodeDecodeError):
        raise ExtractionFailed("unreadable") from None
    if len(text) > MAX_CHARACTERS:
        text, truncated = text[:MAX_CHARACTERS], True
    if not text.strip():
        raise ExtractionFailed("no_text")
    return ExtractedText(text=text, truncated=truncated, pages_read=pages_read, pages_total=pages_total)


# "Ask a question" sends only the parts of the text that best match the question: much less to
# read, so the AI answers in seconds, and the parts about the question are what it sees.
FOCUS_CHARACTERS = 16_000
FOCUS_PIECE = 1_200
_WORD = re.compile(r"[^\W_]+")
_COMMON = frozenset("""the and for are was were has have had can could would should will what which when where who
whom whose why how does did doing this that these those with from into about than then them they their there here
explain define definition meaning mean means describe tell give list name state show write discuss please its
your you our not but all any some more most other such only also very just""".split())


def _question_words(question):
    words = set()
    for word in _WORD.findall(question):
        # Two-letter words count only as capitals (IP, OS); longer ones unless very common.
        if (len(word) >= 3 and word.lower() not in _COMMON) or (len(word) == 2 and word.isupper()):
            words.add(word.lower())
    return words


def _pieces(text):
    """(start, end) pieces of about FOCUS_PIECE characters, cut at whitespace when possible."""
    pieces, start = [], 0
    while start < len(text):
        end = min(start + FOCUS_PIECE, len(text))
        if end < len(text):
            space = text.rfind(" ", start + FOCUS_PIECE // 2, end)
            end = space + 1 if space != -1 else end
        pieces.append((start, end))
        start = end
    return pieces


def focus_on_question(extracted, question):
    """The same text when it is short; otherwise the pieces that mention the question's words most
    (in their original order, up to FOCUS_CHARACTERS), or the first FOCUS_CHARACTERS when none
    match. Deterministic, so the confirm page and the send step pick exactly the same text."""
    text = extracted.text
    if len(text) <= FOCUS_CHARACTERS:
        return extracted
    words = _question_words(question)
    pieces = _pieces(text)
    scored = []
    for index, (start, end) in enumerate(pieces):
        found = [word.lower() for word in _WORD.findall(text[start:end])]
        score = sum(found.count(word) for word in words)
        if score:
            scored.append((-score, index))
    # Best matches first, each with the piece before and after it for context.
    chosen, used = set(), 0
    for _, index in sorted(scored):
        for near in (index, index - 1, index + 1):
            if 0 <= near < len(pieces) and near not in chosen:
                size = pieces[near][1] - pieces[near][0]
                if used + size <= FOCUS_CHARACTERS:
                    chosen.add(near)
                    used += size
    chosen = [pieces[index] for index in sorted(chosen)]
    if chosen:
        # Neighbouring pieces join up again; a gap between parts is marked [...].
        parts, last_end = [], None
        for start, end in chosen:
            if last_end is not None and start == last_end:
                parts[-1] += text[start:end]
            else:
                parts.append(text[start:end])
            last_end = end
        picked = "\n[...]\n".join(part.strip() for part in parts)
    else:
        picked = text[:FOCUS_CHARACTERS]
    # `truncated` keeps describing the file read; the send step records that less than all was sent.
    return dataclasses.replace(extracted, text=picked, picked_from=len(text), matched=bool(chosen))


def describe(extracted):
    """The confirm page's wording, using only facts extraction actually knows."""
    if extracted.picked_from is not None:
        source = describe(dataclasses.replace(extracted, text="x" * extracted.picked_from, picked_from=None))
        source = source[0].lower() + source[1:]
        if extracted.matched:
            return f"The {extracted.characters:,} characters that best match your question, picked from {source}"
        return (f"The first {extracted.characters:,} characters (no part matched your question's words), "
                f"picked from {source}")
    count = f"{extracted.characters:,}"
    if extracted.pages_total is not None:
        if extracted.truncated:
            return (f"The first {count} characters (pages 1–{extracted.pages_read} of "
                    f"{extracted.pages_total:,})")
        pages = "1 page" if extracted.pages_total == 1 else f"{extracted.pages_total:,} pages"
        return f"All {count} characters (all {pages})"
    if extracted.truncated:
        return f"The first {count} of {extracted.total_characters:,} characters"
    return f"All {count} characters"
