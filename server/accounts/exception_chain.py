"""Pure bounded inspection for logging; no classification, I/O or exception text."""
from dataclasses import dataclass
import re

import psycopg
from django.contrib.sessions.backends.base import CreateError, UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.db import utils

WRAPPERS = (SessionInterrupted, CreateError, UpdateError, utils.Error, psycopg.Error)
LIMIT = 16
_CODE = re.compile(r'[0-9A-Z]{5}')
DRIVER_CLASSES = frozenset(
    value for value in vars(psycopg.errors).values()
    if isinstance(value, type) and issubclass(value, psycopg.Error)
)
_LABELS = {cls: label for cls, label in (
    (SessionInterrupted, 'django.SessionInterrupted'), (CreateError, 'django.CreateError'),
    (UpdateError, 'django.UpdateError'),
    *((getattr(utils, name), 'django.' + name) for name in (
        'Error', 'InterfaceError', 'DatabaseError', 'OperationalError', 'ProgrammingError',
        'IntegrityError', 'DataError', 'InternalError', 'NotSupportedError')),
    *((getattr(psycopg, name), 'psycopg.' + name) for name in (
        'Error', 'InterfaceError', 'DatabaseError', 'OperationalError', 'ProgrammingError',
        'IntegrityError', 'DataError', 'InternalError', 'NotSupportedError')),
)}


@dataclass(frozen=True)
class Chain:
    nodes: tuple
    truncated: bool


def walk(exc):
    nodes, seen = [], set()
    while isinstance(exc, BaseException):
        if id(exc) in seen or len(nodes) == LIMIT:
            return Chain(tuple(nodes), True)
        seen.add(id(exc))
        if not isinstance(exc, WRAPPERS):
            break
        nodes.append(exc)
        cause = exc.__cause__
        exc = cause if cause is not None else (None if exc.__suppress_context__ else exc.__context__)
    return Chain(tuple(nodes), False)


def known_sqlstate(code):
    if type(code) is not str or not _CODE.fullmatch(code):
        return False
    try:
        psycopg.errors.lookup(code)
    except (KeyError, LookupError):
        return False
    return True


def class_sqlstate(exc):
    cls = type(exc)
    if cls not in DRIVER_CLASSES:
        return None
    try:
        code = cls.sqlstate
        if known_sqlstate(code) and psycopg.errors.lookup(code) is cls:
            return code
    except Exception:
        pass
    return None  # Deliberately never inspect instance.sqlstate/diag/args.


def exception_label(exc):
    cls = type(exc)
    if cls in _LABELS:
        return _LABELS[cls]
    if cls in DRIVER_CLASSES:
        return 'psycopg.errors[' + (class_sqlstate(exc) or 'XXXXX') + ']'
    return 'OTHER'


def labels(exc):
    if not isinstance(exc, BaseException):
        return '-'
    chain = walk(exc)
    # Unknown outer exceptions are labeled even when opaque and not traversed.
    result = [exception_label(node) for node in chain.nodes] or [exception_label(exc)]
    if chain.truncated:
        result.append('TRUNCATED')
    return ','.join(result)
