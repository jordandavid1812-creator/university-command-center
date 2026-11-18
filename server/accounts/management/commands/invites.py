"""Create, list and cancel sign-up invite codes (launch step 3). Owner only, migrator login.

On the server:
    docker compose -f deploy/compose.yml run --rm migrate python manage.py invites create --count 3 --note "Class rep"
    docker compose -f deploy/compose.yml run --rm migrate python manage.py invites list
    docker compose -f deploy/compose.yml run --rm migrate python manage.py invites cancel 4

Codes are shown once, when created; only their digests are stored. Share each code privately
with one person.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS
from django.utils import timezone
from accounts import invites
from accounts.models import InviteCode


def bounded(low, high):
    def parse(text):
        value = int(text)
        if not low <= value <= high:
            raise ValueError
        return value
    parse.__name__ = f'number from {low} to {high}'
    return parse


class Command(BaseCommand):
    help = 'Create, list or cancel one-use sign-up invite codes.'
    # Always the owner (migrator) connection: the auth role may never create or cancel codes.
    database = DEFAULT_DB_ALIAS

    def add_arguments(self, parser):
        actions = parser.add_subparsers(dest='action', required=True)
        create = actions.add_parser('create', help='Create new codes (shown once).')
        create.add_argument('--count', type=bounded(1, 50), default=1, help='How many codes (1-50, default 1).')
        create.add_argument('--days', type=bounded(1, 60), default=14, help='Days until they expire (1-60, default 14).')
        create.add_argument('--note', default='', help='Optional short note for you, e.g. "Class rep" (max 60).')
        actions.add_parser('list', help='List codes and whether they are used (codes are never shown).')
        cancel = actions.add_parser('cancel', help='Cancel an unused code by its number from the list.')
        cancel.add_argument('number', type=bounded(1, 2**62))

    def handle(self, *args, **options):
        action = options['action']
        if action == 'create':
            note = options['note'].strip()
            if len(note) > 60 or not note.isprintable():
                raise CommandError('The note must be at most 60 printable characters.')
            codes = invites.create(options['count'], options['days'], note, using=self.database)
            self.stdout.write(f'{len(codes)} invite code(s), valid for {options["days"]} days. They are shown only now:')
            for code in codes:
                self.stdout.write(f'  {code}')
            self.stdout.write('Give each code privately to one person. Each works once.')
        elif action == 'list':
            now = timezone.now()
            rows = InviteCode.objects.using(self.database).order_by('pk')
            if not rows:
                self.stdout.write('No invite codes yet.')
            for row in rows:
                state = ('used ' + f'{row.used_at:%Y-%m-%d}' if row.used_at
                         else 'expired' if row.expires_at <= now else f'unused until {row.expires_at:%Y-%m-%d}')
                self.stdout.write(f'{row.pk:>4}  {state:<22}  {row.note}')
        else:
            changed = InviteCode.objects.using(self.database).filter(pk=options['number'], used_at__isnull=True,
                                                expires_at__gt=timezone.now()).update(expires_at=timezone.now())
            if not changed:
                raise CommandError('No unused, unexpired code has that number. Nothing changed.')
            self.stdout.write(f'Invite {options["number"]} cancelled.')
