# Django and PostgreSQL foundation — Milestone 2A

This adds a database foundation alongside the local CLI and Streamlit app. It does
not connect either app to PostgreSQL, import JSON, expose account pages or approve
public hosting. Python 3.12 is supported. Django 5.2 LTS is pinned to 5.2.19;
psycopg 3.3.8 is the PostgreSQL driver. PostgreSQL 17 is the supported test target.
Keep installing security patches and auditing dependencies; a successful audit
only covers known advisories on its run date.

## Folder structure

- `server/manage.py`: separate Django command entry point; adds the repository
  root to Python's path so shared academic validation remains reusable.
- `server/config/settings/`: shared, development, PostgreSQL test and reserved
  production settings. Production settings deliberately refuse to start.
- `server/config/urls.py`: empty routing; no admin, login or registration.
- `server/accounts/`: UUID account identity and its initial migration.
- `server/academics/`: semester, course, assignment, exact credit field,
  migrations and PostgreSQL-backed tests.
- `requirements-django.txt` and `requirements-django-lock.txt`: separate direct
  and hashed database runtime dependencies. Existing Streamlit locks are unchanged.

## Local PostgreSQL setup

Install PostgreSQL 17 and its command-line client using your operating system's
trusted package repository or the official PostgreSQL installer. On Debian/Ubuntu,
where the configured repository supplies version 17:

```sh
sudo apt update
sudo apt install postgresql-17 postgresql-client-17
sudo -u postgres createuser --pwprompt ucc_dev
sudo -u postgres createdb --owner=ucc_dev ucc_dev
```

Choose your own password at the prompt. Use a dedicated local role, never a
production database or PostgreSQL superuser. Ensure `postgresql.conf` uses
`listen_addresses = 'localhost'` and `pg_hba.conf` requires `scram-sha-256` for
local TCP connections. Reload/restart PostgreSQL after editing its configuration.
Do not expose port 5432 on a public interface. Installation and service commands
vary by OS. PostgreSQL data files belong outside the Git checkout.

For tests only, use a separate local role with CREATEDB and ownership of a
separate scratch development database. The Django runner creates and drops the
named test database. Never point the test settings at personal data. A regular
application role does not need CREATEDB. Future deployment must separate migration
privileges from runtime privileges.

```sh
sudo -u postgres createuser --pwprompt --createdb ucc_test_runner
sudo -u postgres createdb --owner=ucc_test_runner ucc_test_scratch
```

## Dependencies and environment

