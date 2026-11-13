"""Secure cookie baseline for future review; not approval to deploy."""
from .runtime import *  # noqa: F403
from .auth_common import configure
configure(globals())
# Production deployment remains disabled in config.settings.production.

UCC_SECURE_PROFILE = True
