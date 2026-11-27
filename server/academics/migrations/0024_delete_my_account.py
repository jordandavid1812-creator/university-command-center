"""Launch step F: self-service account deletion.

ucc_security.delete_my_account() takes no arguments. It deletes only the student proven by the
signed transaction context (ucc_security.current_student()) and refuses without one. Every table
that refers to accounts_student is emptied for that student, children first, then the account
itself, in the caller's single transaction. Explicit WHERE clauses keep it correct even where the
function owner bypasses row-level security (Supabase). The website gets EXECUTE through
configure_runtime; nothing else does.
"""
from django.db import migrations

# Children before parents (composite same-owner foreign keys are not deferrable).
ACADEMIC = ("academics_studyairesult", "academics_studyairequest", "academics_materialtext",
            "academics_materialfile", "academics_studytopic", "academics_studyplan", "academics_classsession",
            "academics_assignment", "academics_studymaterial", "academics_course", "academics_semester",
            "academics_studentprofile")
ACCOUNT = ("accounts_accounttoken", "accounts_trusteddevice", "accounts_devicegeneration", "accounts_signupcode")

FUNCTION = """
CREATE FUNCTION ucc_security.delete_my_account() RETURNS integer
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
""" + "".join(f"    DELETE FROM public.{table} WHERE owner_id = me;\n" for table in ACADEMIC) + \
    "".join(f"    DELETE FROM public.{table} WHERE student_id = me;\n" for table in ACCOUNT) + """
    DELETE FROM public.accounts_student WHERE id = me;
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END;
$function$;
REVOKE ALL ON FUNCTION ucc_security.delete_my_account() FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [("academics", "0023_ai_site_usage_security"), ("accounts", "0005_signup_code")]
    operations = [
        migrations.RunSQL(sql=FUNCTION, reverse_sql="DROP FUNCTION ucc_security.delete_my_account();"),
    ]
