"""Pure B1c classification over B1b's single bounded exception walk."""
from dataclasses import dataclass
import re

import psycopg

from .exception_chain import walk
from .logging import FailureCategory

_CODE = re.compile(r'[0-9A-Z]{5}')
_OUTAGES = frozenset(('57P01', '57P02', '57P03', '57014', '55P03',
                      '40001', '40P01', '25P03'))
_CONFIGURATIONS = frozenset(('42501', '3D000', '57P04'))


@dataclass(frozen=True)
class Classification:
    category: FailureCategory
    origin: str
    sqlstate: str | None
    truncated: bool


def driver_sqlstate(node):
    # Only reached psycopg nodes are read. Unknown server codes live on instances.
    try:
        code = node.sqlstate
    except Exception:
        return None
    return code if type(code) is str and _CODE.fullmatch(code) else None


def classify_database_failure(exc):
    chain = walk(exc)  # Unexpected walker/classifier errors belong to the adapter.
    if not chain.nodes:
        return Classification(FailureCategory.NOT_DATABASE, 'not_database', None, chain.truncated)
    drivers = tuple(node for node in chain.nodes if isinstance(node, psycopg.Error))
    for node in drivers:
        code = driver_sqlstate(node)
        if code is None:
            continue
        if code[:2] in ('08', '53') or code in _OUTAGES:
            category = FailureCategory.OUTAGE
        elif code[:2] == '28' or code in _CONFIGURATIONS:
            category = FailureCategory.CONFIGURATION
        else:
            category = FailureCategory.DEFECT
        return Classification(category, 'database', code, chain.truncated)
    if drivers:
        category = (FailureCategory.CONNECTION_UNAVAILABLE
                    if isinstance(drivers[0], (psycopg.OperationalError, psycopg.InterfaceError))
                    else FailureCategory.DEFECT)
    else:
        category = FailureCategory.DATABASE_UNPROVEN
    return Classification(category, 'database', None, chain.truncated)
