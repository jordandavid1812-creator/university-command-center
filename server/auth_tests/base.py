from datetime import date
from django.contrib.auth import get_user
from django.core import mail
from django.test import Client, RequestFactory, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import Student
from accounts.principals import principal_for_request
from academics.ownership import identity_for_verified_student
from academics.services import assignments, courses, semesters

PASSWORD = 'Synthetic-Academic!83'
NEW_PASSWORD = 'Fresh-Synthetic!94'


class AuthenticationCase(TransactionTestCase):
    databases = {'default', 'runtime', 'auth'}

    def setUp(self):
        mail.outbox = []
        self.a = self.make_student('alpha')
        self.b = self.make_student('bravo')
        self.client_a = Client()
        self.client_b = Client()

    def make_student(self, name, verified=True, active=True):
        return Student.objects.db_manager('default').create_user(
            name, PASSWORD, email=f'{name}@example.invalid', is_active=active,
            email_verified_at=timezone.now() if verified else None)

    def login(self, client=None, username='alpha', password=PASSWORD):
        return (client or self.client_a).post(reverse('accounts:login'), {'username': username, 'password': password})

    def identity(self, client):
        request = RequestFactory().get('/accounts/academic/')
        request.session = client.session
        request.user = get_user(request)
        return identity_for_verified_student(principal_for_request(request))

    def seed(self):
        self.login(self.client_a)
        self.login(self.client_b, 'bravo')
        self.identity_a = self.identity(self.client_a)
        self.identity_b = self.identity(self.client_b)
        self.sem_a = semesters.create(self.identity_a, label='Synthetic A semester')
        self.sem_b = semesters.create(self.identity_b, label='Synthetic B semester')
        self.course_a = courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='ONE',
                                       name='Synthetic A course', credit_units=3, actual_grade='B')
        self.course_b = courses.create(self.identity_b, semester_id=self.sem_b.pk, original_code='ONE',
                                       name='Synthetic B course', credit_units=3, actual_grade='A')
        self.task_a = assignments.create(self.identity_a, course_id=self.course_a.pk,
                                         title='Synthetic A task', due_date=date(2026, 11, 11))
        self.task_b = assignments.create(self.identity_b, course_id=self.course_b.pk,
                                         title='Synthetic B task', due_date=date(2026, 11, 11))
