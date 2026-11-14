"""Study materials: same-owner course link and forced row-level security."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0005_study_material")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_studymaterial
                ADD CONSTRAINT material_course_same_owner
                FOREIGN KEY (course_id, owner_id)
                REFERENCES academics_course (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;

                ALTER TABLE academics_studymaterial ENABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_studymaterial FORCE ROW LEVEL SECURITY;
                CREATE POLICY student_owner ON academics_studymaterial
                FOR ALL TO PUBLIC
                USING (owner_id = (SELECT ucc_security.current_student()))
                WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
            """,
            reverse_sql="""
                DROP POLICY student_owner ON academics_studymaterial;
                ALTER TABLE academics_studymaterial NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE academics_studymaterial DISABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_studymaterial DROP CONSTRAINT material_course_same_owner;
            """,
        ),
    ]
