"""Ordinary UUID foreign keys do not enforce same-owner relationships."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academics", "0001_initial")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_course
                ADD CONSTRAINT course_semester_same_owner
                FOREIGN KEY (semester_id, owner_id)
                REFERENCES academics_semester (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
                ALTER TABLE academics_assignment
                ADD CONSTRAINT assignment_course_same_owner
                FOREIGN KEY (course_id, owner_id)
                REFERENCES academics_course (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
            """,
            reverse_sql="""
                ALTER TABLE academics_assignment DROP CONSTRAINT assignment_course_same_owner;
                ALTER TABLE academics_course DROP CONSTRAINT course_semester_same_owner;
            """,
        ),
    ]
