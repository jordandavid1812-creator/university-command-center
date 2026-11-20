"""Owner decision (two-step removal): erase every saved matric number now; a later reviewed
release drops the empty column once old application code is retired.

Row-level security is forced even for the table owner on plain PostgreSQL, so the owner lifts
the forcing only inside this migration's transaction and restores it before commit. Erasure is
one-way: reversing this migration does not bring the old values back."""
from django.db import migrations

ERASE = """
ALTER TABLE academics_studentprofile NO FORCE ROW LEVEL SECURITY;
UPDATE academics_studentprofile SET matric_number = '' WHERE matric_number <> '';
ALTER TABLE academics_studentprofile FORCE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [('academics', '0026_legacy_matric_database_default')]
    operations = [migrations.RunSQL(sql=ERASE, reverse_sql=migrations.RunSQL.noop)]
