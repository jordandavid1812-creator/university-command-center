"""Create NEW roles/databases on an explicitly disposable PostgreSQL test cluster.

Connect as a cluster DBA via PG* environment variables. Passwords come only from
private environment variables. This script never changes existing roles/databases.
The migrator gets CREATEDB exclusively so Django can create/drop its test DB.
"""
import os
import psycopg
from psycopg import sql


def required(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name} privately before running this test-only helper.")
    return value


def main():
    if os.environ.get("UCC_DISPOSABLE_TEST_CLUSTER") != "1":
        raise SystemExit("This helper requires UCC_DISPOSABLE_TEST_CLUSTER=1; never use a production cluster.")
    migrator = required("UCC_MIGRATION_ROLE")
    runtime = required("UCC_RUNTIME_ROLE")
    scratch = required("UCC_SECURITY_SCRATCH_DATABASE")
    migration_password = required("UCC_MIGRATION_PASSWORD")
    runtime_password = required("UCC_RUNTIME_PASSWORD")
    auth_role = os.environ.get("UCC_AUTH_ROLE")
    auth_password = required("UCC_AUTH_PASSWORD") if auth_role else None
    targets = [migrator, runtime] + ([auth_role] if auth_role else [])
    if len(set(targets)) != len(targets):
        raise SystemExit("Migration and runtime role names must differ.")
    with psycopg.connect(autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (targets,)).fetchone():
            raise SystemExit("A target role already exists; nothing was changed.")
        if connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (scratch,)).fetchone():
            raise SystemExit("The scratch database already exists; nothing was changed.")
        with connection.transaction():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS CREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(migrator), sql.Literal(migration_password)))
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(runtime), sql.Literal(runtime_password)))
            if auth_role:
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                    sql.Identifier(auth_role), sql.Literal(auth_password)))
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(scratch), sql.Identifier(migrator)))
    print("Disposable test roles and scratch database created; no secret values printed.")


if __name__ == "__main__":
    main()
