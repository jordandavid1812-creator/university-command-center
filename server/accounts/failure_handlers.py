"""Django error adapters; preserved handlers are called only on preserved paths."""
import sys
from django.views import defaults
from .failure_classification import classify_database_failure
from .failure_response import failure_response
from .logging import FailureCategory


def _bad_request(request, exception, original):
    try:
        result = classify_database_failure(exception)
    except Exception:
        return failure_response(FailureCategory.DEFECT)
    if result.category in (FailureCategory.NOT_DATABASE, FailureCategory.DATABASE_UNPROVEN):
        return original(request, exception)
    return failure_response(result.category)


def _server_error(request, original):
    exception = sys.exc_info()[1]
    if exception is None:
        return failure_response(FailureCategory.DEFECT)
    try:
        result = classify_database_failure(exception)
    except Exception:
        return failure_response(FailureCategory.DEFECT)
    if result.category is FailureCategory.NOT_DATABASE:
        return original(request)
    return failure_response(result.category)


def auth_bad_request(request, exception):
    return _bad_request(request, exception, defaults.bad_request)


def auth_server_error(request):
    return _server_error(request, defaults.server_error)


def web_bad_request(request, exception):
    from student_web.views import bad_request
    return _bad_request(request, exception, bad_request)


def web_server_error(request):
    from student_web.views import server_error
    return _server_error(request, server_error)
