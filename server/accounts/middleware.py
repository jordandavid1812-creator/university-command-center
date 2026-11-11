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
