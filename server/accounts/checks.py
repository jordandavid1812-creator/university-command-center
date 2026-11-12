from django.conf import settings
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured
from .dbsafety import validate_db_safety


@register()
def database_safety_check(app_configs=None, **kwargs):
    if getattr(settings, 'UCC_DB_SAFETY_CONFIGURED', False) is not True:
        return []
    try:
        validate_db_safety({name: getattr(settings, name) for name in (
            'DATABASES', 'STUDENT_DB_ALIAS', 'UCC_DB_SAFETY_VALUES')})
    except (ImproperlyConfigured, KeyError, AttributeError, TypeError):
        return [Error('Protected database timeout configuration is invalid.', id='accounts.E101')]
    return []
