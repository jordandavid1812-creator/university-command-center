"""The PDF child limits its own memory before reading a file, and stops if it cannot.

Runs without Django or a database. The Windows-only tests are skipped elsewhere; run them
on a Windows PC with:  python -m unittest tests.test_pdf_child_memory -v
"""
import ctypes
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.student_web import pdf_text_child as child

CHILD = Path(child.__file__)
STUDENT_WEB = CHILD.parent


class FakeKernel32:
    """Stands in for kernel32 and records the calls, so the Windows steps can be checked anywhere."""
    def __init__(self, fail=None):
        self.calls, self.fail, self.info = [], fail, None

        def call(name, result):
            def function(*args):
                self.calls.append(name)
                if name == "SetInformationJobObject":
                    self.info = (args[1], ctypes.cast(args[2], ctypes.POINTER(
                        child.JobObjectExtendedLimitInformation)).contents, args[3])
                if name == "AssignProcessToJobObject":
                    self.assigned = args
                return 0 if name == self.fail else result
            return function

        self.CreateJobObjectW = call("CreateJobObjectW", 1234)
        self.SetInformationJobObject = call("SetInformationJobObject", 1)
        self.GetCurrentProcess = call("GetCurrentProcess", 99)
        self.AssignProcessToJobObject = call("AssignProcessToJobObject", 1)


class JobObjectTests(unittest.TestCase):
    @unittest.skipUnless(ctypes.sizeof(ctypes.c_void_p) == 8, "layout checked for 64-bit Python")
    def test_structures_match_the_windows_64_bit_layout(self):
        self.assertEqual(ctypes.sizeof(child.JobObjectBasicLimitInformation), 64)
        self.assertEqual(ctypes.sizeof(child.IoCounters), 48)
        self.assertEqual(ctypes.sizeof(child.JobObjectExtendedLimitInformation), 144)
        self.assertEqual(child.JobObjectBasicLimitInformation.LimitFlags.offset, 16)
        self.assertEqual(child.JobObjectBasicLimitInformation.ActiveProcessLimit.offset, 40)
        self.assertEqual(child.JobObjectExtendedLimitInformation.ProcessMemoryLimit.offset, 112)

    def test_the_job_limits_memory_and_forbids_other_processes(self):
        kernel32 = FakeKernel32()
        # The fake's addresses are not real handles, so pass them through as plain integers.
        with patch.object(ctypes, "byref", side_effect=lambda value: ctypes.addressof(value)):
            self.assertTrue(child._limit_windows_memory(kernel32))
        self.assertEqual(kernel32.calls, ["CreateJobObjectW", "SetInformationJobObject", "GetCurrentProcess",
                                          "AssignProcessToJobObject"])
        information_class, info, size = kernel32.info
        self.assertEqual((information_class, size), (9, ctypes.sizeof(child.JobObjectExtendedLimitInformation)))
        self.assertEqual(info.BasicLimitInformation.LimitFlags, 0x100 | 0x8)
        self.assertEqual(info.BasicLimitInformation.ActiveProcessLimit, 1)
        self.assertEqual(info.ProcessMemoryLimit, 768 * 1024 * 1024)
        self.assertEqual(kernel32.assigned, (1234, 99))

    def test_any_failed_step_means_no_limit(self):
        for step in ("CreateJobObjectW", "SetInformationJobObject", "AssignProcessToJobObject"):
            with self.subTest(step=step), patch.object(ctypes, "byref",
                                                       side_effect=lambda value: ctypes.addressof(value)):
                self.assertFalse(child._limit_windows_memory(FakeKernel32(fail=step)))

        class Broken:
            def __getattr__(self, name):
                raise AttributeError(name)
        self.assertFalse(child._limit_windows_memory(Broken()))

    def test_without_a_limit_the_child_stops_before_reading_the_file(self):
        stdin = io.TextIOWrapper(io.BytesIO(b"%PDF-1.7 synthetic"))
        with patch.object(child, "_limit_memory", return_value=False), patch.object(sys, "stdin", stdin), \
                patch.object(sys, "stderr", sys.stderr), patch.object(child, "open", create=True,
                                                                      return_value=io.StringIO()), \
                patch.object(child, "extract") as extract:
            self.assertEqual(child.main(), child.EXIT_UNREADABLE)
        extract.assert_not_called()
        self.assertEqual(stdin.buffer.tell(), 0)


