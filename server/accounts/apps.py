from django.apps import AppConfig
from django.conf import settings


class AccountsConfig(AppConfig):
    name = 'accounts'
    label = 'accounts'

    def ready(self):
        if getattr(settings, 'UCC_DB_SAFETY_CONFIGURED', False) is True:
            from . import checks  # noqa: F401
        if (getattr(settings, 'UCC_LOG_PRIVACY', None) == 'enforce'
                or getattr(settings, 'UCC_SECURE_PROFILE', False) is True):
            from . import checks  # noqa: F401
        if getattr(settings, 'UCC_LOG_PRIVACY', None) == 'enforce':
            from .log_privacy import enforce_startup
            enforce_startup()
