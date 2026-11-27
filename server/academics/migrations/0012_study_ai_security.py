"""AI requests and results: same-owner links, result size limit and forced row-level security."""
from django.db import migrations

TABLES = ("academics_studyairequest", "academics_studyairesult")


def policy_sql(table):
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY student_owner ON {table}
        FOR ALL TO PUBLIC
        USING (owner_id = (SELECT ucc_security.current_student()))
        WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
    """


def reverse_policy_sql(table):
    return f"""
        DROP POLICY student_owner ON {table};
        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
    """


class Migration(migrations.Migration):
    dependencies = [("academics", "0011_study_ai_records")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_studyairesult
                ADD CONSTRAINT airesult_material_same_owner
                FOREIGN KEY (material_id, owner_id)
                REFERENCES academics_studymaterial (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;

                ALTER TABLE academics_studyairesult
                ADD CONSTRAINT airesult_request_same_owner
                FOREIGN KEY (request_id, owner_id)
                REFERENCES academics_studyairequest (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;

                ALTER TABLE academics_studyairesult
                ADD CONSTRAINT airesult_size_limit CHECK (octet_length(result::text) <= 65536);
            """ + "".join(policy_sql(table) for table in TABLES),
            reverse_sql="".join(reverse_policy_sql(table) for table in reversed(TABLES)) + """
                ALTER TABLE academics_studyairesult DROP CONSTRAINT airesult_size_limit;
                ALTER TABLE academics_studyairesult DROP CONSTRAINT airesult_request_same_owner;
                ALTER TABLE academics_studyairesult DROP CONSTRAINT airesult_material_same_owner;
            """,
        ),
    ]
