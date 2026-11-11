"""Fail closed if a web process is accidentally configured with elevated credentials."""
from django.core.exceptions import ImproperlyConfigured
from django.db import connections


def require_auth_role():
    connection = connections['auth']
    with connection.cursor() as cursor:
        cursor.execute('''SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole
            OR r.rolinherit OR NOT r.rolcanlogin
            OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
            OR EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid)
            OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
            OR EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
            OR has_schema_privilege(current_user, 'public', 'CREATE')
            OR has_schema_privilege(current_user, 'ucc_security', 'USAGE')
            OR has_database_privilege(current_user, current_database(), 'CREATE')
            OR has_database_privilege(current_user, current_database(), 'TEMP')
            OR NOT has_table_privilege(current_user, 'accounts_student', 'SELECT')
            OR NOT has_table_privilege(current_user, 'django_session', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_course', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_semester', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_assignment', 'SELECT')
            -- S0-02A: once accounts.0003 exists, required grants must be present and
            -- identity-binding columns must stay non-updatable. CASE keeps older schemas valid.
            OR CASE WHEN to_regclass('public.accounts_trusteddevice') IS NULL THEN false ELSE (
                NOT has_table_privilege(current_user, 'public.accounts_trusteddevice', 'SELECT')
                OR NOT has_table_privilege(current_user, 'public.accounts_trusteddevice', 'INSERT')
                OR NOT has_table_privilege(current_user, 'public.accounts_trusteddevice', 'DELETE')
                OR NOT has_column_privilege(current_user, 'public.accounts_trusteddevice', 'current_digest', 'UPDATE')
                OR has_column_privilege(current_user, 'public.accounts_trusteddevice', 'id', 'UPDATE')
                OR has_column_privilege(current_user, 'public.accounts_trusteddevice', 'student_id', 'UPDATE')
                OR has_column_privilege(current_user, 'public.accounts_trusteddevice', 'created_at', 'UPDATE')
                OR has_table_privilege(current_user, 'public.accounts_trusteddevice', 'TRUNCATE, TRIGGER')) END
            OR CASE WHEN to_regclass('public.accounts_devicegeneration') IS NULL THEN false ELSE (
                NOT has_table_privilege(current_user, 'public.accounts_devicegeneration', 'SELECT')
                OR NOT has_table_privilege(current_user, 'public.accounts_devicegeneration', 'INSERT')
                OR NOT has_column_privilege(current_user, 'public.accounts_devicegeneration', 'generation', 'UPDATE')
                OR has_column_privilege(current_user, 'public.accounts_devicegeneration', 'student_id', 'UPDATE')
                OR has_table_privilege(current_user, 'public.accounts_devicegeneration', 'DELETE, TRUNCATE, TRIGGER')) END
            OR CASE WHEN to_regclass('public.accounts_loginlimit') IS NULL THEN false ELSE (
                NOT has_table_privilege(current_user, 'public.accounts_loginlimit', 'SELECT')
                OR NOT has_table_privilege(current_user, 'public.accounts_loginlimit', 'INSERT')
                OR NOT has_table_privilege(current_user, 'public.accounts_loginlimit', 'DELETE')
                OR NOT has_column_privilege(current_user, 'public.accounts_loginlimit', 'attempts', 'UPDATE')
                OR has_column_privilege(current_user, 'public.accounts_loginlimit', 'bucket', 'UPDATE')
                OR has_column_privilege(current_user, 'public.accounts_loginlimit', 'kind', 'UPDATE')
                OR has_table_privilege(current_user, 'public.accounts_loginlimit', 'TRUNCATE, TRIGGER')) END
            FROM pg_roles r WHERE rolname=current_user''')
        if cursor.fetchone() != (False,):
            raise ImproperlyConfigured('Authentication requires a separate restricted database role.')
