# Milestone 3 implementation and verification report

Starting master: `35aeb45432c8bff6ff00abb572d32f03bce2212d` (PR #21 verified merged).
Branch: `feature/student-authentication`. Verification date: 11 November 2026.
No deployment, automatic merge or Milestone 4 work is included.

## Architecture and account/session design

Application settings contain an academic runtime default connection and a distinct
restricted authentication connection, with no migration/DBA credentials. Account
and Django session queries route to auth; academic operations use existing services,
forced PostgreSQL RLS and signed transaction/backend context unchanged. Runtime
retains no account/session/private key access. The auth role has no academic/private
key access, ownership, bypass or schema privileges. Offline provisioning grants
only needed tables/columns. Middleware rejects unsafe/shared-role configurations.

Registration uses case-sensitive ASCII usernames, normalized unique ASCII email,
Django password validation/PBKDF2 (12–128 characters), confirmation and required
email verification. Existing internal accounts remain unverified with nullable
email; no identity/profile values were invented or JSON imported. New models store
only digests for expiring email/reset secrets and atomic HMAC-keyed throttle counts.
Django's standard signed database sessions, authentication hash and key rotation
handle browser sessions; no custom password hash or cookie protocol was introduced.

The hardened capability factory accepts verified live-session principals, not
Student instances or is_authenticated flags. Session signature/expiry, configured
backend, password-derived hash, active status and verified email are rechecked.
Capabilities bind the owner to that session/hash and expire in five minutes; they
are not sent to clients. The old 2B fixture adapter exists only in explicit non-web
security-test settings; auth profiles disable it and refuse web requests if enabled.

## Implemented flows

- Registration, duplicate detection with generic confirmation, password validation
  and CSRF; verification confirmation and resend with 24-hour one-use links.
- Generic login failures, session fixation protection, fixed safe redirect, POST
  logout, browser-session HttpOnly/SameSite=Lax cookies and 30-minute server expiry.
  Secure cookie defaults exist in auth_secure; local HTTP development alone disables
  Secure. The separate production deployment profile still refuses startup.
- Generic reset requests for active verified accounts; one-hour one-use reset links,
  secure password change, invalidation of old sessions/capabilities and handling of
  expired/replayed/invalid links. Email change is not supported or granted.
- Transactional token issuance/consumption with account-before-token lock order,
  email/password binding, rollback and post-commit email delivery. No real emails
  sent in testing. Local console mail and in-memory test backends only.
- Shared PostgreSQL fixed-window IP limits with Retry-After; socket address only,
  not untrusted forwarding headers. Cleanup for expired counters/tokens/sessions.
- Minimal protected academic list, own-course grade edit and own-assignment delete,
  all using the existing services/version checks. Foreign/missing UUIDs share 404;
  request owner fields are rejected and raw SQL/errors/signing material are hidden.

## Verification results

Actual versions: Python 3.12.14, Django 5.2.19 LTS, psycopg 3.3.8 and PostgreSQL
17.11. All database tests used real PostgreSQL, separate LOGIN credentials and
synthetic example.invalid accounts. Local database connections used SCRAM password
authentication. No SQLite result is used to claim PostgreSQL security.

| Suite | Result |
| --- | --- |
| Legacy CLI/Streamlit/academic/storage tests | 113/113 passed, unchanged, no skips |
| Original Milestone 2A database tests | 33/33 passed, unchanged |
| Original Milestone 2B security tests | 46/46 passed, unchanged |
| New authentication and integration tests | 63/63 passed |
| Total distinct automated tests | **255 passed** |

The auth suite also passed through the exact extended CI role-bootstrap helper
using NEW dedicated migrator/runtime/auth roles and a fresh test database. The test
migrator is non-superuser/NOBYPASSRLS with CREATEDB only for disposable tests;
application roles never get that privilege. Web requests were verified to query
zero times through the privileged test-only migration connection.

The 63 tests cover registration/duplicates/passwords, verified/active login, email
verification expiry/reuse/resend, reset/password changes, session expiry/fixation/
revocation, CSRF tokens and hostile/null origins, forged model/session/principal
attacks, direct service invocation, cross-student read/update/delete, role denials,
shared/concurrent rate limits, simultaneous token consumption with exactly one
winner, rollback, multiple concurrent student sessions, owner context cleanup,
stored-text escaping, safe redirects/email origin and account migration reversal
without weakening RLS. Existing database constraints and all original RLS tests pass.

A REAL Chromium 156.0.8078.79 smoke test passed registration, CSRF forms, verification,
login, protected records, grade editing, reset, re-login and logout, with no page
errors. It ran only on 127.0.0.1 with restricted application credentials, in-memory
email, synthetic records and no migration credential in the web process. Playwright
1.65.0 was a local QA tool only; no runtime requirement/lock was added for it.

Chromium exposed a no-referrer/Origin:null interaction rejected by Django CSRF.
The final same-origin referrer policy suppresses cross-origin referrers while keeping
Django origin/referer checks functional. A regression test verifies hostile/null
origins still fail and same-origin form submissions succeed. CSRF was not relaxed.
The browser driver initially hit workspace capacity; only earlier task-owned caches
and stopped synthetic containers were removed, and the driver install/smoke passed.
No application requirement remains blocked by that environment issue.

Fresh migrations, reversal/reapplication, no-drift checks, Django system checks,
compile/whitespace checks, pip check and repository safety passed. Both existing
hashed runtime locks passed strict pip-audit with no known vulnerabilities and no
suppressions. No new application dependency or runtime lock change was required.
CI now runs the auth suite alongside all historical suites and both lock audits,
with generated/masked ephemeral credentials. Hosted status must be read from the
pushed commit/PR; local passing results alone do not establish hosted CI success.

## Remaining risks and scope limits

This is a local authentication foundation, not production approval. Public HTTPS,
proxy/cookie policy, independent security review, secret rotation, transactional mail
sender/queue/retry/bounce controls, distributed anti-abuse, external-pool/load tests,
backup/restore, durable audit history and account lifecycle operations still need
review. IP limits are bounded per source, shared NAT users share limits and many-IP
attackers can evade them. Schedule expired artifact cleanup before long-lived use.

Auth DB compromise can expose account hashes/sessions or permit account attacks;
stolen valid sessions/email links, compromised inboxes/endpoints and arbitrary
trusted Python/migrator/DBA access are outside this tested request-isolation boundary.
Signed sessions are not encrypted. Redact token URLs/SQL parameters and never retain
console email links or secrets in shared logs. Already-authorized in-flight operations
can finish during concurrent logout/credential revocation; later calls revalidate.

CLI/Streamlit remain local single-user JSON apps, unchanged. No personal JSON was
read/imported/modified, GPA formulas were not changed, no public server was deployed,
no social login/payments/email-change workflow or full dashboard was added.

See [AUTHENTICATION.md](AUTHENTICATION.md) for setup, complete privileges, routing,
trusted principal flow, sessions, transaction boundaries and future mail requirements.
