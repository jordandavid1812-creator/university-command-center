"""Constant, template/database-independent B1c responses; no outcome claims."""
import re
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from .logging import FailureCategory

_BODIES = {
    FailureCategory.OUTAGE: 'The service is temporarily unavailable.\n',
    FailureCategory.CONNECTION_UNAVAILABLE: 'The service is temporarily unavailable.\n',
    FailureCategory.CONFIGURATION: 'The service is not configured safely.\n',
}
_FALLBACK = 'A service error occurred.\n'


def validate_retry_after(value):
    if type(value) is str and 1 <= len(value) <= 3 and re.fullmatch(r'[0-9]+', value):
        value = int(value)
    if type(value) is not int or not 1 <= value <= 300:
        raise ImproperlyConfigured('B1c Retry-After must be an integer from 1 to 300.')
    return value


def _plain_response(body, status, category):
    response = HttpResponse(body, status=status, content_type='text/plain; charset=utf-8')
    response['Cache-Control'] = 'no-store'
    if category is FailureCategory.OUTAGE:
        try:
            retry_after = validate_retry_after(settings.UCC_FAILURE_RETRY_AFTER)
        except Exception:
            # Startup still rejects invalid configuration. If settings fail/change
            # at runtime, omit this optional header rather than lose the safe503.
            # Do not substitute an operational value or catch process controls.
            pass
        else:
            response['Retry-After'] = str(retry_after)
    return response


def _build(category, status):
    return _plain_response(_BODIES.get(category, _FALLBACK), status, category)


def failure_response(category):
    status = 503 if category in _BODIES else 500
    try:
        return _build(category, status)
    except Exception:
        # Preserve status AND all privacy/cache/header contracts in the fallback.
        return _plain_response(_FALLBACK, status, category)
