from django.core.exceptions import ValidationError
from academic_logic import checked_credits


def validate_credits(value):
    try:
        checked_credits(value)
    except ValueError as error:
        raise ValidationError(str(error)) from error
