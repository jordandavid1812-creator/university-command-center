"""Student profiles: forced row-level security, like the other student-owned tables."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0009_student_profile")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_studentprofile ENABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_studentprofile FORCE ROW LEVEL SECURITY;
                CREATE POLICY student_owner ON academics_studentprofile
                FOR ALL TO PUBLIC
                USING (owner_id = (SELECT ucc_security.current_student()))
                WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
            """,
            reverse_sql="""
                DROP POLICY student_owner ON academics_studentprofile;
                ALTER TABLE academics_studentprofile NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE academics_studentprofile DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
