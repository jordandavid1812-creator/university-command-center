"""Signed owner context: plain custom PostgreSQL settings are not trusted."""
from django.db import migrations

SETUP = """
CREATE SCHEMA ucc_security;
REVOKE ALL ON SCHEMA ucc_security FROM PUBLIC;
CREATE SCHEMA ucc_crypto;
REVOKE ALL ON SCHEMA ucc_crypto FROM PUBLIC;
CREATE EXTENSION pgcrypto WITH SCHEMA ucc_crypto;
CREATE TABLE ucc_security.context_key (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    secret bytea NOT NULL CHECK (octet_length(secret) >= 32)
);
REVOKE ALL ON TABLE ucc_security.context_key FROM PUBLIC;
CREATE FUNCTION ucc_security.current_student() RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    student uuid;
    signature text;
    signing_key bytea;
    payload text;
BEGIN
    student := NULLIF(current_setting('ucc.student_id', true), '')::uuid;
    signature := NULLIF(current_setting('ucc.student_signature', true), '');
    IF student IS NULL OR signature IS NULL THEN RETURN NULL; END IF;
    SELECT secret INTO signing_key FROM ucc_security.context_key WHERE singleton;
    IF signing_key IS NULL THEN RETURN NULL; END IF;
    payload := 'transaction|' || student::text || '|' || pg_current_xact_id()::text
               || '|' || pg_backend_pid()::text;
    IF signature <> encode(ucc_crypto.hmac(convert_to(payload, 'UTF8'), signing_key, 'sha256'), 'hex')
    THEN RETURN NULL; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.accounts_student WHERE id = student AND is_active)
    THEN RETURN NULL; END IF;
    RETURN student;
EXCEPTION WHEN invalid_text_representation THEN
    RETURN NULL;
END;
$function$;
REVOKE ALL ON FUNCTION ucc_security.current_student() FROM PUBLIC;
"""


def policy_sql(table):
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY student_owner ON {table}
        FOR ALL TO PUBLIC
        USING (owner_id = (SELECT ucc_security.current_student()))
        WITH CHECK (owner_id = (SELECT ucc_security.current_student()));
    """


TABLES = ("academics_semester", "academics_course", "academics_assignment")


class Migration(migrations.Migration):
    dependencies = [("academics", "0003_semester_version")]
    operations = [migrations.RunSQL(
        SETUP + "".join(policy_sql(table) for table in TABLES),
        reverse_sql="".join(
            f"DROP POLICY student_owner ON {table}; "
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY; "
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY; " for table in reversed(TABLES)
        ) + """
            DROP FUNCTION ucc_security.current_student();
            DROP TABLE ucc_security.context_key;
            DROP SCHEMA ucc_security;
            DROP EXTENSION pgcrypto;
            DROP SCHEMA ucc_crypto;
        """,
    )]
