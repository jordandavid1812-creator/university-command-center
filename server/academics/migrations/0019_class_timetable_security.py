"""Timetable classes: same-owner course link and forced row-level security."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0018_class_timetable")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_classsession
                ADD CONSTRAINT classsession_course_same_owner
                FOREIGN KEY (course_id, owner_id)
                REFERENCES academics_course (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;

                ALTER TABLE academics_classsession ENABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_classsession FORCE ROW LEVEL SECURITY;
                CREATE POLICY student_owner ON academics_classsession
                FOR ALL TO PUBLIC
                USING (owner_id = (SELECT ucc_security.current_student()))
                WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
            """,
            reverse_sql="""
                DROP POLICY student_owner ON academics_classsession;
                ALTER TABLE academics_classsession NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE academics_classsession DISABLE ROW LEVEL SECURITY;
                ALTER TABLE academics_classsession DROP CONSTRAINT classsession_course_same_owner;
            """,
        ),
    ]
