"""Fixed-label sink. No record message, formatter, traceback or request retention."""
from dataclasses import dataclass
from enum import Enum
import logging
import sys
import threading

from django.http import HttpRequest
from .exception_chain import known_sqlstate, labels


class EventKind(Enum):
    FAILURE = 'FAILURE'


class FailureCategory(Enum):
    UNCLASSIFIED = 'UNCLASSIFIED'
    OUTAGE = 'OUTAGE'
    CONNECTION_UNAVAILABLE = 'CONNECTION_UNAVAILABLE'
    CONFIGURATION = 'CONFIGURATION'
    DEFECT = 'DEFECT'
    DATABASE_UNPROVEN = 'DATABASE_UNPROVEN'
    NOT_DATABASE = 'NOT_DATABASE'


_CATEGORY_LABELS = {
    FailureCategory.UNCLASSIFIED: 'UNCLASSIFIED',
    FailureCategory.OUTAGE: 'OUTAGE',
    FailureCategory.CONNECTION_UNAVAILABLE: 'CONNECTION_UNAVAILABLE',
    FailureCategory.CONFIGURATION: 'CONFIGURATION',
    FailureCategory.DEFECT: 'DEFECT',
    FailureCategory.DATABASE_UNPROVEN: 'DATABASE_UNPROVEN',
    FailureCategory.NOT_DATABASE: 'NOT_DATABASE',
}


@dataclass(frozen=True)
class FailureEvent:
    event: EventKind
    category: FailureCategory
    sqlstate: str | None = None


