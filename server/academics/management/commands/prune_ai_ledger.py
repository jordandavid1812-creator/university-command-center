"""Offline maintenance: delete AI ledger rows older than 365 days that have no saved result.

Run only with the migration settings and role, with the website stopped:
    python server/manage.py prune_ai_ledger --settings=config.settings.auth_migration

Forced RLS applies to the table owner too, so with no student context the owner would see no
rows. In ONE transaction this lifts FORCE on the two AI tables, deletes, and restores FORCE;
ALTER TABLE is transactional, so any failure rolls everything back. It prints only a count.
The runtime role still has no DELETE on the ledger.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

TABLES = ("academics_studyairequest", "academics_studyairesult")
RETENTION_DAYS = 365


class Command(BaseCommand):
    help = "Delete AI ledger rows older than 365 days without a saved result (migration role only)."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default", help="Connection alias (the migration connection).")

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
            cursor.execute("""SELECT count(*) FROM pg_class
                              WHERE relname = ANY(%s) AND relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)""",
                           [list(TABLES)])
            if cursor.fetchone()[0] != len(TABLES):
                raise CommandError("Run this with the migration settings and role (the owner of the AI tables).")
            # Django's foreign keys are deferred; check them at once so FORCE can be restored below.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            for table in TABLES:
                cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")  # nosec B608: constant names
            cursor.execute(f"""DELETE FROM academics_studyairequest r
                               WHERE r.created_at < now() - interval '{RETENTION_DAYS} days'
                                 AND NOT EXISTS (SELECT 1 FROM academics_studyairesult s WHERE s.request_id = r.id)""")  # nosec B608
            deleted = cursor.rowcount
            for table in TABLES:
                cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")  # nosec B608
        self.stdout.write(f"Removed {deleted} AI ledger rows older than {RETENTION_DAYS} days.")
