"""Per-deployment upload cap. Vercel refuses request bodies over 4.5 MB before Django runs, so
web_vercel accepts files up to 4,000,000 bytes; everywhere else keeps 10 MiB. The database limit
stays 10 MiB, so files already stored are untouched. Synthetic files only."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from academics import services
from .base import WebsiteCase

CAP = 4_000_000
VERCEL = override_settings(UCC_MAX_UPLOAD_BYTES=CAP, FILE_UPLOAD_MAX_MEMORY_SIZE=CAP + 65536)


@VERCEL
class VercelUploadCapTests(WebsiteCase):
    def upload(self, content, filename='notes.txt'):
        return self.client_a.post(reverse('student_web:material-upload'), {
            'title': 'Week 1 notes', 'course_id': str(self.course_a.pk),
            'file': SimpleUploadedFile(filename, content)})

    def stored(self):
        return services.materials.list(self.identity_a)

    def test_exactly_the_cap_is_stored_and_one_byte_more_is_refused(self):
        self.seed()
        response = self.upload(b'a' * (CAP + 1))
        self.assertContains(response, 'Choose a file no larger than 4 MB.', status_code=400)
        self.assertEqual(self.stored(), [])
        self.assertEqual(self.upload(b'a' * CAP).status_code, 302)
        [material] = self.stored()
        self.assertEqual(material.size_bytes, CAP)

    def test_pdf_over_the_cap_is_refused(self):
        self.seed()
        response = self.upload(b'%PDF-1.7\n' + b'0' * CAP, 'slides.pdf')
        self.assertContains(response, 'no larger than 4 MB', status_code=400)
        self.assertEqual(self.stored(), [])

    def test_whole_request_over_the_allowance_gets_the_clear_413_page(self):
        self.seed()
        response = self.upload(b'a' * (CAP + 70_000))
        self.assertContains(response, 'Choose a PDF or TXT file no larger than 4 MB.', status_code=413)
        self.assertEqual(self.stored(), [])

    def test_the_largest_accepted_request_fits_under_vercels_limit(self):
        # File at the cap plus the other fields and multipart framing must stay under 4.5 MB.
        self.seed()
        self.client_a.get(reverse('student_web:material-upload'))
        response = self.upload(b'a' * CAP, 'n' * 200 + '.txt')
        self.assertEqual(response.status_code, 302)
        self.assertLess(CAP + 65536, 4_500_000)

    def test_page_tells_students_the_cap(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:material-upload'))
        self.assertContains(page, 'PDF or UTF-8 TXT, up to 4 MB.')
        self.assertNotContains(page, '10 MiB')

    def test_files_stored_before_the_cap_still_download(self):
        # A 5 MB file saved when the limit was 10 MiB stays readable (database limit unchanged).
        self.seed()
        content = b'b' * 5_000_000
        material = services.materials.create_with_file(
            self.identity_a, title='Older notes', course_id=self.course_a.pk,
            original_filename='older.txt', file_type='txt', content=content)
        response = self.client_a.get(reverse('student_web:material-download', args=[material.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, content)


class DefaultUploadCapTests(WebsiteCase):
    def test_other_deployments_keep_10_mib(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:material-upload'))
        self.assertContains(page, 'PDF or UTF-8 TXT, up to 10 MiB.')


class UploadCapSettingTests(WebsiteCase):
    def test_cap_outside_1_byte_to_10_mib_stops_the_website(self):
        from django.core.exceptions import ImproperlyConfigured
        from config.settings.web_common import set_upload_cap
        for value in (0, 10 * 1024 * 1024 + 1, 4.0, '4000000', None):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                set_upload_cap({}, value)
        namespace = {}
        set_upload_cap(namespace, 4_000_000)
        self.assertEqual(namespace, {'UCC_MAX_UPLOAD_BYTES': 4_000_000, 'FILE_UPLOAD_MAX_MEMORY_SIZE': 4_065_536})
