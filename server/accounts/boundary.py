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
            FROM pg_roles r WHERE rolname=current_user''')
        if cursor.fetchone() != (False,):
            raise ImproperlyConfigured('Authentication requires a separate restricted database role.')
