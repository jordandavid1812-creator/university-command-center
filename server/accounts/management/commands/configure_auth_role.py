"""Offline migrator grants for a distinct authentication LOGIN, never academic access."""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql


class Command(BaseCommand):
    help = 'Provision a separate existing restricted account/session role, without academic/key access.'

    def handle(self, *args, **options):
        role = os.environ.get('UCC_AUTH_ROLE', '')
        if not role or role == os.environ.get('UCC_RUNTIME_ROLE'):
            raise CommandError('Set UCC_AUTH_ROLE to a separate restricted login.')
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('''SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin
                              FROM pg_roles WHERE rolname=%s''', [role])
            if cursor.fetchone() != (False, False, False, False, False, True):
                raise CommandError('Auth role must be LOGIN NOINHERIT with no privileged role flags.')
            cursor.execute('''SELECT EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                OR EXISTS (SELECT 1 FROM pg_class WHERE relowner=r.oid)
                OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
                OR EXISTS (SELECT 1 FROM pg_database WHERE datdba=r.oid)
                OR EXISTS (SELECT 1 FROM pg_proc WHERE proowner=r.oid)
                FROM pg_roles r WHERE rolname=%s''', [role])
            if cursor.fetchone() != (False,):
                raise CommandError('Auth role must have no memberships or owned objects.')
            cursor.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM {}').format(
                sql.Identifier(connection.settings_dict['NAME']), sql.Identifier(role)))
            cursor.execute(sql.SQL('REVOKE ALL ON SCHEMA public, ucc_security, ucc_crypto FROM {}').format(sql.Identifier(role)))
            cursor.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA public, ucc_security FROM {}').format(sql.Identifier(role)))
            cursor.execute(sql.SQL('REVOKE ALL ON FUNCTION ucc_security.current_student() FROM {}').format(sql.Identifier(role)))
            cursor.execute('''SELECT n.nspname, c.relname, array_agg(a.attname ORDER BY a.attnum)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_attribute a ON a.attrelid=c.oid
                WHERE n.nspname IN ('public','ucc_security') AND c.relkind IN ('r','p')
                  AND a.attnum>0 AND NOT a.attisdropped GROUP BY n.nspname,c.relname''')
            for schema, table, columns in cursor.fetchall():
                cursor.execute(sql.SQL('REVOKE ALL ({}) ON {}.{} FROM {}').format(
                    sql.SQL(', ').join(map(sql.Identifier, columns)), sql.Identifier(schema),
                    sql.Identifier(table), sql.Identifier(role)))
            cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(
                sql.Identifier(connection.settings_dict['NAME']), sql.Identifier(role)))
            cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
            cursor.execute(sql.SQL('GRANT SELECT, INSERT ON accounts_student TO {}').format(sql.Identifier(role)))
            cursor.execute(sql.SQL('GRANT UPDATE (password, last_login, email_verified_at, updated_at) ON accounts_student TO {}').format(sql.Identifier(role)))
            cursor.execute(sql.SQL('GRANT SELECT, INSERT, DELETE ON accounts_accounttoken, accounts_auththrottle, django_session TO {}').format(sql.Identifier(role)))
            for table, fields in (
                ('accounts_accounttoken', ['consumed_at']),
                ('accounts_auththrottle', ['attempts', 'expires_at']),
                ('django_session', ['session_data', 'expire_date']),
            ):
                cursor.execute(sql.SQL('GRANT UPDATE ({}) ON {} TO {}').format(
                    sql.SQL(', ').join(map(sql.Identifier, fields)), sql.Identifier(table), sql.Identifier(role)))
            # S0-02A trusted-device/login-limit tables (accounts.0003). Granted only when the
            # migration is applied; middleware fails closed if they exist without these grants.
            # Identity binding (id, student_id, created_at, bucket, kind) is never updatable.
            for table, fields in (
                ('accounts_trusteddevice', ['current_digest', 'previous_digest', 'rotated_at', 'last_used_at', 'expires_at']),
                ('accounts_loginlimit', ['attempts', 'expires_at']),
            ):
                cursor.execute('SELECT to_regclass(%s) IS NOT NULL', ['public.' + table])
                if cursor.fetchone()[0]:
                    cursor.execute(sql.SQL('GRANT SELECT, INSERT, DELETE ON {} TO {}').format(
                        sql.Identifier(table), sql.Identifier(role)))
                    cursor.execute(sql.SQL('GRANT UPDATE ({}) ON {} TO {}').format(
                        sql.SQL(', ').join(map(sql.Identifier, fields)), sql.Identifier(table), sql.Identifier(role)))
        self.stdout.write('Separate authentication role configured; academic runtime privileges unchanged.')
