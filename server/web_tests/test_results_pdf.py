"""Results PDF: "Download PDF" on the GPA page opens the printable summary ready to save, named
with today's date, with the student's own profile details (never the matric number)."""
from django.urls import reverse
from academics import services
from .base import WebsiteCase


class ResultsPdfTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()

    def test_overview_offers_download_pdf(self):
        page = self.client_a.get(reverse('student_web:overview'))
        self.assertContains(page, f'href="{reverse("student_web:standing-print")}?save=pdf">Download PDF</a>', html=False)

    def test_summary_is_named_by_date_and_shows_own_profile_details_only(self):
        services.profiles.create(self.identity_a, display_name='Synthetic Alpha', programme='B.Sc. Synthetic',
                                 level='300', institution='Synthetic University')
        page = self.client_a.get(reverse('student_web:standing-print'), {'save': 'pdf'})
        self.assertEqual(page.status_code, 200)
        self.assertRegex(page.content.decode(), r'<title>Academic summary \d{4}-\d{2}-\d{2} - UniCommand</title>')
        for text in ('Synthetic Alpha', 'B.Sc. Synthetic', '300 level', 'Synthetic University', 'Save as PDF'):
            self.assertContains(page, text)
        self.assertNotContains(page, 'Matric / student ID')
        other = self.client_b.get(reverse('student_web:standing-print'))
        self.assertNotContains(other, 'Synthetic Alpha')
        self.assertNotContains(other, 'class="print-details"')
