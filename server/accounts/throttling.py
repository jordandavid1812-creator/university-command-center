"""Shared fixed-window IP limits; REMOTE_ADDR only, never client forwarding headers."""
from datetime import timedelta
import math
from django.conf import settings
from django.db import connections
from django.http import HttpResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac


def rate_limit(request, action):
    limit, seconds = settings.AUTH_RATE_LIMITS[action]
    # Both input length and counter values are bounded. No plaintext IP stored.
    address = str(request.META.get('REMOTE_ADDR', 'unknown'))[:128]
    bucket = salted_hmac('ucc-auth-rate', f'{action}|{address}', algorithm='sha256').hexdigest()
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
