"""Stored study files: private downloads, list status, quota message and safe headers."""
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from academics import services
from .base import WebsiteCase


class MaterialDownloadTests(WebsiteCase):
    def upload(self, filename='notes.txt', content=b'Synthetic notes', client=None, course=None):
        data = {'title': 'Week 1 notes', 'course_id': str((course or self.course_a).pk),
                'file': SimpleUploadedFile(filename, content)}
        return (client or self.client_a).post(reverse('student_web:material-upload'), data)

    def only_material(self, identity=None):
        [material] = services.materials.list(identity or self.identity_a)
        return material

    def download(self, material, client=None):
        return (client or self.client_a).get(reverse('student_web:material-download', args=[material.pk]))

    def test_uploaded_file_downloads_privately_as_an_attachment(self):
        self.seed()
        self.assertEqual(self.upload().status_code, 302)
        response = self.download(self.only_material())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'Synthetic notes')
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="notes.txt"')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', response['Content-Security-Policy'])
        self.assertIn('no-store', response['Cache-Control'])

    def test_pdf_keeps_its_type_and_unusual_names_are_encoded_safely(self):
        self.seed()
        self.upload('week 1 "slides" résumé.PDF', b'%PDF-1.7 synthetic')
        response = self.download(self.only_material())
        self.assertEqual(response['Content-Type'], 'application/pdf')
        disposition = response['Content-Disposition']
        self.assertTrue(disposition.startswith('attachment; '))
        self.assertIn("filename*=utf-8''", disposition)
        self.assertNotIn('\n', disposition)

    def test_other_students_and_signed_out_visitors_cannot_download(self):
        self.seed()
        self.upload()
        material = self.only_material()
        self.assertEqual(self.download(material, self.client_b).status_code, 404)
        self.assertRedirects(self.download(material, self.client), reverse('accounts:login'),
                             fetch_redirect_response=False)

    def test_list_offers_download_only_when_a_file_is_stored(self):
        self.seed()
        self.upload()
        services.materials.create(self.identity_a, course_id=self.course_a.pk, title='Details only',
                                  original_filename='old.txt', file_type='txt', size_bytes=10)
        page = self.client_a.get(reverse('student_web:material-list'))
        self.assertContains(page, 'Download Week 1 notes')
        self.assertNotContains(page, 'Download Details only')
        self.assertContains(page, 'File not stored. Upload again to keep a copy.', count=1)

    def test_details_only_record_has_no_download(self):
        self.seed()
        material = services.materials.create(self.identity_a, course_id=self.course_a.pk, title='Details only',
                                             original_filename='old.txt', file_type='txt', size_bytes=10)
        self.assertEqual(self.download(material).status_code, 404)

    def test_full_storage_shows_a_clear_message_and_saves_nothing(self):
        self.seed()
        with patch.object(services, 'MAX_FILES_PER_STUDENT', 1):
            self.assertEqual(self.upload().status_code, 302)
            response = self.upload('more.txt')
        self.assertContains(response, 'storage is full', status_code=400)
        self.assertEqual(len(services.materials.list(self.identity_a)), 1)
