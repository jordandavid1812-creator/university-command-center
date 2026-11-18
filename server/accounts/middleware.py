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


# The browser rule for every page: scripts, styles, pictures and form posts may come only from
# this site; plugins, <base> changes and framing by other sites are refused. Style *attributes*
# stay allowed because the class-band bar places its parts with them (pages must work without
# JavaScript), but <style> blocks and style sheets must still come from this site.
CONTENT_SECURITY_POLICY = '; '.join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "style-src-elem 'self'",
    "img-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))


class ContentSecurityPolicyMiddleware:
    """Adds CONTENT_SECURITY_POLICY to responses that do not already set their own.

    Downloads and the data export keep their stricter "default-src 'none'; sandbox" rule.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = CONTENT_SECURITY_POLICY
        return response
