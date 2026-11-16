"""Fail closed if a web process is accidentally configured with elevated credentials."""
from django.core.exceptions import ImproperlyConfigured
from django.db import connections

# S0-02A support tables: the EXACT auth-role allowlist (must match configure_auth_role).
# (required table privileges, exact set of updatable columns). Anything else is drift.
SUPPORT_TABLES = {
    'accounts_trusteddevice': (('SELECT', 'INSERT', 'DELETE'),
                               ('current_digest', 'expires_at', 'last_used_at', 'previous_digest', 'rotated_at')),
    'accounts_loginlimit': (('SELECT', 'INSERT', 'DELETE'), ('attempts', 'expires_at')),
    'accounts_devicegeneration': (('SELECT', 'INSERT'), ('generation',)),
}
BASE_TABLE_PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')


def table_privileges(connection):
    """All table privilege names the server knows; PostgreSQL 17 adds MAINTAIN."""
    return BASE_TABLE_PRIVILEGES + (('MAINTAIN',) if connection.pg_version >= 170000 else ())


def maintain_anywhere_sql(connection):
    """PostgreSQL 17 MAINTAIN (VACUUM/ANALYZE/REINDEX/LOCK TABLE) is never needed by app roles."""
    if connection.pg_version < 170000:
        return 'false'
    return """EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname IN ('public', 'ucc_security') AND c.relkind IN ('r', 'p')
                 AND has_table_privilege(current_user, c.oid, 'MAINTAIN'))"""


def auth_support_violation_sql(connection):
    """True if the auth role's grants on any present support table differ from the allowlist,
    or if only some of the support tables exist (partial schema)."""
    privileges = table_privileges(connection)
    grant_options = ', '.join(f'{privilege} WITH GRANT OPTION' for privilege in privileges)
    parts = []
    for table, (required, updatable) in SUPPORT_TABLES.items():
        name = f'public.{table}'
        forbidden = ', '.join(p for p in privileges if p not in required and p != 'UPDATE')
        expected = ', '.join(f"'{column}'" for column in sorted(updatable))
        checks = [f"NOT has_table_privilege(current_user, '{name}', '{p}')" for p in required]
        checks += [
            f"has_table_privilege(current_user, '{name}', '{forbidden}')",
            f"has_table_privilege(current_user, '{name}', '{grant_options}')",
            f"has_any_column_privilege(current_user, '{name}', 'REFERENCES, SELECT WITH GRANT OPTION, "
            f"INSERT WITH GRANT OPTION, UPDATE WITH GRANT OPTION, REFERENCES WITH GRANT OPTION')",
            # Exact column-level UPDATE allowlist: every required column, nothing more.
            # Bandit B608 false positive: only module-constant identifiers are interpolated.
            f"""(SELECT coalesce(array_agg(a.attname::text ORDER BY a.attname::text COLLATE "C"), '{{}}')
                 FROM pg_attribute a WHERE a.attrelid = to_regclass('{name}') AND a.attnum > 0
                  AND NOT a.attisdropped AND has_column_privilege(current_user, a.attrelid, a.attnum, 'UPDATE'))
                IS DISTINCT FROM ARRAY[{expected}]::text[]""",  # nosec B608
        ]
        parts.append(f"CASE WHEN to_regclass('{name}') IS NULL THEN false ELSE ({' OR '.join(checks)}) END")
    names = ', '.join(f"'public.{table}'" for table in SUPPORT_TABLES)
    # Bandit B608 false positive: only module-constant identifiers are interpolated.
    parts.append(f"(SELECT count(*) FROM unnest(ARRAY[{names}]) AS t(name) "
                 f"WHERE to_regclass(t.name) IS NOT NULL) NOT IN (0, {len(SUPPORT_TABLES)})")  # nosec B608
    return '(' + ' OR '.join(parts) + ')'


def runtime_support_violation_sql(connection):
    """True if the runtime role holds ANY privilege on a support table (incl. MAINTAIN)."""
    privileges = ', '.join(table_privileges(connection))
    parts = [f"""CASE WHEN to_regclass('public.{table}') IS NULL THEN false ELSE
                 has_table_privilege(current_user, 'public.{table}', '{privileges}')
                 OR has_any_column_privilege(current_user, 'public.{table}', 'SELECT, INSERT, UPDATE, REFERENCES') END"""
             for table in SUPPORT_TABLES]
    return '(' + ' OR '.join(parts) + ')'


def require_auth_role():
    connection = connections['auth']
    with connection.cursor() as cursor:
        sql = '''SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole
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
            OR has_any_column_privilege(current_user, 'academics_studymaterial', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_materialfile', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_studentprofile', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_studyairequest', 'SELECT')
            OR has_any_column_privilege(current_user, 'academics_studyairesult', 'SELECT')
            OR {support}
            OR {maintain}
            FROM pg_roles r WHERE rolname=current_user'''
        # Only module constants are interpolated (table/column/privilege names), never input.
        cursor.execute(sql.format(support=auth_support_violation_sql(connection),  # nosec B608
                                  maintain=maintain_anywhere_sql(connection)))
        if cursor.fetchone() != (False,):
            raise ImproperlyConfigured('Authentication requires a separate restricted database role.')
