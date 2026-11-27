#!/bin/sh
# Runs once, when the database volume is first created. Creates the three restricted logins
# and the website database owned by the migrator, exactly like the local setup.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
     -v dbname="$UCC_DB_NAME" \
     -v migrator="$UCC_MIGRATOR_ROLE" -v migrator_pw="$UCC_MIGRATOR_PASSWORD" \
     -v runtime="$UCC_RUNTIME_ROLE" -v runtime_pw="$UCC_RUNTIME_PASSWORD" \
     -v auth="$UCC_AUTH_ROLE" -v auth_pw="$UCC_AUTH_PASSWORD" <<'SQL'
CREATE ROLE :"migrator" LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'migrator_pw';
CREATE ROLE :"runtime" LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'runtime_pw';
CREATE ROLE :"auth" LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'auth_pw';
CREATE DATABASE :"dbname" OWNER :"migrator";
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
SQL
