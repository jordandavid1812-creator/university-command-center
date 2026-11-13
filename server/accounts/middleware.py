from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DatabaseError
from django.http import HttpResponse
from academics.ownership import database_alias, require_runtime_role
from .boundary import require_auth_role


class DatabaseRoleBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            if getattr(settings, 'ALLOW_INTERNAL_TEST_PRINCIPALS', False):
                raise ImproperlyConfigured('Fixture-only capabilities must never serve authentication requests.')
            require_runtime_role(connections[database_alias()])
            require_auth_role()
        except (ImproperlyConfigured, DatabaseError):
            return HttpResponse('The service is not configured safely.', status=503)
        return self.get_response(request)


class AuthFailureMiddleware:
    """View exceptions only; response-phase failures use both URL-root handlers."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        from .failure_classification import classify_database_failure
        from .failure_response import failure_response
        from .logging import FailureCategory, FailureEvent, EventKind
        import logging
        try:
            result = classify_database_failure(exception)
        except Exception:
            category, code = FailureCategory.DEFECT, None
        else:
            if result.category not in (FailureCategory.OUTAGE,
                                      FailureCategory.CONNECTION_UNAVAILABLE,
                                      FailureCategory.CONFIGURATION):
                return None
            category, code = result.category, result.sqlstate
        logging.getLogger('accounts.failures').error(
            'failure', extra={'request': request,
                              'ucc_event': FailureEvent(EventKind.FAILURE, category, code)})
        return failure_response(category)
