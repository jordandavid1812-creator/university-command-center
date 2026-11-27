"""Study planner: same-owner links (plan to course, topic to plan) and forced row-level security."""
from django.db import migrations

TABLES = ("academics_studyplan", "academics_studytopic")


def policies(table):
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY student_owner ON {table}
        FOR ALL TO PUBLIC
        USING (owner_id = (SELECT ucc_security.current_student()))
        WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
    """


def undo(table):
    return f"""
        DROP POLICY student_owner ON {table};
        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
    """


class Migration(migrations.Migration):
    dependencies = [("academics", "0020_study_planner")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_studyplan
                ADD CONSTRAINT studyplan_course_same_owner
                FOREIGN KEY (course_id, owner_id) REFERENCES academics_course (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
                ALTER TABLE academics_studytopic
                ADD CONSTRAINT studytopic_plan_same_owner
                FOREIGN KEY (plan_id, owner_id) REFERENCES academics_studyplan (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
            """ + "".join(policies(table) for table in TABLES),
            reverse_sql="".join(undo(table) for table in TABLES) + """
                ALTER TABLE academics_studytopic DROP CONSTRAINT studytopic_plan_same_owner;
                ALTER TABLE academics_studyplan DROP CONSTRAINT studyplan_course_same_owner;
            """,
        ),
    ]
