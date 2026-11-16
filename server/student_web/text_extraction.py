"""Text for the AI study assistant from one stored study file (stage 2). No network, no database.

TXT files are already checked UTF-8 and are cleaned here. PDFs are parsed only in a
separate child process (pdf_text_child.py) with no secrets in its environment, a hard
time limit and an output cap; its output is checked strictly before any text is used.
"""
import json
import os
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


def describe(extracted):
    """The confirm page's wording, using only facts extraction actually knows."""
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
