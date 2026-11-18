# Milestone 2B — database security and student isolation

This milestone adds a tested service/database boundary for the three academic
record tables. It does not add public authentication, registration, a web API,
JSON imports, deployment or changes to CLI/Streamlit/GPA calculations.
Python 3.12, Django 5.2.19 LTS, psycopg 3.3.8 and PostgreSQL 17 remain supported.
No additional application dependency is needed. PostgreSQL's trusted `pgcrypto`
extension is installed by migration 0004 in its private `ucc_crypto` schema.
Use a dedicated application database with no pre-existing pgcrypto installation;
the migration deliberately fails instead of taking over an existing extension.

## Milestone 3 update

For application authentication use [AUTHENTICATION.md](AUTHENTICATION.md). The
historical persisted-Student fixture boundary below is now available ONLY in
explicit non-web 2B test settings. Web applications require a verified live-session
principal and session/password-bound capabilities; they cannot mint from a Student
instance. Academic RLS/roles/context remain as described here. Auth web settings
configure a separate restricted account/session role, never a migration connection.

## Study materials update

Two more student-owned tables use the same signed context, forced RLS and
same-owner foreign keys: `academics_studymaterial` and `academics_materialfile`.
Runtime grants for stored files exclude UPDATE entirely, and `require_runtime_role`
now requires forced RLS on the academic tables (nine: six including `academics_studentprofile`,
see STUDENT_WEBSITE.md, the AI ledger and results, see AI_STUDY_ASSISTANT.md, and the saved search
text `academics_materialtext`, which like stored files is never updated) and refuses TRUNCATE, REFERENCES,
TRIGGER or stored-file UPDATE grants. After `migrate`, re-run `configure_runtime`
before starting the website. See
[STUDY_MATERIALS.md](STUDY_MATERIALS.md).

## Trusted ownership boundary (historical 2B fixture adapter)

`academics.ownership.identity_for_verified_student(principal)` is an INTERNAL
adapter boundary. Only trusted server code that already verified the principal
may call it. It requires a persisted, active Django Student and creates a signed,
immutable `TrustedStudent` capability with a five-minute lifetime. There is no
public authentication adapter in this milestone. Django's `is_authenticated` flag
on a Student object does not itself authenticate a person. Never construct a
Student from request JSON/URL owner IDs and pass it to this factory. Authentication
integration and its tests are required before any public endpoint is added.

Every service operation accepts the capability, not a student UUID, dictionary,
or client-supplied Student object. Its signature binds the UUID and expiration.
Missing, malformed, expired and altered capabilities fail with `OwnershipRequired`.
The database also verifies that the signed student still exists and is active.
A capability must not be serialized into a browser response or logged as a token.
Arbitrary Python execution in the trusted process is outside this boundary: that
process holds the signing key and can deliberately act as another student.

`academics.services` exports `semesters`, `courses` and `assignments`, each with:

- `create(identity, **allowed_fields)`
- `list(identity)` (an evaluated list, not a lazy queryset)
- `retrieve(identity, identifier)`
- `update(identity, identifier, version=expected_version, **allowed_fields)`
- `delete(identity, identifier, version=expected_version)`

Owners always come from the capability. ID, owner, normalized code, version and
timestamp fields are not accepted as client changes. Parent UUIDs are resolved
under the same owner. Foreign/nonexistent/malformed record and parent UUIDs yield
the same `RecordNotFound` message; duplicate/invalid records and dependency-protected
deletes yield generic `InvalidRecord` errors without constraint details.
`RecordConflict` means a visible record changed since the caller read its version.
A row already deleted before retrieval is `RecordNotFound`. Error translation
into HTTP responses is future API work; do not expose raw database exceptions.

All operations explicitly scope ORM queries by owner as well as using RLS.
Existing shared credit/grade validation runs; database constraints remain intact.
Owner validation/unique checks that would require account-table access are left
to database FK/UNIQUE constraints. Runtime cannot read account records. Parent
validation follows the instance's database alias, never the migrator connection.
Returned model instances are snapshots: use another service call to refresh or
write them, rather than accessing lazy relationships outside an owner transaction.

## Why a signed PostgreSQL context is necessary

A custom PostgreSQL setting such as `ucc.student_id` is user-settable. A policy
that trusts that setting alone can be bypassed by SQL setting another UUID.
This design also requires a SHA-256 HMAC signature over:

```
transaction|canonical_student_uuid|full_transaction_id|backend_pid
```

`student_transaction(identity)` starts its own atomic transaction, obtains
`pg_current_xact_id()` and `pg_backend_pid()`, signs the payload in Python and
sets the UUID and signature using transaction-local `set_config(..., true)`.
The private database function `ucc_security.current_student()` verifies the
signature with a key in `ucc_security.context_key`, then checks account activation.
Missing/bad settings or an unprovisioned key return NULL, so access fails closed.

The verifier is SECURITY DEFINER with `search_path=pg_catalog`, fully qualified
application/crypto objects, no dynamic SQL, and no PUBLIC execution grant. Its
owner is the migrator, not runtime. It exposes no arbitrary signing function or
key reader. Runtime gets EXECUTE on this verifier and USAGE on its schema only;
it cannot access the private key table or crypto schema.

