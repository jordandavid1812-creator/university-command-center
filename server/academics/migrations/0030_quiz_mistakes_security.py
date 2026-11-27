"""Mistake bank: a same-owner link (mistake to saved quiz), forced row-level security, and account
deletion that also removes the student's mistakes (children first, before their quiz results)."""
from django.db import migrations

POLICY = """
    ALTER TABLE academics_quizmistake ENABLE ROW LEVEL SECURITY;
    ALTER TABLE academics_quizmistake FORCE ROW LEVEL SECURITY;
    CREATE POLICY student_owner ON academics_quizmistake
    FOR ALL TO PUBLIC
    USING (owner_id = (SELECT ucc_security.current_student()))
    WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
"""
UNDO_POLICY = """
    DROP POLICY student_owner ON academics_quizmistake;
    ALTER TABLE academics_quizmistake NO FORCE ROW LEVEL SECURITY;
    ALTER TABLE academics_quizmistake DISABLE ROW LEVEL SECURITY;
"""

# Children before parents (composite same-owner foreign keys are not deferrable).
ACADEMIC = ("academics_quizmistake", "academics_studyairesult", "academics_studyairequest", "academics_materialtext",
            "academics_materialfile", "academics_studytopic", "academics_studyplan", "academics_classsession",
            "academics_assignment", "academics_studymaterial", "academics_course", "academics_semester",
            "academics_studentprofile")
ACCOUNT = ("accounts_accounttoken", "accounts_trusteddevice", "accounts_devicegeneration", "accounts_signupcode")


def function(tables):
    return """
CREATE OR REPLACE FUNCTION ucc_security.delete_my_account() RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    me uuid := ucc_security.current_student();
    removed integer;
BEGIN
    IF me IS NULL THEN
        RAISE EXCEPTION 'A signed student context is required.' USING ERRCODE = '42501';
    END IF;
""" + "".join(f"    DELETE FROM public.{table} WHERE owner_id = me;\n" for table in tables) + \
        "".join(f"    DELETE FROM public.{table} WHERE student_id = me;\n" for table in ACCOUNT) + """
    DELETE FROM public.accounts_student WHERE id = me;
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END;
$function$;
REVOKE ALL ON FUNCTION ucc_security.delete_my_account() FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [("academics", "0029_quiz_mistakes")]
    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE academics_quizmistake
                ADD CONSTRAINT quizmistake_result_same_owner
                FOREIGN KEY (result_id, owner_id) REFERENCES academics_studyairesult (id, owner_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION NOT DEFERRABLE;
            """ + POLICY + function(ACADEMIC),
            reverse_sql=function(ACADEMIC[1:]) + UNDO_POLICY + """
                ALTER TABLE academics_quizmistake DROP CONSTRAINT quizmistake_result_same_owner;
            """,
        ),
    ]
