"""Shared fixed-window limits keyed by a normalized source address.

REMOTE_ADDR is trusted by default. X-Forwarded-For is read ONLY when the socket
peer is inside an explicitly configured UCC_TRUSTED_PROXIES network (empty in
every operational profile until a deployment topology is reviewed).
"""
from datetime import timedelta
import ipaddress
import math
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.http import HttpResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac

MAX_FORWARDED_HOPS = 20


def _parse_address(value):
    """One IP address, or None. IPv4-mapped IPv6 becomes IPv4; zone IDs are dropped."""
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    try:
        address = ipaddress.ip_address(value.strip().split('%', 1)[0])
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _trusted_proxies():
    configured = getattr(settings, 'UCC_TRUSTED_PROXIES', ())
    if isinstance(configured, str) or not isinstance(configured, (list, tuple)):
        raise ImproperlyConfigured('UCC_TRUSTED_PROXIES must be a list of proxy networks.')
    networks = []
    for value in configured:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except (TypeError, ValueError):
            raise ImproperlyConfigured('UCC_TRUSTED_PROXIES contains an invalid network.') from None
        if network.prefixlen == 0:
            raise ImproperlyConfigured('UCC_TRUSTED_PROXIES must not trust every client address.')
        networks.append(network)
    return networks


def _trusted(address, networks):
    return any(address.version == network.version and address in network for network in networks)


def client_address(request):
    """Normalized throttle source: IPv4 address, IPv6 /64 network, or 'unknown'."""
    address = _parse_address(request.META.get('REMOTE_ADDR'))
    if address is None:
        return 'unknown'
    networks = _trusted_proxies()
    if networks and _trusted(address, networks):
        # Right-most entry not added by a trusted proxy is the client. Anything to its
        # left was supplied by the client and is ignored. Malformed headers keep the
        # proxy address (one shared, conservative bucket) instead of guessing.
        hops = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[-MAX_FORWARDED_HOPS:]
        for item in reversed(hops):
            hop = _parse_address(item)
            if hop is None:
                break
            if not _trusted(hop, networks):
                address = hop
                break
    if address.version == 6:
        return str(ipaddress.ip_network(f'{address}/64', strict=False))
    return str(address)


def rate_limit(request, action):
    limit, seconds = settings.AUTH_RATE_LIMITS[action]
    # Both input length and counter values are bounded. No plaintext IP stored.
    bucket = salted_hmac('ucc-auth-rate', f'{action}|{client_address(request)}', algorithm='sha256').hexdigest()
    now = timezone.now()
    end = now + timedelta(seconds=seconds)
    with connections['auth'].cursor() as cursor:
        cursor.execute('''
            INSERT INTO accounts_auththrottle (bucket, attempts, expires_at) VALUES (%s, 1, %s)
            ON CONFLICT (bucket) DO UPDATE SET
              attempts = CASE WHEN accounts_auththrottle.expires_at <= %s THEN 1
                         ELSE LEAST(accounts_auththrottle.attempts + 1, %s) END,
              expires_at = CASE WHEN accounts_auththrottle.expires_at <= %s THEN %s
                           ELSE accounts_auththrottle.expires_at END
            RETURNING attempts, expires_at
        ''', [bucket, end, now, limit + 1, now, end])
        attempts, expires = cursor.fetchone()
    if attempts > limit:
        response = HttpResponse('Too many attempts. Please try again later.', status=429)
        response['Retry-After'] = str(max(1, math.ceil((expires - now).total_seconds())))
        return response
    return None
