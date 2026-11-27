"""Restricted localhost HTTP website; never a public deployment profile."""
from .auth_development import *  # noqa: F403
from .web_common import configure
configure(globals())
UCC_LOCAL_STATIC = True
