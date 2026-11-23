from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from .models import Student


class FullNameField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.update(max_length=150, required=False, strip=False, label="Full name (optional)",
                      help_text="Your self-reported name, separate from your username. You can edit or clear it in Settings.",
                      widget=forms.TextInput(attrs={"autocomplete": "name"}))
        super().__init__(*args, **kwargs)

    def clean(self, value):
        from .names import clean_full_name
        return super().clean(clean_full_name(value or ""))


class RegistrationForm(forms.Form):
    full_name = FullNameField()
    username = forms.RegexField(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{2,29}\Z", max_length=30,
                               help_text="3–30 ASCII characters; usernames are case-sensitive.")
    email = forms.EmailField(max_length=254)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, strip=False, max_length=128)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, strip=False, max_length=128)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Launch step 3: the public site is invite-only (UCC_REQUIRE_INVITE in web_production).
        if getattr(settings, 'UCC_REQUIRE_INVITE', False):
            self.fields['invite_code'] = forms.CharField(
                label='Invite code', max_length=64,
                help_text='Ask the site owner for one. Each code works once, for one account.',
                widget=forms.TextInput(attrs={'autocomplete': 'off', 'autocapitalize': 'characters',
                                              'spellcheck': 'false'}))

        # Owner's choice: an explicit "I agree" box on the public site (UCC_TERMS_TICK).
        if getattr(settings, 'UCC_TERMS_TICK', False) is True:
            self.fields['agree_terms'] = forms.BooleanField(
                label='I agree to the Terms of use and have read the Privacy notice', label_suffix='',
                error_messages={'required': 'Tick the box to agree to the Terms of use and Privacy notice.'})

    def clean_invite_code(self):
        from .invites import INVALID, normalize
        if normalize(self.cleaned_data['invite_code']) is None:
            raise forms.ValidationError(INVALID)
        return self.cleaned_data['invite_code']

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


class SignupCodeForm(forms.Form):
    """Public site: confirm a new account with the 6-digit emailed code, or ask for a new one."""
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
                             help_text='The email you signed up with.')
    code = forms.CharField(label='6-digit code', max_length=12, required=False,
                           help_text='From the email we just sent. It works for 5 minutes.',
                           widget=forms.TextInput(attrs={'autocomplete': 'one-time-code', 'inputmode': 'numeric',
                                                         'spellcheck': 'false'}))

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if not value.isascii():
            raise forms.ValidationError('Use an ASCII email address.')
        return value


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
