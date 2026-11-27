"""Protected-process setup and snapshot validation; not runtime immutability."""
import logging
import sys
import threading
from django.core.exceptions import ImproperlyConfigured
from .logging import (SanitizingHandler, process_exception_hook, thread_exception_hook,
                      unraisable_exception_hook)

# Exactly one reviewed backend is approved (launch step C, accounts.email_backend): fixed
# providers, STARTTLS with verified certificates, one recipient per message. Changing this
# needs a separate reviewed change. Local and test profiles keep console/locmem and E105.
from .email_backend import ReviewedSMTPBackend  # noqa: E402

APPROVED_EMAIL_BACKENDS = (ReviewedSMTPBackend,)
_PREFIXES = ('django', 'psycopg', 'accounts', 'academics', 'student_web')


def covered(name):
    return name == 'py.warnings' or any(name == p or name.startswith(p + '.') for p in _PREFIXES)


def configure(namespace):
    namespace['UCC_LOG_PRIVACY'] = 'enforce'
    namespace['LOGGING'] = {
        'version': 1, 'disable_existing_loggers': False,
        'handlers': {'safe': {'class': 'accounts.logging.SanitizingHandler'}},
        'root': {'handlers': ['safe'], 'level': 'WARNING'},
        'loggers': {
            'django': {'handlers': [], 'propagate': True, 'level': 'INFO'},
            'django.server': {'handlers': [], 'propagate': True, 'level': 'INFO'},
        },
    }
    # These are installed before django.setup/configure_logging/AppConfig.ready.
    if type(logging.lastResort) is not SanitizingHandler:
        logging.lastResort = SanitizingHandler(logging.WARNING)
    sys.excepthook = process_exception_hook
    threading.excepthook = thread_exception_hook
    sys.unraisablehook = unraisable_exception_hook


def valid_graph():
    if (type(logging.lastResort) is not SanitizingHandler
            or logging.lastResort.filters or logging.lastResort.formatter is not None
            or sys.excepthook is not process_exception_hook
            or threading.excepthook is not thread_exception_hook
            or sys.unraisablehook is not unraisable_exception_hook):
        return False
    root = logging.getLogger()
    if len(root.handlers) != 1 or type(root.handlers[0]) is not SanitizingHandler:
        return False
    loggers = [root] + [obj for name, obj in logging.root.manager.loggerDict.copy().items()
                       if covered(name) and isinstance(obj, logging.Logger)]
    for logger in loggers:
        if logger.filters:
            return False
        for handler in logger.handlers:
            if (type(handler) not in (SanitizingHandler, logging.NullHandler)
                    or handler.filters or handler.formatter is not None):
                return False
    for name in ('django', 'django.server'):
        logger = logging.getLogger(name)
        if logger.handlers or not logger.propagate:
            return False
    return True


def enforce_startup():
    if not valid_graph():
        raise ImproperlyConfigured('Protected logging configuration is unsafe.')
