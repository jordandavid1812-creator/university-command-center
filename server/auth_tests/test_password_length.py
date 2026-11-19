"""Owner's choice: passwords need at least 8 characters (was 12). Synthetic data only."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse
from accounts.models import Student
from .base import AuthenticationCase


class PasswordLengthTests(AuthenticationCase):
    def register(self, password):
        return self.client.post(reverse('accounts:register'), {
            'username': 'new-student', 'email': 'new@example.invalid', 'password1': password, 'password2': password})

    def created(self):
        return Student.objects.using('default').filter(username='new-student').exists()

    def test_seven_characters_are_refused(self):
        response = self.register('Kx7#pQ2')
        self.assertContains(response, 'at least 8 characters')
        self.assertFalse(self.created())

    def test_eight_characters_are_accepted(self):
        self.register('Kx7#pQ2m')
        self.assertTrue(self.created())

    def test_other_password_rules_still_apply(self):
        for weak in ('password', '12345678', 'new-student1'):
            with self.subTest(password=weak), self.assertRaises(ValidationError):
                validate_password(weak, Student(username='new-student', email='new@example.invalid'))
