"""B1a connection options only; no role policy, retry, logging or error routing."""
from copy import deepcopy
import os
import re
from django.core.exceptions import ImproperlyConfigured

DEFAULTS = {
    'connect_seconds': 5, 'lock_ms': 3000, 'auth_statement_ms': 5000,
    'runtime_statement_ms': 10000, 'idle_ms': 15000,
}
ENVIRON = {
    'connect_seconds': 'UCC_DB_CONNECT_TIMEOUT_SECONDS',
    'lock_ms': 'UCC_DB_LOCK_TIMEOUT_MS',
    'auth_statement_ms': 'UCC_AUTH_STATEMENT_TIMEOUT_MS',
    'runtime_statement_ms': 'UCC_RUNTIME_STATEMENT_TIMEOUT_MS',
    'idle_ms': 'UCC_DB_IDLE_TIMEOUT_MS',
}


def integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,12}', value):
        return int(value)
    raise ImproperlyConfigured('B1a timers require bounded unsigned integers.')


def validate_values(values):
    if not isinstance(values, dict) or set(values) != set(DEFAULTS):
        raise ImproperlyConfigured('B1a timer configuration is incomplete.')
    result = {key: integer(value) for key, value in values.items()}
    if not (2 <= result['connect_seconds'] <= 30
            and 5000 <= result['idle_ms'] <= 300000
            and 1000 <= result['lock_ms'] < result['auth_statement_ms'] <= 60000
            and result['lock_ms'] < result['runtime_statement_ms'] <= 60000):
        raise ImproperlyConfigured('B1a timers are outside the approved candidate bounds.')
    return result


def options_for(values, statement_key):
    return (f"-c lock_timeout={values['lock_ms']} "
            f"-c statement_timeout={values[statement_key]} "
            f"-c idle_in_transaction_session_timeout={values['idle_ms']}")


def expected(namespace):
    if 'PGOPTIONS' in os.environ:
        raise ImproperlyConfigured('PGOPTIONS is not permitted in protected auth profiles.')
    values = validate_values(namespace['UCC_DB_SAFETY_VALUES'])
    academic = namespace['STUDENT_DB_ALIAS']
    if academic == 'auth' or academic not in namespace['DATABASES']:
        raise ImproperlyConfigured('B1a requires distinct academic and authentication aliases.')
    return values, {'auth': options_for(values, 'auth_statement_ms'),
                    academic: options_for(values, 'runtime_statement_ms')}


def validate_db_safety(namespace):
    """Read-only settings validation; deliberately opens no connection."""
    values, aliases = expected(namespace)
    for alias, options in aliases.items():
        db = namespace['DATABASES'][alias]
        actual = db.get('OPTIONS', {})
        if (db.get('ENGINE') != 'django.db.backends.postgresql'
                or actual.get('options') != options
                or type(actual.get('connect_timeout')) is not int
                or actual.get('connect_timeout') != values['connect_seconds']):
            raise ImproperlyConfigured('B1a application connection options are missing or inconsistent.')


def apply_db_safety(namespace):
    """Opt in protected profiles only. Never mutate an inherited/shared DB dict."""
    raw = namespace.get('UCC_DB_SAFETY_VALUES')
    if raw is None:
        raw = {key: os.environ.get(ENVIRON[key], value) for key, value in DEFAULTS.items()}
    # Validate everything before changing the namespace or exposing the opt-in flag.
    candidate = dict(namespace, UCC_DB_SAFETY_VALUES=validate_values(raw))
    values, aliases = expected(candidate)
    databases = deepcopy(namespace['DATABASES'])
    for alias, options in aliases.items():
        db = databases[alias]
        current = db.setdefault('OPTIONS', {})
        if not isinstance(current, dict):
            raise ImproperlyConfigured('B1a requires a connection options mapping.')
        existing = current.get('options', '')
        if not isinstance(existing, str) or existing not in ('', options):
            raise ImproperlyConfigured('B1a owns application options; conflicting options are not permitted.')
        if 'connect_timeout' in current and integer(current['connect_timeout']) != values['connect_seconds']:
            raise ImproperlyConfigured('B1a connect_timeout conflicts with the selected configuration.')
        current.update(options=options, connect_timeout=values['connect_seconds'])
    candidate.update(DATABASES=databases)
    validate_db_safety(candidate)
    namespace.update(DATABASES=databases, UCC_DB_SAFETY_VALUES=values,
                     UCC_DB_SAFETY_CONFIGURED=True)
