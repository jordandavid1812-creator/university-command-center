"""Child process that extracts text from one untrusted PDF (AI study assistant, stage 2).

Started by student_web.text_extraction with `python -I`, a minimal environment (no
secrets), a temporary working directory and a hard time limit. Before reading anything
it limits its own memory (Linux: RLIMIT_AS; Windows: a Job Object that also forbids
starting other processes); if that fails it stops without reading the file. It must
stay self-contained: standard library and pypdf only, never project or Django code.

Protocol:
- stdin: the PDF bytes (at most MAX_INPUT_BYTES).
- stdout: one metadata line, a JSON object
  {"pages_read": n, "pages_total": n, "truncated": true|false}, then a newline, then
  the cleaned text as UTF-8.
- exit code: 0 text, 3 encrypted, 4 no selectable text, 5 unreadable.
"""
import ctypes
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


# Windows Job Object structures (winnt.h), from ctypes only: LARGE_INTEGER is 64-bit,
# DWORD 32-bit, SIZE_T and ULONG_PTR pointer-sized.
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100


class JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JobObjectBasicLimitInformation), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _limit_windows_memory(kernel32=None):
    """Put this process in a new Job Object: at most MEMORY_LIMIT_BYTES of memory and no
    other processes. Returns True only if every step succeeded."""
    try:
        if kernel32 is None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.restype = ctypes.c_int
        kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                     ctypes.c_uint32]
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False
        info = JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        info.BasicLimitInformation.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = MEMORY_LIMIT_BYTES
        if not kernel32.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                                                ctypes.byref(info), ctypes.sizeof(info)):
            return False
        # The job handle stays open for this process's whole (short) life.
        return bool(kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()))
    except (AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError):
        return False


def _limit_memory():
    """Limit this process's memory. Returns True if a limit is in place (fail closed)."""
    if os.name == "nt":
        return _limit_windows_memory()
    try:
        import resource
    except ImportError:
        return False
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
        return True
    except (ValueError, OSError):
        # Raising is refused if the existing hard limit is already lower; that is fine.
        hard = resource.getrlimit(resource.RLIMIT_AS)[1]
        return hard != resource.RLIM_INFINITY and hard <= MEMORY_LIMIT_BYTES


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


def use_library_folder(argv):
    """Hosts such as Vercel keep installed packages in a folder that Python's isolated mode (-I)
    does not search. The parent may name that folder as the only argument. It is used only if it
    is an absolute folder that really holds pypdf, and is added AFTER the standard library, so it
    can never replace a standard module."""
    if len(argv) != 2:
        return
    folder = argv[1]
    if (os.path.isabs(folder) and os.path.isfile(os.path.join(folder, "pypdf", "__init__.py"))
            and folder not in sys.path):
        sys.path.append(folder)


def main():
    use_library_folder(sys.argv)
    # pypdf messages (through Python's last-resort log handler) and warnings can contain
    # fragments of the file; this process's stderr goes to the null device. Logging
    # settings are not changed (the parent also discards stderr).
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if not _limit_memory():
        return EXIT_UNREADABLE  # never read an untrusted PDF without a memory limit
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
