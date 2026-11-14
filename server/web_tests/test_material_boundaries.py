"""Review follow-ups: exact 10 MiB boundary and the damaged-file page."""
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from academics import services
from .base import WebsiteCase

LIMIT = 10 * 1024 * 1024


class MaterialBoundaryTests(WebsiteCase):
    def upload(self, content, filename='notes.txt'):
        return self.client_a.post(reverse('student_web:material-upload'), {
            'title': 'Week 1 notes', 'course_id': str(self.course_a.pk),
            'file': SimpleUploadedFile(filename, content)})

    def test_exactly_10_mib_is_stored_and_one_byte_more_is_refused(self):
        self.seed()
        self.assertEqual(self.upload(b'a' * (LIMIT + 1)).status_code, 400)
        self.assertEqual(services.materials.list(self.identity_a), [])
        self.assertEqual(self.upload(b'a' * LIMIT).status_code, 302)
        [material] = services.materials.list(self.identity_a)
        self.assertEqual(material.size_bytes, LIMIT)

    def test_damaged_file_shows_a_clear_page_and_sends_nothing(self):
        self.seed()
        self.upload(b'Synthetic notes')
        [material] = services.materials.list(self.identity_a)

        with patch.object(services, 'fingerprint', return_value='0' * 64):
            response = self.client_a.get(reverse('student_web:material-download', args=[material.pk]))
        self.assertContains(response, 'failed an integrity check', status_code=500)
        self.assertNotIn('Content-Disposition', response)
        self.assertNotContains(response, 'Synthetic notes', status_code=500)
