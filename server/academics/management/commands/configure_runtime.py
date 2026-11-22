"""Run only with the migrator connection; never from the runtime process."""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql


class Command(BaseCommand):
    help = "Install the private context key and grant an existing restricted runtime role."

    def handle(self, *args, **options):
        role = os.environ.get("UCC_RUNTIME_ROLE", "")
        try:
            key = bytes.fromhex(os.environ.get("UCC_CONTEXT_SIGNING_KEY", ""))
        except ValueError:
            raise CommandError("UCC_CONTEXT_SIGNING_KEY must be hexadecimal.") from None
        if not role or len(key) < 32:
            raise CommandError("Set UCC_RUNTIME_ROLE and a random signing key of at least 32 bytes.")
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("""
                SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin
                FROM pg_roles WHERE rolname = %s
            """, [role])
            if cursor.fetchone() != (False, False, False, False, False, True):
                raise CommandError("Runtime must be LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE.")
            cursor.execute("SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s", [role])
            if cursor.fetchone():
                raise CommandError("Runtime must have no role memberships.")
            cursor.execute("SELECT current_user")
            if cursor.fetchone()[0] == role:
                raise CommandError("Use a separate migration role.")
            cursor.execute("""
                SELECT EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid)
                    OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
                    OR EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
                    OR EXISTS (SELECT 1 FROM pg_proc WHERE proowner=r.oid)
                FROM pg_roles r WHERE rolname=%s
            """, [role])
            if cursor.fetchone() != (False,):
                raise CommandError("Runtime must not own database objects.")
            # No public schema creation/temp objects for app connections.
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute("REVOKE ALL ON SCHEMA ucc_security, ucc_crypto FROM PUBLIC")
            cursor.execute("REVOKE ALL ON FUNCTION ucc_security.current_student() FROM PUBLIC")
            cursor.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public, ucc_security FROM PUBLIC")
            cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(connection.settings_dict["NAME"])))
            cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                sql.Identifier(connection.settings_dict["NAME"]), sql.Identifier(role)))
            cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA public, ucc_security, ucc_crypto FROM {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(connection.settings_dict["NAME"]), sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public, ucc_security TO {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public, ucc_security FROM {}").format(sql.Identifier(role)))
            # Table-level REVOKE does not remove old column-level grants.
            cursor.execute("""
                SELECT n.nspname, c.relname, array_agg(a.attname ORDER BY a.attnum)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_attribute a ON a.attrelid=c.oid
                WHERE n.nspname IN ('public','ucc_security')
                  AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
                GROUP BY n.nspname, c.relname
            """)
            for schema, table, columns in cursor.fetchall():
                cursor.execute(sql.SQL("REVOKE ALL ({}) ON {}.{} FROM PUBLIC, {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.Identifier(schema), sql.Identifier(table), sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT, DELETE ON public.academics_semester, public.academics_course, public.academics_assignment, public.academics_studymaterial, public.academics_materialfile, public.academics_materialtext, public.academics_classsession, public.academics_studyplan, public.academics_studytopic TO {}").format(sql.Identifier(role)))
            # Mistake bank (0029/0030): saved and removed, never edited. Older schemas have no table yet.
            cursor.execute("SELECT to_regclass('public.academics_quizmistake') IS NOT NULL")
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL("GRANT SELECT, INSERT, DELETE ON public.academics_quizmistake TO {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT ON public.academics_studentprofile TO {}").format(sql.Identifier(role)))
            # AI ledger: never deleted by the website; results: never edited.
            cursor.execute(sql.SQL("GRANT SELECT, INSERT ON public.academics_studyairequest TO {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT, DELETE ON public.academics_studyairesult TO {}").format(sql.Identifier(role)))
            # Launch step E: the site-wide AI counter (0022/0023). Only its count may change.
            cursor.execute("SELECT to_regclass('public.academics_aisiteusage') IS NOT NULL")
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL("GRANT SELECT, INSERT ON public.academics_aisiteusage TO {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT UPDATE (requests) ON public.academics_aisiteusage TO {}").format(sql.Identifier(role)))
            for table, columns in (
                ("academics_semester", ("label", "display_order", "record_version", "updated_at")),
                ("academics_course", ("semester_id", "original_code", "normalized_code", "name", "credit_units", "actual_grade", "record_version", "updated_at")),
                ("academics_assignment", ("course_id", "title", "due_date", "completed", "record_version", "updated_at")),
                ("academics_studymaterial", ("course_id", "title", "record_version", "updated_at")),
                ("academics_studentprofile", ("display_name", "institution", "programme", "level",
                                              "first_class_min", "second_upper_min", "second_lower_min", "third_class_min",
                                              "pass_min", "record_version", "updated_at")),
                ("academics_studyairequest", ("status", "error_category", "status_class", "updated_at")),
                ("academics_classsession", ("course_id", "weekday", "start_time", "end_time", "kind", "venue", "record_version", "updated_at")),
                ("academics_studyplan", ("exam_date", "review_days", "record_version", "updated_at")),
                ("academics_studytopic", ("title", "position", "planned_date", "done", "record_version", "updated_at")),
            ):
                cursor.execute(sql.SQL("GRANT UPDATE ({}) ON public.{} TO {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, columns)), sql.Identifier(table), sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION ucc_security.current_student() TO {}").format(sql.Identifier(role)))
            # Keep existing legacy-column grants during the additive rollout. A later
            # reviewed contract release can drop the column after old code is retired.
            cursor.execute("""SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'public.academics_studentprofile'::regclass
                              AND attname = 'matric_number' AND NOT attisdropped)""")
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL("GRANT UPDATE (matric_number) ON public.academics_studentprofile TO {}").format(sql.Identifier(role)))
            # Automatic backup (academics.0028): which backup answered an in-progress request.
            # Granted only once the columns exist, so provisioning a rolled-back schema still works.
            cursor.execute("""SELECT count(*) = 2 FROM pg_attribute WHERE attrelid = 'public.academics_studyairequest'::regclass
                              AND attname IN ('answered_by', 'answered_by_model') AND NOT attisdropped""")
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL("GRANT UPDATE (answered_by, answered_by_model) ON public.academics_studyairequest TO {}")
                               .format(sql.Identifier(role)))
            # Grade scale (academics.0025): the student's 4- or 5-point choice. Granted only once the
            # column exists, so provisioning an older (rolled-back) schema still works.
            cursor.execute("""SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'public.academics_studentprofile'::regclass
                              AND attname = 'grading_scale' AND NOT attisdropped)""")
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL("GRANT UPDATE (grading_scale) ON public.academics_studentprofile TO {}").format(
                    sql.Identifier(role)))
            # Launch step F (academics.0024): self-service deletion, only for the signed student.
            cursor.execute("SELECT to_regprocedure('ucc_security.delete_my_account()') IS NOT NULL")
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL("REVOKE ALL ON FUNCTION ucc_security.delete_my_account() FROM PUBLIC"))
                cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION ucc_security.delete_my_account() TO {}").format(
                    sql.Identifier(role)))
            cursor.execute("""
                INSERT INTO ucc_security.context_key(singleton, secret) VALUES (true, %s)
                ON CONFLICT (singleton) DO UPDATE SET secret = EXCLUDED.secret
            """, [key])
        self.stdout.write("Runtime grants and private signing key configured; no secret values printed.")