From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip==26.3
python -m pip install --require-hashes -r requirements-lock.txt -r requirements-django-lock.txt
python -m pip check
```

The CLI still works using Python's standard library alone. Streamlit still runs
with `streamlit run web_app.py --server.address 127.0.0.1`.

Set variables in your shell, IDE's private environment settings or a secret
manager. `.env.example` lists names only; Django does not load dotenv files.
Generate a new Django secret locally using
`python -c 'import secrets; print(secrets.token_urlsafe(64))'` and place it in your
private environment. Never copy it into source, logs, screenshots or commits.
Missing `DJANGO_SECRET_KEY`, `PGDATABASE` or `PGUSER` blocks startup.

| Variable | Meaning/default |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required random secret; no source-code fallback |
| `DJANGO_DEBUG` | Explicit `1` enables development debug; default off |
| `PGDATABASE`, `PGUSER` | Required development database and role |
| `PGPASSWORD` | Private password; omit only when securely configured local authentication allows it |
| `PGHOST`, `PGPORT` | Default `127.0.0.1`, `5432`; local setup must use loopback |
| `PGSSLMODE` | Default `prefer` for local development; remote TLS policy is deferred |
| `PGTESTDATABASE` | Required disposable test database name, different from `PGDATABASE` |
| `DJANGO_SETTINGS_MODULE` | Defaults to `config.settings.development` via manage.py |

`.env` and `.env.*` are ignored except the empty `.env.example`. Shell environment
values are not automatically inherited by other terminals. Never paste passwords
into shell commands saved in history. No real student data is required here.

```sh
python server/manage.py check
python server/manage.py migrate --plan
python server/manage.py migrate
python server/manage.py showmigrations
python server/manage.py runserver 127.0.0.1:8000
```

The server has no application routes yet. The optional runserver is local only.

## Records and relationships

| Model | Fields and relationships |
| --- | --- |
| Student | Stable UUID primary key, unique username, password hash/unusable password, active flag, last login, creation/update times. No required email, name or profile data. |
| Semester | UUID, required owner, label, explicit nonnegative display order, timestamps. Order ties use creation time then UUID; labels never imply chronology. |
| Course | UUID, required owner and semester, original and normalized code, name, exact credit units, nullable actual grade, positive record version, timestamps. |
| Assignment | UUID, required owner and course, title, due date, Boolean completion flag, positive record version, timestamps. |

A student has many semesters, courses and assignments. A course belongs to exactly
one semester, and an assignment to exactly one course. Course codes are unique
per owner across all semesters; repeated-course policies are not inferred.
Account usernames are case-sensitive PostgreSQL identifiers for now, not a final
login identity policy. `create_user` without a password creates an unusable one.
Password policy enforcement in a future registration flow remains deferred.

All relationships use Django `PROTECT`. Delete assignments before their courses,
courses before their semesters, and all dependent records before an owner.
PostgreSQL foreign keys also prevent raw SQL from deleting referenced rows.
There is no cascading student-data deletion or automatic import/cleanup.

Course codes preserve the original input, normalize outer ASCII spaces and
uppercase ASCII letters. New Django records deliberately restrict code characters
to ASCII letters/digits/spaces and `_ . / -` (64 characters maximum), avoiding
Python/PostgreSQL Unicode case-mapping differences. This restriction does not
change legacy JSON validation. Empty/whitespace-only labels, names and titles
are rejected. Grade normalization reuses `checked_grade`; database grades are
exactly A–F or NULL. NULL means ungraded; F means an actual zero-point grade.

Credits reuse `checked_credits`: 0.0001–1000000 inclusive, at most four decimal
places. The Python field is DecimalField(11,4), but the PostgreSQL column is
unconstrained `numeric` with range and `scale(value) <= 4` CHECK constraints.
A usual numeric(11,4) would silently round 3.00001 to 3.0000 before checking;
this schema rejects it, even in raw SQL/bulk updates. NaN and infinities fail the
range check. It conservatively rejects stored decimals with more than four
fractional places even if those extra places are trailing zeros.

Model saves run `full_clean()` for useful validation errors. Bulk operations and
raw SQL bypass that method, so CHECK/UNIQUE/FK/NOT NULL constraints are essential.
Bulk course inserts must supply the correctly normalized code. If using
`save(update_fields=...)`, include all changed dependent fields, e.g.
`original_code` and `normalized_code`; include `updated_at` to refresh that time.
QuerySet updates/raw SQL do not automatically update timestamps.

## Ownership integrity and remaining security work

An ordinary foreign key only proves that the referenced row exists; it does not
prove that both rows have the same owner. Migration `0002_owner_relationships`
adds immediate, validated composite PostgreSQL foreign keys:

- Course `(semester_id, owner_id)` → Semester `(id, owner_id)`.
- Assignment `(course_id, owner_id)` → Course `(id, owner_id)`.

Supporting unique constraints exist on the referenced pairs. These keys reject
mismatched inserts, owner changes and reparenting through model-bypassing writes.
They are reversible SQL migrations because Django's ordinary single-column
ForeignKey cannot represent this rule. Do not remove them during schema changes.
The test suite checks both actual PostgreSQL metadata and rejected writes.

**Owner isolation is not complete.** These constraints prevent inconsistent links;
they do not restrict who may read or change an otherwise consistent row. There
are no authenticated application endpoints, owner-scoped query services,
authorization tests, PostgreSQL row-level security or reviewed production roles.
Those controls must be designed and verified in Milestone 2B before any multi-user
exposure. UUIDs are identifiers, not access-control tokens. `record_version`
starts at 1 and must stay positive, but automatic increments and transactional
compare-and-swap conflict detection are deferred. `updated_at` is ORM-managed,
not a database audit trail. Account retention/deactivation, privacy policy,
backup/restore, secret rotation, TLS, rate limiting, sessions and deployment
hardening remain unimplemented. No login or registration is added here.

Historical JSON provenance concerns and local JSON single-writer limitations in
`FOUNDATION_REVIEW.md` still apply. No personal JSON is read or migrated here.

## Verification and CI

For tests, privately set PGUSER/PGPASSWORD to the dedicated CREATEDB test role,
PGDATABASE to its scratch database, PGTESTDATABASE to a separate disposable name.

```sh
python -m unittest discover -v
python server/manage.py test accounts academics --settings=config.settings.test -v 2
python server/manage.py makemigrations --check --dry-run
python tools/check_repository_safety.py
python -m pip install -r requirements-dev.txt
python -m pip_audit --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt
```

The first command preserves all 113 original tests, including synthetic Streamlit
interactions. The Django tests require PostgreSQL; there is no SQLite fallback.
They exercise fresh migrations, reverse/reapply academics migrations, live schema
metadata, UUIDs, model validation, exact credits, grades, per-owner uniqueness,
protected deletion and composite ownership constraints. The test database is
created with migrations enabled and destroyed after completion. CI adds a
PostgreSQL 17 service job and audits both dependency locks. Hosted CI status must
be checked separately; local passing tests do not establish hosted success.
