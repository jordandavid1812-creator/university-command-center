"""Essential-cookie notice (owner's choice): a slim bar until the student presses OK. Works without
JavaScript (a normal form POST). Only remembers that OK was pressed; no tracking."""
from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .context import COOKIE_NOTICE_COOKIE

ONE_YEAR = 365 * 24 * 60 * 60


@never_cache
@require_POST
def cookie_notice_ok(request):
    target = request.POST.get('next', '')
    if not (target.startswith('/') and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
        target = '/'
    response = HttpResponseRedirect(target)
    response.set_cookie(COOKIE_NOTICE_COOKIE, '1', max_age=ONE_YEAR, httponly=True, samesite='Lax',
                        secure=settings.SESSION_COOKIE_SECURE)
    return response
