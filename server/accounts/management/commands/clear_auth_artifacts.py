from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from accounts.devices import cleanup_expired
from accounts.models import AccountToken, AuthThrottle


class Command(BaseCommand):
    help = ('Remove expired throttle buckets, sessions, email tokens expired more than seven days ago, '
            'and expired trusted-device records and login-limit buckets (batched).')

    def handle(self, *args, **options):
        now = timezone.now()
        AuthThrottle.objects.using('auth').filter(expires_at__lte=now).delete()
        AccountToken.objects.using('auth').filter(expires_at__lt=now - timedelta(days=7)).delete()
        SessionStore.clear_expired()
        cleanup_expired(now=now)
        self.stdout.write('Expired authentication artifacts removed; no private records printed.')
