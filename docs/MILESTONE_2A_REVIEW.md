# Milestone 2A verification

Verified locally on 11 November 2026, from Milestone 1 commit
`b9c9222a9e45a4e942906c43365a9a09376b5982`, on `feature/database-foundation`.

## Result

The separate Django/PostgreSQL model foundation is implemented. No application
endpoints, login/registration, JSON imports, deployment, merge or Milestone 2B
work is included. The existing application modules, all 113 existing tests,
and the Streamlit dependency lock remain unchanged from master.

## Versions and execution

- Python 3.12.14.
- Django 5.2.19 (5.2 LTS), psycopg 3.3.8.
- Actual PostgreSQL 17.11, from the official postgres:17 container image
  `sha256:ff87138949ad9a46f32ff23bd6852b52ce024a13dffe9b4087be98292cdd3b4f`.
- Temporary synthetic database, mapped only to 127.0.0.1:55432, with generated
  ephemeral credentials outside tracked files. No personal JSON was imported.
- No SQLite verification or fallback.

## Checks

- All 113 legacy unittest tests passed with Streamlit installed; no skips.
- All 33 Django tests passed against PostgreSQL. Tests cover settings failing
  closed, UUID/timestamps, model validation, actual grades versus ungraded,
  credit boundaries/scale/nonfinite rejection, normalization and uniqueness,
  owner mismatches including bulk writes and reparenting, missing foreign keys,
  protected deletion, and migration/schema checks.
- Fresh migration application succeeded. Test creation also applied the complete
  migration graph; academics migrations were reversed and reapplied successfully.
- `makemigrations --check --dry-run`: no changes detected.
- `manage.py check`: no issues.
- Hashed runtime dependency installation and `pip check` passed.
- `pip-audit --strict --require-hashes --disable-pip` over both runtime locks:
  no known vulnerabilities found. No advisories were suppressed.
- Repository safety and whitespace checks passed before commit.

The first migrate attempt raced container startup; retry after PostgreSQL was
ready succeeded. Two initial test errors were test expectations: Django rejected
NaN/Infinity before SQL execution. Switching those database checks to raw SQL
verified that PostgreSQL itself also rejects them. No failures remain locally.

CI now includes an actual PostgreSQL 17 service job, the unchanged legacy suite,
and an audit of both locks. The disposable CI service uses loopback-bound trust
authentication with no reusable password; that configuration is strictly for the
isolated runner, not development or production. Local results do not establish
hosted CI success. Check the pushed commit's GitHub Actions run separately.

## Remaining boundaries

Composite foreign keys enforce same-owner links but do not authorize access.
Complete owner isolation, authentication, authorization, owner-scoped queries,
RLS/production privileges, concurrent edit detection, database-managed audit
records, backup/restore and deployment hardening remain deferred. A positive
record_version field is present; it does not yet provide optimistic locking.
Production settings intentionally refuse startup. No public hosting is approved.
See [DATABASE_FOUNDATION.md](DATABASE_FOUNDATION.md) for setup and detailed limits.

The existing Milestone 1 history/provenance concerns remain documented in
[FOUNDATION_REVIEW.md](FOUNDATION_REVIEW.md); this task did not rewrite history.
