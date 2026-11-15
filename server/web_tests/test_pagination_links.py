"""Pagination shows only links that lead somewhere; placeholders keep the layout."""
from django.urls import reverse
from academics import services
from .base import WebsiteCase


class PaginationLinkTests(WebsiteCase):
    def add_courses(self, count):
        for index in range(count):
            services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code=f'PAGE{index:02}',
                                    name='Synthetic paged course', credit_units=1)

    def test_single_page_shows_no_previous_or_next(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:course-list'))
        self.assertContains(page, 'Page 1 of 1')
        self.assertNotContains(page, 'Previous page')
        self.assertNotContains(page, 'Next page')

    def test_first_page_offers_next_only_and_last_page_previous_only(self):
        self.seed()
        self.add_courses(26)
        first = self.client_a.get(reverse('student_web:course-list'))
        self.assertContains(first, 'Page 1 of 2')
        self.assertContains(first, 'rel="next">Next page</a>')
        self.assertNotContains(first, 'Previous page')
        last = self.client_a.get(reverse('student_web:course-list'), {'page': 2})
        self.assertContains(last, 'Page 2 of 2')
        self.assertContains(last, 'rel="prev">Previous page</a>')
        self.assertNotContains(last, 'Next page')

    def test_middle_page_offers_both_and_links_lead_to_real_pages(self):
        self.seed()
        self.add_courses(60)
        middle = self.client_a.get(reverse('student_web:course-list'), {'page': 2})
        self.assertContains(middle, 'Page 2 of 3')
        self.assertContains(middle, 'rel="prev">Previous page</a>')
        self.assertContains(middle, 'rel="next">Next page</a>')
        following = self.client_a.get(reverse('student_web:course-list') + middle.context['next_url'])
        self.assertContains(following, 'Page 3 of 3')
