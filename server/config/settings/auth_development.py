"""Local HTTP only; application default connection must be restricted runtime."""
from .runtime import *  # noqa: F403
from .auth_common import configure
configure(globals())
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
