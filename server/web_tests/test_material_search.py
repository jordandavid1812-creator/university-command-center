"""Search all study files: text saved once at upload (or on the first search), owner-only results
with highlighted snippets, literal words, and clear notes for files that are not ready or have
no readable text. Synthetic files only; nothing is sent to an AI service."""
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from academics import services
from student_web import search, text_extraction
from .base import WebsiteCase

NOTES = (b"Week 3. TCP is the Transmission Control Protocol. It resends lost packets. "
         b"<script>alert(1)</script> stays text. tcp also appears in lower case. 50% of _marks_.")


class MaterialSearchTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.url = reverse('student_web:material-search')

    def upload(self, content=NOTES, title='Week 3 notes', client=None, course=None):
        data = {'title': title, 'course_id': str((course or self.course_a).pk),
                'file': SimpleUploadedFile('notes.txt', content)}
        return (client or self.client_a).post(reverse('student_web:material-upload'), data)

    def test_upload_saves_text_and_search_highlights_matches(self):
        self.assertEqual(self.upload().status_code, 302)
        self.assertEqual(services.search_texts.missing(self.identity_a, 10), ([], 0))  # saved at upload
        page = self.client_a.get(self.url, {'q': 'tcp'})
        self.assertContains(page, '1 file with “tcp”')
        self.assertContains(page, '<h3>Week 3 notes</h3>', html=False)
        self.assertContains(page, '2 matches')
        self.assertContains(page, '<mark>TCP</mark> is the Transmission', html=False)
        self.assertContains(page, '<mark>tcp</mark> also appears', html=False)
        self.assertContains(page, '&lt;script&gt;alert(1)&lt;/script&gt;', html=False)  # escaped, never run
        self.assertNotContains(page, '<script>alert(1)</script>')

    def test_words_are_literal_and_other_students_never_match(self):
        self.upload()
        self.upload(client=self.client_b, course=self.course_b, title='B notes')
        self.assertContains(self.client_a.get(self.url, {'q': '50%'}), '1 file with')
        self.assertContains(self.client_a.get(self.url, {'q': '5_%'}), 'No files contain')
        page = self.client_a.get(self.url, {'q': 'Transmission'})
        self.assertContains(page, 'Week 3 notes')
        self.assertNotContains(page, 'B notes')

    def test_files_stored_before_search_existed_are_prepared_on_first_search(self):
        for n in range(4):
            services.materials.create_with_file(self.identity_a, title=f'Old notes {n}', course_id=self.course_a.pk,
                                                original_filename=f'old{n}.txt', file_type='txt', content=NOTES)
        first = self.client_a.get(self.url, {'q': 'TCP'})
        self.assertContains(first, '3 files with')  # three prepared per visit
        self.assertContains(first, '1 file is still being prepared for search.')
        second = self.client_a.get(self.url, {'q': 'TCP'})
        self.assertContains(second, '4 files with')
        self.assertNotContains(second, 'still being prepared')

    def test_files_without_text_are_counted_not_searched(self):
        with patch.object(text_extraction, 'extract_text_remembered',
                          side_effect=text_extraction.ExtractionFailed('no_text')):
            self.upload(title='Scanned slides')
        page = self.client_a.get(self.url, {'q': 'TCP'})
        self.assertContains(page, '1 file has no readable text')

    def test_busy_reader_leaves_the_file_for_later(self):
        with patch.object(text_extraction, 'extract_text_remembered',
                          side_effect=text_extraction.ExtractionFailed('busy')):
            self.assertEqual(self.upload().status_code, 302)  # the upload itself still succeeds
            self.assertEqual(services.search_texts.missing(self.identity_a, 10)[1], 1)
        self.assertContains(self.client_a.get(self.url, {'q': 'TCP'}), '1 file with')

    def test_bad_searches_are_refused(self):
        self.assertEqual(self.client_a.get(self.url).status_code, 200)  # empty form
        for bad in ({'q': 'a'}, {'q': 'x' * 101}, {'q': '\x00\x01'}, {'q': 'TCP', 'extra': '1'}):
            with self.subTest(bad=bad):
                self.assertEqual(self.client_a.get(self.url, bad).status_code, 400)
        self.assertEqual(self.client.get(self.url, {'q': 'TCP'}).status_code, 302)  # signed out

    def test_materials_page_has_a_search_box(self):
        page = self.client_a.get(reverse('student_web:material-list'))
        self.assertContains(page, f'action="{self.url}"')
        self.assertContains(page, 'name="q" type="search"')


class SnippetTests(WebsiteCase):
    def test_snippets_cut_around_matches_and_count_all(self):
        text = 'a' * 200 + ' TCP one ' + 'b' * 50 + ' tcp two ' + 'c' * 200 + ' Tcp three Tcp four'
        pieces, count = search.snippets(text, 'tcp')
        self.assertEqual(count, 4)
        self.assertEqual(len(pieces), 3)
        self.assertEqual([p['match'] for p in pieces], ['TCP', 'tcp', 'Tcp'])
        self.assertTrue(pieces[0]['before'].startswith('…'))
        self.assertEqual(search.snippets(text, 'a.b')[1], 0)  # dots are literal, not "any character"
