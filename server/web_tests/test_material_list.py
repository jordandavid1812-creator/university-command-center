"""Study material list and delete: own records only, versioned delete."""
from django.urls import reverse
from academics import services
from .base import WebsiteCase

FACTS = {'original_filename': 'notes.txt', 'file_type': 'txt', 'size_bytes': 2048}


class MaterialListPageTests(WebsiteCase):
    def add(self, identity, course, title):
        return services.materials.create(identity, course_id=course.pk, title=title, **FACTS)

    def test_signed_out_visitors_are_sent_to_login(self):
        self.assertRedirects(self.client.get(reverse('student_web:material-list')), reverse('accounts:login'),
                             fetch_redirect_response=False)

    def test_list_shows_only_own_materials_in_a_scrollable_region(self):
        self.seed()
        self.add(self.identity_a, self.course_a, 'Synthetic A notes')
        self.add(self.identity_b, self.course_b, 'Synthetic B notes')
        page = self.client_a.get(reverse('student_web:material-list'))
        self.assertContains(page, 'Synthetic A notes')
        self.assertNotContains(page, 'Synthetic B notes')
        self.assertContains(page, 'role="region" aria-label="Your study materials" tabindex="0"')
        self.assertContains(page, reverse('student_web:material-list'))

    def test_empty_list_invites_first_upload(self):
        self.seed()
        self.assertContains(self.client_a.get(reverse('student_web:material-list')), 'Add your first material')

    def test_delete_own_material_with_confirmation_and_version(self):
        self.seed()
        material = self.add(self.identity_a, self.course_a, 'Synthetic A notes')
        url = reverse('student_web:material-delete', args=[material.pk])
        self.assertContains(self.client_a.get(url), 'Synthetic A notes')
        self.assertEqual(self.client_a.post(url, {'version': 1}).status_code, 400)
        response = self.client_a.post(url, {'version': 1, 'confirm': 'on'})
        self.assertRedirects(response, reverse('student_web:material-list'), fetch_redirect_response=False)
        self.assertEqual(services.materials.list(self.identity_a), [])

    def test_stale_delete_is_refused(self):
        self.seed()
        material = self.add(self.identity_a, self.course_a, 'Synthetic A notes')
        services.materials.update(self.identity_a, material.pk, version=1, title='Renamed notes')
        url = reverse('student_web:material-delete', args=[material.pk])
        self.assertEqual(self.client_a.post(url, {'version': 1, 'confirm': 'on'}).status_code, 409)
        self.assertEqual(len(services.materials.list(self.identity_a)), 1)

    def test_cannot_view_or_delete_another_students_material(self):
        self.seed()
        theirs = self.add(self.identity_b, self.course_b, 'Synthetic B notes')
        url = reverse('student_web:material-delete', args=[theirs.pk])
        self.assertEqual(self.client_a.get(url).status_code, 404)
        self.assertEqual(self.client_a.post(url, {'version': 1, 'confirm': 'on'}).status_code, 404)
        self.assertEqual(len(services.materials.list(self.identity_b)), 1)

    def test_course_with_materials_explains_why_it_cannot_be_deleted(self):
        self.seed()
        course = services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='MAT101',
                                         name='Synthetic materials course', credit_units=3)
        self.add(self.identity_a, course, 'Synthetic A notes')
        response = self.client_a.post(reverse('student_web:course-delete', args=[course.pk]),
                                      {'version': 1, 'confirm': 'on'})
        self.assertContains(response, 'study materials', status_code=400)
