from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from accounts.models import AccountToken, AuthThrottle


class Command(BaseCommand):
    help = 'Remove expired throttle buckets, sessions and email tokens expired more than seven days ago.'

    def handle(self, *args, **options):
        now = timezone.now()
        AuthThrottle.objects.using('auth').filter(expires_at__lte=now).delete()
        AccountToken.objects.using('auth').filter(expires_at__lt=now - timedelta(days=7)).delete()
        SessionStore.clear_expired()
        self.stdout.write('Expired authentication artifacts removed; no private records printed.')