The signature cannot be repurposed for another owner, new transaction or backend.
Even a session-level stale setting cannot authenticate a later transaction.
The capability signature uses a separate `identity|...` payload domain and cannot
be reused as a database signature. Signing keys are random, at least 32 bytes,
hex-encoded privately as `UCC_CONTEXT_SIGNING_KEY`, unique per database/environment and separate from DJANGO_SECRET_KEY.
The Python and private database copies must match. Never log SQL parameters for
the provisioning command or expose that key in application diagnostics.

## RLS and role privileges

Migration 0004 ENABLEs and FORCEs RLS on `academics_semester`, `academics_course`
and `academics_assignment`. Each has a FOR ALL policy with BOTH:

- `USING (owner_id = current_student())` for SELECT/UPDATE/DELETE visibility.
- `WITH CHECK (owner_id = current_student())` for INSERT/UPDATE output rows.

Composite owner-consistent foreign keys from Milestone 2A remain authoritative.
A permitted owner cannot reassign a row to another owner. Plain/forged UUID
settings, direct SQL, bulk writes and known foreign UUIDs cannot bypass these
policies under the configured runtime role. PostgreSQL integrity checks may run
outside RLS to protect referential integrity; service errors deliberately mask
their details. RLS is not a general solution for every database metadata/timing
side channel or denial-of-service attempt.

| Role | Rights and restrictions |
| --- | --- |
| Cluster DBA | Creates separate roles/database. Superusers and BYPASSRLS roles can bypass RLS; never use them for application requests. Keep credentials outside the runtime process. |
| Migrator | Owns the dedicated DB/schema/tables/private verifier/key. No SUPERUSER, BYPASSRLS, CREATEROLE or role memberships. Normal provisioning does not require CREATEDB. FORCE RLS applies, but the owner can alter schema/policies and read keys, so it is still privileged and must never serve requests. |
| Runtime | LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE, no memberships or owned objects. CONNECT, schema USAGE, verifier EXECUTE and SELECT/INSERT/DELETE plus column-limited UPDATE on ONLY the academic tables (semester, course, assignment, and since study materials, studymaterial and materialfile, which has no UPDATE at all; studentprofile has SELECT/INSERT and column-limited UPDATE, never DELETE; the AI ledger studyairequest has SELECT/INSERT and UPDATE of only status, error_category and updated_at, never DELETE; studyairesult has SELECT/INSERT/DELETE, never UPDATE). No account/key/migration table access, DDL, TRUNCATE or TEMP privileges. |

`configure_runtime` checks role flags, memberships and object ownership, revokes
PUBLIC app-database access and schema creation, clears the role's app schema/table
grants, grants only the above privileges, and installs the key atomically.
Use a new dedicated role, not a shared pre-existing application role. Do not grant
PUBLIC table access or add other role memberships/privileges afterward. New tables
are not automatically granted to runtime: migrations need an explicit security
review. Services also refuse privileged roles or academic tables without forced RLS.

Runtime UPDATE grants exclude UUID, owner and created_at columns, reinforcing immutable
identity/ownership and creation timestamps even for direct SQL.

The application runtime environment must contain only its runtime PGUSER/PGPASSWORD
and signing key, never the migrator/DBA password or a role it can SET ROLE into.
Provisioning/test settings deliberately contain privileged connections and are not
application settings. Keep migration tooling and secret access operationally separate.

## Local setup and secrets

Follow the hashed dependency and localhost PostgreSQL installation instructions in
[DATABASE_FOUNDATION.md](DATABASE_FOUNDATION.md). PostgreSQL 17 must supply pgcrypto.
Use the PostgreSQL administrator console to create NEW dedicated roles/database:

```sql
CREATE ROLE ucc_migrator LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE ROLE ucc_runtime LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
-- In psql, use its private password prompts (no password literals in SQL/history):
\password ucc_migrator
\password ucc_runtime
CREATE DATABASE ucc OWNER ucc_migrator;
```

For migration/provisioning, privately set PGUSER/PGPASSWORD to the migrator,
PGDATABASE=ucc, PGHOST=127.0.0.1, UCC_RUNTIME_ROLE=ucc_runtime, DJANGO_SECRET_KEY,
and UCC_CONTEXT_SIGNING_KEY. Generate the latter locally with
`python -c 'import secrets; print(secrets.token_hex(32))'` and store it privately.

```sh
python server/manage.py migrate --noinput
python server/manage.py configure_runtime
python server/manage.py makemigrations --check --dry-run
```

Then use a separate process environment with PGUSER/PGPASSWORD set to runtime,
the same database/signing key, and DJANGO_SETTINGS_MODULE=config.settings.runtime.
No migrator password belongs there. There are still no application routes;
production settings remain disabled. Bind any local development service only to
127.0.0.1. Local password authentication should use SCRAM. Remote TLS, public
hosting and production secret management are not approved by this milestone.

