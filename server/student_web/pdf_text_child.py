"""Child process that extracts text from one untrusted PDF (AI study assistant, stage 2).

Started by student_web.text_extraction with `python -I`, a minimal environment (no
secrets), a temporary working directory and a hard time limit. It must stay
self-contained: standard library and pypdf only, never project or Django code.

Protocol:
- stdin: the PDF bytes (at most MAX_INPUT_BYTES).
- stdout: one metadata line, a JSON object
  {"pages_read": n, "pages_total": n, "truncated": true|false}, then a newline, then
  the cleaned text as UTF-8.
- exit code: 0 text, 3 encrypted, 4 no selectable text, 5 unreadable.
"""
import io
import json
import os
import re
import sys

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_CHARACTERS = 60000
MAX_PAGES = 300
MEMORY_LIMIT_BYTES = 768 * 1024 * 1024
EXIT_TEXT, EXIT_ENCRYPTED, EXIT_NO_TEXT, EXIT_UNREADABLE = 0, 3, 4, 5

# Control characters except tab and line feed, C1 controls, and lone surrogates.
_UNWANTED = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")

# Low limits for pypdf (the defaults allow 75 MB per stream). jbig2dec_binary=None
# means pypdf never starts an outside program for JBIG2 images.
PYPDF_LIMITS = {
    "maximum_declared_stream_length": 11_000_000,
    "array_based_stream_maximum_output_length": 20_000_000,
    "jbig2_maximum_output_length": 20_000_000,
    "lzw_maximum_output_length": 20_000_000,
    "run_length_maximum_output_length": 20_000_000,
    "zlib_maximum_output_length": 20_000_000,
    "brotli_maximum_output_length": 20_000_000,
    "image_maximum_buffer_size": 20_000_000,
    "stream_decoding_work_maximum_length": 50_000_000,
    "jbig2dec_binary": None,
}


def clean_text(text):
    """Line breaks as \\n; no control characters (except tab and line feed) or lone surrogates."""
    return _UNWANTED.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def _limit_memory():
    try:
        import resource  # not available on Windows: there the time limit still applies
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (ImportError, ValueError, OSError):
        pass


def extract(data):
    """Return (exit code, metadata, text). Never raises."""
    import warnings
    warnings.simplefilter("ignore")
    try:
        import pypdf
        pypdf.overwrite_configuration(**PYPDF_LIMITS)
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
        except Exception:
            # Some encrypted files fail while opening; never try a password.
            return (EXIT_ENCRYPTED if b"/Encrypt" in data else EXIT_UNREADABLE), None, ""
        if reader.is_encrypted:
            return EXIT_ENCRYPTED, None, ""
        pages = reader.pages
        total = len(pages)
        pieces, count, pages_read, truncated = [], 0, 0, False
        for index in range(min(total, MAX_PAGES)):
            piece = ("\n\n" if pieces else "") + clean_text(pages[index].extract_text() or "")
            pages_read += 1
            if count + len(piece) > MAX_CHARACTERS:
                pieces.append(piece[:MAX_CHARACTERS - count])
                count, truncated = MAX_CHARACTERS, True
                break
            pieces.append(piece)
            count += len(piece)
            if count == MAX_CHARACTERS and index + 1 < total:
                truncated = True
                break
        else:
            truncated = total > MAX_PAGES
    except Exception:  # includes RecursionError and MemoryError from malformed files
        return EXIT_UNREADABLE, None, ""
    text = "".join(pieces)
    if not text.strip():
        return EXIT_NO_TEXT, None, ""
    return EXIT_TEXT, {"pages_read": pages_read, "pages_total": total, "truncated": truncated}, text


def main():
    # pypdf messages (through Python's last-resort log handler) and warnings can contain
    # fragments of the file; this process's stderr goes to the null device. Logging
    # settings are not changed (the parent also discards stderr).
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
    _limit_memory()
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        return EXIT_UNREADABLE
    code, metadata, text = extract(data)
    if code == EXIT_TEXT:
        # UTF-8 bytes, never the console code page (Windows pipes default to it).
        sys.stdout.buffer.write(json.dumps(metadata).encode("ascii") + b"\n" + text.encode("utf-8"))
        sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
