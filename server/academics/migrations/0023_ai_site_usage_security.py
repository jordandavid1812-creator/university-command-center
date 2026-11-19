"""Launch step E: the site-wide AI counter. Forced row-level security: only a transaction with a
valid signed student context can read or add to it. It holds no student data."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0022_ai_site_usage")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_aisiteusage ENABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_aisiteusage FORCE ROW LEVEL SECURITY;
                CREATE POLICY signed_student ON academics_aisiteusage
                FOR ALL TO PUBLIC
                USING ((SELECT ucc_security.current_student()) IS NOT NULL)
                WITH CHECK ((SELECT ucc_security.current_student()) IS NOT NULL);
            """,
            reverse_sql="""
                DROP POLICY signed_student ON academics_aisiteusage;
                ALTER TABLE academics_aisiteusage NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE academics_aisiteusage DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