Re-running configure_runtime with a new signing key rotates the database copy;
coordinate the application copy at the same time. Existing contexts/capabilities
will fail closed when keys disagree. Backup/restore/key rotation operational drills
are not implemented. Reverse migrations remove the RLS/key objects, so only use
that path in disposable tests or a separately reviewed offline maintenance plan;
reapplying requires provisioning grants and the key again.

## Transactions and optimistic concurrency

`student_transaction(identity)` owns the database transaction. It rejects unmanaged
outer transactions, disabled autocommit, raw SQL BEGIN and nested changes of student.
Nested operations for the same identity use savepoints. Exceptions roll back the
unit; caught inner failures roll back their savepoint, leaving the outer unit usable.
Context variables are reset on every exit, and PostgreSQL SET LOCAL values end at
commit/rollback. Transaction-pooling can therefore reuse a connection without
inheriting a student's identity. Statement pooling is not supported. Keep operations
synchronous and transactions short; actual external pool products are not deployed
or load-tested here. Tests exercise the same backend reused across owners and replay
on a separate login/backend, not a simulated SQLite database.

Semesters now also have positive record_version tokens. Updates compare the
expected version and atomically write fields, `version = version + 1` and updated_at
in one SQL statement. A competing writer gets zero updated rows and RecordConflict.
Deletes lock the visible row and compare its version before deleting. Creation times
are preserved; failed updates/rollbacks preserve timestamps and versions. Creation
starts at version 1. Do not wrap these services in ATOMIC_REQUESTS or an external
atomic block; use student_transaction for a multi-operation unit instead.

```python
# verified_principal is supplied by trusted server code, never constructed from a request owner ID.
identity = identity_for_verified_student(verified_principal)
with student_transaction(identity):
    updated = courses.update(identity, course_id, version=previous_version, actual_grade="B")
    assignments.update(identity, assignment_id, version=assignment_version, completed=True)
```

Optimistic locking is the supported SERVICE contract. A direct SQL writer allowed
by RLS can still change its own versions/update timestamps without that contract. Runtime
is not meant to accept arbitrary user SQL. Privileged migrations/maintenance need
their own reviewed write/version policy. Timestamps are not an immutable audit log.

## Tests and CI

Use synthetic data only, in a disposable local PostgreSQL cluster. Preserve the
113 legacy tests and 33 original foundation tests unchanged. Run the latter as a
privileged TEST HARNESS, never the runtime process: those older tests deliberately
inspect unrestricted schema/data and reverse migrations to 0002. Destroy that test
DB afterward. Run the new security suite separately in a freshly migrated test DB
with the actual non-superuser migration/runtime login roles.

```sh
python -m unittest discover -v
# Dedicated disposable DBA test environment:
python server/manage.py test accounts academics --settings=config.settings.test -v 2
```

For the security suite, a DBA first creates dedicated test roles. The optional
`tools/prepare_security_test_roles.py` helper is test-only and refuses existing
roles/databases. Privately set UCC_DISPOSABLE_TEST_CLUSTER=1,
UCC_MIGRATION_ROLE/UCC_MIGRATION_PASSWORD, UCC_RUNTIME_ROLE/UCC_RUNTIME_PASSWORD,
and UCC_SECURITY_SCRATCH_DATABASE. PG* must initially connect to the disposable DBA
scratch DB. It creates a test migrator with CREATEDB so Django can create/drop its
test DB; that privilege is NOT needed or permitted for the runtime role.

```sh
python tools/prepare_security_test_roles.py
# Change private PGUSER/PGPASSWORD to the test migrator; PGDATABASE to its scratch DB.
# Set PGTESTDATABASE to a DIFFERENT disposable name and UCC_CONTEXT_SIGNING_KEY privately.
python server/manage.py test security_tests --settings=config.settings.security_test -v 2
python tools/check_repository_safety.py
python -m pip check
python -m pip_audit --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt
```

The security runner applies fresh migrations as the non-superuser migrator,
provisions grants/key, and connects the runtime alias through a separate LOGIN
(not SET ROLE from a superuser). It tests services, SQL policies, signing/replay,
permissions, rollback, migration reversal/reapplication and real simultaneous edits.
CI runs all three suites and audits both dependency locks. CI generates ephemeral
keys/passwords; its PostgreSQL service remains isolated on loopback and uses trust
only within the disposable runner. Local verification also uses actual SCRAM login
passwords. No SQLite claim substitutes for PostgreSQL behavior.

## Limits before Milestone 3

This verifies isolation for configured academic services and restricted PostgreSQL
connections. It does NOT establish complete end-to-end application security.
Public authentication/authorization integration, session/CSRF/API permission tests,
account recovery/deactivation policy, secure production credentials/transport,
external-pool integration/load testing, pagination/resource limits, backup/restore,
monitoring and durable audit history still require design and verification.
DBA/migrator compromise and arbitrary trusted Python execution can bypass this
boundary. CLI/Streamlit remain independent local single-user JSON applications;
they do not gain multi-user isolation through these new database services.
Historical JSON provenance concerns from Milestone 1 remain unchanged.
