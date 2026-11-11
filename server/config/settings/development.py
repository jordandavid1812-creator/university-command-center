"""Local development only; DEBUG requires explicit opt-in."""
from .base import *  # noqa: F403

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
