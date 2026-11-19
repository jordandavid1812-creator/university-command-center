-- University Command Center: the read-only backup login (launch step H). Not a numbered file:
-- run it once in the Supabase SQL editor (as the postgres login), then set its password with the
-- private file from tools/backup_password.py. Safe to run again.
--
-- ucc_backup can only READ the student tables below. BYPASSRLS lets pg_dump copy every student's
-- rows in one go (row-level security would otherwise hide them all); it has no write rights, every
-- transaction is read-only, and it cannot read sessions, sign-in tokens, security counters or the
-- private signing key.

BEGIN;

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ucc_backup') THEN
        CREATE ROLE ucc_backup LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS
            CONNECTION LIMIT 2;
    END IF;
END
$role$;
-- (SUPERUSER and REPLICATION can only be named by a superuser; both stay off from CREATE ROLE, and
-- the restore test checks it.)
ALTER ROLE ucc_backup LOGIN NOINHERIT NOCREATEDB NOCREATEROLE BYPASSRLS CONNECTION LIMIT 2;
ALTER ROLE ucc_backup SET default_transaction_read_only = on;
ALTER ROLE ucc_backup SET statement_timeout = '15min';
ALTER ROLE ucc_backup SET idle_in_transaction_session_timeout = '15min';

REVOKE ALL ON SCHEMA ucc_security, ucc_crypto FROM ucc_backup;
REVOKE ALL ON ALL TABLES IN SCHEMA public, ucc_security FROM ucc_backup;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ucc_security, ucc_crypto FROM ucc_backup;
REVOKE TEMPORARY, CREATE ON DATABASE postgres FROM ucc_backup;
GRANT CONNECT ON DATABASE postgres TO ucc_backup;
GRANT USAGE ON SCHEMA public TO ucc_backup;
GRANT SELECT ON
    public.accounts_student,
    public.academics_semester, public.academics_course, public.academics_assignment,
    public.academics_studymaterial, public.academics_materialfile, public.academics_materialtext,
    public.academics_studentprofile, public.academics_studyairequest, public.academics_studyairesult,
    public.academics_classsession, public.academics_studyplan, public.academics_studytopic,
    public.academics_aisiteusage
TO ucc_backup;

COMMIT;
