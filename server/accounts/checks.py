from django.conf import settings
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured
from .dbsafety import validate_db_safety


@register()
def database_safety_check(app_configs=None, **kwargs):
    if getattr(settings, 'UCC_DB_SAFETY_CONFIGURED', False) is not True:
        return []
    try:
        validate_db_safety({name: getattr(settings, name) for name in (
            'DATABASES', 'STUDENT_DB_ALIAS', 'UCC_DB_SAFETY_VALUES')})
    except (ImproperlyConfigured, KeyError, AttributeError, TypeError):
        return [Error('Protected database timeout configuration is invalid.', id='accounts.E101')]
    return []


@register()
def logging_admins_check(app_configs=None, **kwargs):
    if getattr(settings, 'UCC_LOG_PRIVACY', None) == 'enforce' and settings.ADMINS:
        return [Error('Protected logging requires empty ADMINS.', id='accounts.E102')]
    return []


@register()
def logging_graph_check(app_configs=None, **kwargs):
    if getattr(settings, 'UCC_LOG_PRIVACY', None) == 'enforce':
        from .log_privacy import valid_graph
        if not valid_graph():
            return [Error('Protected logging configuration is unsafe.', id='accounts.E103')]
    return []


@register()
def secure_debug_check(app_configs=None, **kwargs):
    if (getattr(settings, 'UCC_SECURE_PROFILE', False) is True
            and (settings.DEBUG or settings.DEBUG_PROPAGATE_EXCEPTIONS)):
        return [Error('Secure profiles require disabled debug flags.', id='accounts.E104')]
    return []


@register()
def secure_email_check(app_configs=None, **kwargs):
    if getattr(settings, 'UCC_SECURE_PROFILE', False) is not True:
        return []
    from django.utils.module_loading import import_string
    from .log_privacy import APPROVED_EMAIL_BACKENDS
    try:
        backend = import_string(settings.EMAIL_BACKEND)
        approved = (isinstance(backend, type) and len(APPROVED_EMAIL_BACKENDS) <= 1
                    and any(backend is cls for cls in APPROVED_EMAIL_BACKENDS))
    except Exception:
        approved = False
    if not approved:
        return [Error('Secure email backend is not approved.', id='accounts.E105')]
    return []


@register()
def public_invite_check(app_configs=None, **kwargs):
    if getattr(settings, 'UCC_PUBLIC_SITE', False) is True and getattr(settings, 'UCC_REQUIRE_INVITE', False) is not True:
        return [Error('The public site requires invite-only sign-up (UCC_REQUIRE_INVITE).', id='accounts.E106')]
    return []
