from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from .models import Student


class RegistrationForm(forms.Form):
    username = forms.RegexField(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{2,29}\Z", max_length=30,
                               help_text="3–30 ASCII characters; usernames are case-sensitive.")
    email = forms.EmailField(max_length=254)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, strip=False, max_length=128)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, strip=False, max_length=128)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if not email.isascii():
            raise forms.ValidationError("Use an ASCII email address.")
        return email

    def clean(self):
        values = super().clean()
        password = values.get('password1')
        if password and values.get('password2') and password != values['password2']:
            self.add_error('password2', 'Passwords do not match.')
        if password:
            candidate = Student(username=values.get('username', ''), email=values.get('email'))
            try:
                password_validation.validate_password(password, candidate)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return values


class EmailRequestForm(forms.Form):
    email = forms.EmailField(max_length=254)

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if not value.isascii():
            raise forms.ValidationError('Use an ASCII email address.')
        return value


class BoundedAuthenticationForm(AuthenticationForm):
    password = forms.CharField(widget=forms.PasswordInput, strip=False, max_length=128)


class BoundedSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput, strip=False, max_length=128)
    new_password2 = forms.CharField(label="Confirm new password", widget=forms.PasswordInput, strip=False, max_length=128)


class BoundedPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(label="Current password", widget=forms.PasswordInput, strip=False, max_length=128)
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput, strip=False, max_length=128)
    new_password2 = forms.CharField(label="Confirm new password", widget=forms.PasswordInput, strip=False, max_length=128)
