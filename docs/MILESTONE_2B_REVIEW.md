# Milestone 2B implementation and verification report

Verified locally on 11 November 2026. Starting master:
`34c9c8e34426c718da11c043375a34eecb653d9d`, the merge of PR #20.
Feature branch: `feature/database-security`. No merge or deployment is included.

## Implementation

- `academics/ownership.py`: trusted five-minute principal capabilities and signed,
  transaction/backend-bound PostgreSQL owner context. No unsigned UUID setting is
  trusted. Missing/invalid context fails closed. Active account status is checked
  in the private database verifier.
- `academics/services.py`: owner-scoped create/list/retrieve/update/delete for all
  three academic models. Owner/server fields cannot be supplied by clients;
  foreign/nonexistent UUIDs share the same error. Results are evaluated snapshots.
- Migrations 0003/0004: semester record versions, preserved foundation constraints,
  private pgcrypto/HMAC verifier/key storage and ENABLE + FORCE RLS with USING and
  WITH CHECK policies for every academic table and SQL operation.
- `configure_runtime`: migrator-only atomic key/grant provisioning. Separate runtime
  LOGIN has no bypass, memberships, object ownership, DDL, TRUNCATE, TEMP, account,
  migration-table or key privileges. UPDATE grants exclude ID, owner and created_at.
  Provisioning also clears old column-level and PUBLIC grants.
- Runtime/test settings, disposable test-role helper and a restricted-role test
  runner keep application operations separate from migration/setup privileges.
- Transactional units/savepoints, atomic version compare-and-swap updates,
  version-checked locked deletes and explicit update timestamps. Stale edits fail.
- CI adds restricted-role tests with generated/masked ephemeral test secrets.

## Versions and actual database roles

Python 3.12.14; Django 5.2.19 LTS; psycopg 3.3.8; PostgreSQL 17.11.
No new application dependencies or lock changes were needed. PostgreSQL pgcrypto
was installed by migration in a private schema. Tests used an official PostgreSQL
17 container mapped ONLY to 127.0.0.1:55433 with SCRAM password authentication and
synthetic identities. No SQLite tests were used to claim PostgreSQL behavior.

The original foundation suite used a disposable DBA test harness. The security
suite used a different fresh database, created/migrated by an actual NOSUPERUSER
NOBYPASSRLS migrator, and a separate restricted runtime LOGIN/password. Runtime
was not simulated with SET ROLE from a privileged session. The migrator had CREATEDB
only to support Django test database creation; runtime never had that privilege.
The CI helper/bootstrap path was also executed locally with separate new test roles.

## Results

- **113/113 legacy tests passed**, unchanged, with Streamlit installed; no skips.
- **33/33 original Milestone 2A database tests passed**, unchanged, against PostgreSQL.
- **46/46 new security tests passed** against PostgreSQL; no remaining failures.
- Fresh migrations and security migration reversal/reapplication passed. Existing
  owner composite FKs, grade, credit-range and exact-scale checks remain intact.
- `makemigrations --check --dry-run`: no changes detected.
- Django system checks, compile/whitespace checks and dependency consistency passed.
- Both hashed runtime locks audited with strict pip-audit: **no known vulnerabilities**;
  no suppressions. Repository safety is checked before committing.

The 46 tests include all CRUD ownership contexts, known/malformed/foreign UUIDs,
client owner-field rejection, deactivation, parent isolation, direct SQL SELECT/
INSERT/UPDATE/DELETE, forged UUID/signature settings, token replay across transactions
and backends, session-level stale settings, actual connection reuse after commit and
rollback, role/privilege checks, protected key/account tables, forced RLS on table
owners, immutable ID/owner/creation fields, migration/grant re-provisioning, rollback/
savepoints and synchronized two-connection optimistic-update races with exactly one
winner. Services were also checked to make zero queries on the migration connection.

The original destructive 2A migration test restores schema 0002; it is intentionally
run in a separate disposable database/process from the security suite, which applies
all current migrations. No original tests were changed to hide failures.

Hosted CI results must be checked on the pushed commit/PR; local results alone do
not establish hosted success. All three CI jobs now include the full required suites
and runtime-lock audits. No personal JSON was read/imported, no GPA formula changed,
and the CLI/Streamlit source and existing runtime locks remain unchanged from master.

## Remaining limits before Milestone 3

Isolation is verified for the supported academic service/restricted-role database
boundary, not for a public application. The verified-principal factory is a trusted
internal integration boundary, not an authentication implementation; never feed it
a principal constructed from untrusted owner IDs. Public auth/session/API permission
integration is still required. Runtime must never receive migration/DBA credentials.
DBA/migrator compromise or arbitrary trusted Python execution can bypass the boundary.

External pool integration/load tests, production TLS/secrets/deployment, rate limits,
backup/restore drills, durable audit history and account recovery/retention policy
remain deferred. Direct SQL for one's own rows is permitted by RLS and can bypass
service-only optimistic locking/update-time rules. CLI/Streamlit remain local
single-user JSON apps. Production settings are still disabled; no hosting is approved.

See [DATABASE_SECURITY.md](DATABASE_SECURITY.md) for setup, operations, precise trust
assumptions, privileges, transaction behavior and all test commands.
