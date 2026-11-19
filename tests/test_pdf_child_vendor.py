"""The PDF child finds pypdf when packages live in a separate folder, as on Vercel (/var/task/_vendor).

A fresh virtual environment WITHOUT pypdf runs the real extraction code, with pypdf copied into a
synthetic _vendor folder that only the website's own search path knows about (like Vercel's
startup does). The isolated child (-I, empty environment) must still read the PDF.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
DRIVER = r'''
import sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from student_web import text_extraction
assert "pypdf" not in sys.modules
result = text_extraction.extract_text("pdf", sys.stdin.buffer.read())
assert "pypdf" not in sys.modules  # the website process itself never imports pypdf
sys.stdout.write(result.text)
'''


def synthetic_pdf(words):
    body = b"BT /F1 12 Tf 40 800 Td (" + words + b") Tj ET"
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
    return bytes(pdf)


@unittest.skipIf(os.name == 'nt', 'Vercel runs Linux; the Windows path is covered by test_pdf_child_memory')
class VendorFolderTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec('pypdf')
        if spec is None:
            self.skipTest('pypdf is not installed')
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.vendor = self.folder / '_vendor'
        shutil.copytree(Path(next(iter(spec.submodule_search_locations))), self.vendor / 'pypdf')
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(self.folder / 'bare')], check=True, timeout=120)
        self.python = str(self.folder / 'bare' / 'bin' / 'python')
        bare = subprocess.run([self.python, '-I', '-c', 'import pypdf'], capture_output=True, timeout=60)
        self.assertNotEqual(bare.returncode, 0)  # the bare interpreter really has no pypdf

    def test_isolated_child_reads_pdfs_with_packages_in_a_vendor_folder(self):
        result = subprocess.run([self.python, '-I', '-c', DRIVER, str(self.vendor), str(REPO / 'server')],
                                input=synthetic_pdf(b'Synthetic vendor notes'), capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-2000:])
        self.assertIn('Synthetic vendor notes', result.stdout.decode())

    def test_child_ignores_a_folder_without_pypdf_and_relative_paths(self):
        sys.path.insert(0, str(REPO / 'server'))
        try:
            from student_web import pdf_text_child as child
        finally:
            sys.path.remove(str(REPO / 'server'))
        before = list(sys.path)
        try:
            for argv in (['child', str(self.folder)], ['child', '_vendor'], ['child', str(self.vendor), 'extra'], ['child']):
                with self.subTest(argv=argv):
                    child.use_library_folder(argv)
                    self.assertEqual(sys.path, before)
            child.use_library_folder(['child', str(self.vendor)])
            self.assertEqual(sys.path, before + [str(self.vendor)])  # appended after the standard library
        finally:
            sys.path[:] = before


if __name__ == '__main__':
    unittest.main()