def process_is_gone(pid):
    """True if no process with this ID is running (Windows: also checks it has exited)."""
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE, QUERY_LIMITED_INFORMATION
        if not handle:
            return True
        try:
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 5000) == 0  # WAIT_OBJECT_0
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


class TimeLimitTests(unittest.TestCase):
    def test_the_real_python_process_is_gone_after_the_time_limit(self):
        """On Windows, sys.executable in a virtual environment is a launcher that starts the real
        interpreter; killing the launcher must end that interpreter too."""
        from server.student_web import text_extraction
        with tempfile.TemporaryDirectory() as folder:
            pid_file = Path(folder) / "pid.txt"
            script = Path(folder) / "slow_child.py"
            script.write_text(f"import os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
                              "time.sleep(60)\n", encoding="utf-8")
            started = time.monotonic()
            with patch.object(text_extraction, "CHILD_SCRIPT", script), \
                    patch.object(text_extraction, "TIME_LIMIT_SECONDS", 3), \
                    self.assertRaises(text_extraction.ExtractionFailed):
                text_extraction.extract_text("pdf", b"%PDF-1.7 synthetic")
            elapsed = time.monotonic() - started
            pid = int(pid_file.read_text())
        # Killed at the 3-second limit, not left to finish its 60-second sleep.
        self.assertLess(elapsed, 20)
        self.assertTrue(process_is_gone(pid), f"process {pid} is still running")


def run_limited(code):
    """Run `code` in a fresh, isolated Python after the child's own memory limit is applied."""
    script = (f"import sys\nsys.path.insert(0, {str(STUDENT_WEB)!r})\nimport pdf_text_child as child\n"
              f"if not child._limit_memory():\n    print('NO LIMIT'); sys.exit(2)\n{code}")
    environment = {"SYSTEMROOT": os.environ["SYSTEMROOT"]} if os.name == "nt" else {}
    return subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, env=environment, timeout=60)


class RealLimitTests(unittest.TestCase):
    """Real processes: the limit must hold on this operating system."""

    @unittest.skipUnless(os.name in ("nt", "posix") and sys.platform != "darwin", "Windows or Linux only")
    def test_one_gibibyte_is_refused(self):
        result = run_limited("try:\n    block = bytearray(1024 ** 3)\n    print('ALLOCATED')\n"
                             "except MemoryError:\n    print('REFUSED')\n")
        self.assertEqual(result.stdout.decode().strip(), "REFUSED", result.stderr.decode(errors="replace"))

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_child_cannot_start_another_process(self):
        result = run_limited("import subprocess\ntry:\n    subprocess.run(['cmd', '/c', 'exit'], timeout=10)\n"
                             "    print('STARTED')\nexcept OSError:\n    print('REFUSED')\n")
        self.assertEqual(result.stdout.decode().strip(), "REFUSED", result.stderr.decode(errors="replace"))

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_child_still_reads_a_normal_pdf(self):
        try:
            import pypdf  # noqa: F401  (installed from requirements-django-lock.txt)
        except ImportError:
            self.skipTest("pypdf is not installed")
        body = b"BT /F1 12 Tf 40 800 Td (Synthetic Windows notes) Tj ET"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >>"
                   b" /Contents 5 0 R >>",
                   b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"]
        pdf, offsets = bytearray(b"%PDF-1.7\n"), []
        for number, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
        start = len(pdf)
        pdf += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
        pdf += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % start
        result = subprocess.run([sys.executable, "-I", str(CHILD)], input=bytes(pdf), capture_output=True,
                                env={"SYSTEMROOT": os.environ["SYSTEMROOT"]}, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Synthetic Windows notes", result.stdout)


if __name__ == "__main__":
    unittest.main()
