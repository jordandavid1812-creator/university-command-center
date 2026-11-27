"""Study material upload page: own courses only, checked files, size guard."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from academics import services
from .base import WebsiteCase


class MaterialUploadPageTests(WebsiteCase):
    def url(self):
        return reverse('student_web:material-upload')

    def post_file(self, course, filename='notes.txt', content=b'Synthetic notes', **changes):
        data = {'title': 'Week 1 notes', 'course_id': str(course.pk),
                'file': SimpleUploadedFile(filename, content), **changes}
        return self.client_a.post(self.url(), data)

    def test_signed_out_visitors_are_sent_to_login(self):
        self.assertRedirects(self.client.get(self.url()), reverse('accounts:login'), fetch_redirect_response=False)

    def test_form_lists_only_own_courses_and_works_without_javascript(self):
        self.seed()
        page = self.client_a.get(self.url())
        self.assertContains(page, 'enctype="multipart/form-data"')
        self.assertContains(page, 'Synthetic A course')
        self.assertNotContains(page, 'Synthetic B course')

    def test_valid_upload_saves_checked_file_facts(self):
        self.seed()
        response = self.post_file(self.course_a)
        self.assertRedirects(response, reverse('student_web:material-list'), fetch_redirect_response=False)
        saved = services.materials.list(self.identity_a)
        self.assertEqual([(m.title, m.original_filename, m.file_type, m.size_bytes) for m in saved],
                         [('Week 1 notes', 'notes.txt', 'txt', 15)])

    def test_other_students_course_and_disguised_files_save_nothing(self):
        self.seed()
        self.assertEqual(self.post_file(self.course_b).status_code, 400)
        self.assertEqual(self.post_file(self.course_a, 'virus.pdf', b'MZ\x90\x00').status_code, 400)
        self.assertEqual(self.post_file(self.course_a, owner_id=str(self.identity_b.student_id)).status_code, 400)
        self.assertEqual(services.materials.list(self.identity_a), [])
        self.assertEqual(services.materials.list(self.identity_b), [])

    def test_oversized_upload_is_refused(self):
        self.seed()
        content = b'a' * (10 * 1024 * 1024 + 70_000)
        response = self.post_file(self.course_a, content=content)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(services.materials.list(self.identity_a), [])