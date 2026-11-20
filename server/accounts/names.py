"""Self-reported account names; these never establish identity or authentication."""
import unicodedata
from django.core.exceptions import ValidationError

MAX_NAME_LENGTH = 150


def clean_full_name(value):
    if not isinstance(value, str) or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise ValidationError("Use a name without hidden control characters.")
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if len(value) > MAX_NAME_LENGTH:
        raise ValidationError("Use at most 150 characters for your name.")
    return value


def validate_full_name(value):
    if clean_full_name(value) != value:
        raise ValidationError("Use a name without extra surrounding or repeated spaces.")
