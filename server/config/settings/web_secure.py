"""Future secure-cookie baseline, still not production deployment approval."""
from .auth_secure import *  # noqa: F403
from .web_common import configure
configure(globals())
