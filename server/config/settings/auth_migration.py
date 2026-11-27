"""Offline migration/provisioning ONLY. Never use for web requests."""
from .base import *  # noqa: F403
INSTALLED_APPS = INSTALLED_APPS + ["django.contrib.sessions"]