LEVELS = {10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR', 50: 'CRITICAL'}
METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE', 'CONNECT')
ROUTES = (
    'student_web:robots', 'student_web:sitemap', 'student_web:favicon', 'student_web:cookie-notice-ok',
    'accounts:register', 'accounts:privacy', 'accounts:terms', 'accounts:login', 'accounts:logout', 'accounts:resend',
    'accounts:verify', 'accounts:verify-code', 'accounts:reset', 'accounts:reset-confirm', 'accounts:password-change',
    'accounts:academic', 'accounts:course', 'accounts:delete-assignment',
    'student_web:dashboard', 'student_web:semester-list', 'student_web:course-list',
    'student_web:assignment-list', 'student_web:overview', 'student_web:predictor',
    'student_web:planner', 'student_web:settings', 'student_web:full-name', 'student_web:account-delete', 'student_web:email-change',
    'student_web:email-change-confirm', 'student_web:grading-scale', 'student_web:assignment-status',
    'student_web:semester-create', 'student_web:semester-edit', 'student_web:semester-delete',
    'student_web:course-create', 'student_web:course-edit', 'student_web:course-delete',
    'student_web:assignment-create', 'student_web:assignment-edit', 'student_web:assignment-delete',
    'student_web:material-upload', 'student_web:material-list', 'student_web:material-delete',
    'student_web:material-download', 'student_web:display-preference',
    'student_web:profile-edit', 'student_web:data-export',
    'student_web:mistakes-save', 'student_web:mistakes', 'student_web:mistakes-practice', 'student_web:mistakes-clear',
    'student_web:mistake-remove',
    'student_web:planner-projection', 'student_web:planner-suggest', 'student_web:quick-start', 'student_web:standing-print', 'student_web:class-bands',
    'student_web:class-bands-reset', 'student_web:material-search', 'student_web:timetable',
    'student_web:session-create', 'student_web:session-edit', 'student_web:session-delete',
    'student_web:study-plans', 'student_web:study-plan-create', 'student_web:study-plan', 'student_web:study-plan-replan',
    'student_web:study-topic-add', 'student_web:plan-delete', 'student_web:study-topic-done', 'student_web:study-topic-delete',
    'student_web:ai-tools', 'student_web:ai-confirm', 'student_web:ai-send', 'student_web:ai-request',
    'student_web:ai-result', 'student_web:ai-result-download', 'student_web:ai-result-delete',
)
_EXACT_LOGGERS = ('django.request', 'django.security.csrf', 'django.security.SuspiciousSession',
                  'django.server', 'accounts.failures', 'py.warnings')
_PREFIXES = (('django.security', 'django.security'), ('django.db.backends', 'django.db'),
             ('django', 'django'), ('psycopg', 'psycopg'), ('accounts', 'accounts'),
             ('academics', 'academics'), ('student_web', 'student_web'))
_LOCAL = threading.local()
FALLBACK = 'ucc-log record suppressed (sanitizer error)\n'


def member(value, choices, other):
    if type(value) is str:
        for constant in choices:
            if value == constant:
                return constant
    return other


def logger_label(value):
    exact = member(value, _EXACT_LOGGERS, None)
    if exact is not None:
        return exact
    if type(value) is str:
        for prefix, constant in _PREFIXES:
            if value == prefix or value.startswith(prefix + '.'):
                return constant
    return 'other'


def safe_record(record):
    raw = record.__dict__
    level = raw.get('levelno')
    status = raw.get('status_code')
    fields = {
        'logger': logger_label(raw.get('name')),
        'level': LEVELS.get(level, 'OTHER') if type(level) is int else 'OTHER',
        'status': str(status) if type(status) is int and 100 <= status <= 599 else '-',
        'method': 'OTHER', 'route': 'other', 'event': '-', 'category': '-', 'sqlstate': '-',
        'exc': '-',
    }
    request = raw.get('request')
    if isinstance(request, HttpRequest):
        fields['method'] = member(request.method, METHODS, 'OTHER')
        match = request.resolver_match
        if match is not None:
            fields['route'] = member(match.view_name, ROUTES, 'other')
    info = raw.get('exc_info')
    if type(info) is tuple and len(info) == 3 and isinstance(info[1], BaseException):
        fields['exc'] = labels(info[1])
    event = raw.get('ucc_event')
    if (type(event) is FailureEvent and type(event.event) is EventKind
            and type(event.category) is FailureCategory):
        fields['event'] = EventKind.FAILURE.value
        fields['category'] = _CATEGORY_LABELS[event.category]
        fields['sqlstate'] = '-' if event.sqlstate is None else (
            event.sqlstate if known_sqlstate(event.sqlstate) else 'XXXXX')
    safe = logging.LogRecord(fields['logger'], 0, '', 0, 'ucc-log', None, None)
    safe.exc_text = safe.stack_info = None
    safe.fields = fields
    return safe


def render(record):
    return 'ucc-log ' + ' '.join(key + '=' + value for key, value in record.fields.items()) + '\n'


def emit_safe(record, stream=None):
    if getattr(_LOCAL, 'active', False):
        return
    _LOCAL.active = True
    try:
        try:
            line = render(safe_record(record))
        except Exception:
            line = FALLBACK
        try:
            # One call only, even after partial output. No flush/retry/default handleError.
            (sys.stderr if stream is None else stream).write(line)
        except Exception:
            return
    finally:
        _LOCAL.active = False


class SanitizingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET, stream=None):
        super().__init__(level)
        self.stream = stream

    def emit(self, record):
        emit_safe(record, self.stream)

    def handleError(self, record):
        return  # Never call the raw stdlib fallback, even if called externally.


def _hook_emit(exc):
    record = logging.LogRecord('accounts', logging.ERROR, '', 0, 'uncaught', None,
                               (type(exc), exc, None))
    emit_safe(record)


def process_exception_hook(exc_type, exc, traceback):
    try:
        _hook_emit(exc)
    except BaseException:
        return


def thread_exception_hook(args):
    try:
        if args.exc_type is not SystemExit:
            _hook_emit(args.exc_value)
    except BaseException:
        return


def unraisable_exception_hook(args):
    try:
        _hook_emit(args.exc_value)
    except BaseException:
        return
