"""Restricted local service process. PGUSER must be the runtime login role."""
from .base import *  # noqa: F403

UCC_CONTEXT_SIGNING_KEY = required("UCC_CONTEXT_SIGNING_KEY")
STUDENT_DB_ALIAS = "default"
