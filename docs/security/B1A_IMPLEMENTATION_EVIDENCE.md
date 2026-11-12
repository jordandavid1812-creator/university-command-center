# B1a implementation and independent-review handoff

## Authority and scope

Source baseline: master `2d811ab31b811fb5652dc4c9142a559e738ad6d0`.
Specification: PR #50 `7d8b2ceb4b4f535dc811bc79362b540ccb2693b8`,
`docs/security/B1A_POST_MERGE_READINESS.md`. That draft is not merged or edited.
The owner's subsequent explicit implementation instruction approves D-B1-1,
D-B1-2, D-B1-3, D-B1-5 within the proposal's limits, and cleanup option 1.
Its historical pending labels do not supersede that later authorization.
D-B1-4 and D-B1-6 remain later decisions before B1b and B1c respectively.

This increment adds only connection-option validation/application, protected
profile wiring, flag-gated E101, documentation and tests. No authentication view,
backend, session implementation, throttle/device policy, model, migration, grant,
role, academic calculation, template or CSS is changed. No deployment or persistent
migration is performed. Trusted devices remain dormant. B1b–B1d are not implemented.

## Implementation contract

`accounts.dbsafety` validates integers, bounds and each alias's lock/statement
relationship before copying/mutating settings. The ordered options are:

```text
auth:    -c lock_timeout=3000 -c statement_timeout=5000 -c idle_in_transaction_session_timeout=15000
runtime: -c lock_timeout=3000 -c statement_timeout=10000 -c idle_in_transaction_session_timeout=15000
connect_timeout=5
```

Protected profiles opt in through `auth_common.configure`; existing TLS and
unrelated options survive. Test migrator/default and inactive/offline profiles
remain excluded. Conflicting options/connect timeout and presence of `PGOPTIONS`
fail configuration. Identical reapplication is accepted. `AccountsConfig` keeps
name and label `accounts`; it imports the check only with the helper's explicit
flag. E101 is also flag-gated when already registered. It opens no DB connection.
Fresh subprocesses cover six protected and five excluded profiles. The real
`check --deploy` command on a deliberately broken `web_secure` derivative must
report E101; other deployment warnings are permitted.

See [authentication operations](../AUTHENTICATION.md#b1a-protected-application-connection-timeouts)
for environment names, bounds and connection recycling/rollback requirements.

## Reproduction

Use Python 3.12 and all three existing hash-locked requirements files. The existing
workflow provisions a disposable PostgreSQL 17 service and creates distinct
non-superuser migrator, auth and runtime LOGIN roles with ephemeral secrets.
For local execution use an equivalent disposable cluster and private environment;
never reuse production credentials or weaken role guards. Do not publish the
environment file or captured request data.

```sh
python -m unittest discover -v
python server/manage.py test accounts academics --settings=config.settings.test -v2
python tools/prepare_security_test_roles.py
# For the remaining DB commands use the fixture migrator login and scratch DB;
# set UCC_AUTH_ROLE/UCC_RUNTIME_ROLE and their separate ephemeral passwords.
python server/manage.py test security_tests --settings=config.settings.security_test -v2
python server/manage.py test auth_tests --settings=config.settings.auth_test -v2
python server/manage.py test web_tests --settings=config.settings.web_test -v2
PYTHONPATH=tools python server/manage.py test auth_tests.test_b1_settings auth_tests.test_b1_database auth_tests.test_b1_sessions auth_tests.test_b1_measurements b1a_negative_controls --settings=config.settings.web_test -v2
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py -v
python -m pip_audit --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt -r requirements-browser-test-lock.txt
python -m pip check
python server/manage.py makemigrations --check --dry-run --settings=config.settings.auth_migration
python tools/check_repository_safety.py
git diff --check
```

Use separate test database names for concurrent suites. The existing role
preparation tool requires its documented disposable-cluster opt-in and a setup
administrator; that administrator is never an application request alias. Browser
suite fixtures are synthetic and remain separate from PostgreSQL security evidence.

## Test evidence and oracles

Local environment: PostgreSQL **17.11** (`server_version_num=170011`), Python
**3.12.14**, Django **5.2.19**, psycopg **3.3.8**; Chromium **158.0.8127.18**,
Playwright **1.65.0**. No SQLite substitute is used for database assertions.

The preserved 432 baseline comprises 113 legacy, 33 foundation, 46 isolation,
149 auth and 91 website methods. B1a adds **23** ordinary auth methods (5 settings,
10 database, 7 session, 1 measurement), bringing discovery to **455** regressions:
113 + 33 + 46 + 172 + 91. The 23 B1a methods also run under the website URL root,
plus **2** explicit mutation methods; these duplicates are not counted as new
baseline regressions. Browser baseline stays **27** (10 UI1 + 5 premium-auth +
12 UI2). No historical assertion or test is edited.

| Contract | Reproducible evidence |
| --- | --- |
| E: configuration | Integer/type/range/cross-alias negatives; fixed options; TLS retention; idempotence; PGOPTIONS/conflict rejection; protected/excluded subprocesses and real check commands; E101 specifically |
| E: actual timers | Fresh/reused/direct SHOW; excluded migrator SHOW; restricted-role 57014 statement failures on both application roles; 25P03 idle termination and reconnect; stalled single-address handshake |
| Cleanup | Real auth 55P03; actual blocker observed with `pg_blocking_pids`; failed delete leaves data unchanged; failure propagates without success output; existing auth/runtime privilege guards still pass; unlocked cleanup succeeds |
| H: unit persistence | Real throttle and old-hash CAS remain committed after finalizer lock timeout without `_commit`; failed throttle leaves count unchanged with exactly one dispatch; injected post-execute acknowledgement loss leaves one persisted increment |
| H: COMMIT | Explicit pre-COMMIT failure rolls back; real `_commit` followed by injected acknowledgement failure persists as observed through a fresh auth connection; real deferred trigger shows statement_timeout is not a COMMIT deadline |
| A1 | N/AN cycle once; SA/SX/DA do not; SA keeps its key; SX/DA have no row inside finalizer and INSERT during response, N/AN/SA UPDATE |
| Nominated A2 | L0/L1 actual locks for all five starting states; L4u real session-row lock; L4i exists/INSERT faults; L5u/L5i pre-COMMIT versus real-COMMIT-then-error; 400 UPDATE / 500 INSERT status preserved; prior keys/expiry/rows inspected; no newly issued authenticated cookie |
| A5 C0 | Real password-change Student lock timeout leaves old password and server session valid; no new authenticated-cookie delivery |
| Existing retry | Actual session-key collision performs Django's two INSERT attempts; no new retry code introduced |
| F | Existing password races, CSRF, grants/MAINTAIN, RLS, ownership, math, query budgets and device dormancy suites remain unchanged; all three existing browsers and dependency audit |

Cleanup tests do **not** promise whole-command atomicity: prior completed DELETEs
can survive a later failed delete call. Likewise prior SA authority may remain or
renew, rolled-back DA switches preserve A, and committed response saves can leave
undelivered authenticated rows. An error status does not prove rollback.

### Local acceptance result

All suites passed: legacy 113, foundation 33, isolation 46, auth 172, website 91,
website-root B1a/mutation 25, UI1 10, premium-auth 5 and UI2 12. Audit of all three
hashed locks reports no known vulnerabilities; pip check, migration drift,
repository safety, Python/YAML parsing, relative links and whitespace checks pass.

The final local auth-root PBKDF2 observations were 0.268951 s (login recheck,
1 hash), 0.515573 s (password change, 2 hashes), and 0.337611 s (reset confirm,
1 hash). The concurrent website-root run observed 0.414983 s, 0.626651 s and
0.203276 s respectively. Variation is expected; these are observations only.
Hosted exact-head evidence is linked in the draft PR, separately from local runs.

### Mutation controls

`tools/b1a_negative_controls.py` explicitly requires assertion failures, not
infrastructure exceptions. It mutates missing lock options, migrator timer
leakage, overwritten TLS, disabled input validation, overwritten conflicting
options, ignored PGOPTIONS and disabled E101. A separate real-connection mutant
removes the auth lock option and observes `SHOW lock_timeout=0`, proving the
normal `3s` assertion fails. Restores/connection closure run in `finally`.
Ordinary lifecycle/persistence assertions also discriminate incorrect key/row,
rollback and retry assumptions. These controls do not modify tracked source or
relax a historical test. They do not simulate arbitrary network failures.

### PBKDF2 observation

The test uses Django's real PBKDF2 SHA-256 hasher at **1,000,000 iterations**.
The login case commits a fixture-only same-secret/different-salt hash between
initial verification and the actual finalizer lock. A real NOWAIT row-lock
observer proves contention; actual hashing calls under that lock are counted.
The measurement covers lock acquisition through real commit return, including
observer coordination and machine scheduling. It is evidence for Stage C tuning,
not a timing threshold or production SLA. Aggregate observations are emitted as
`B1A_PBKDF2_LOCK_MEASUREMENTS` in local/hosted test logs without account identifiers,
passwords, hashes, tokens, session keys, addresses or request paths.

Final local/hosted results and measurement values are recorded in the draft PR
handoff at its exact head; CI logs are authoritative for that run, not historical
PR #49 or a different source head.

## Failures investigated and remaining risks

Early new-test failures were fixture/import issues: settings-only labels did not
request the aliases needed by the existing runner; subprocesses needed the repo
import path; the old-hash fixture needed PBKDF2 enabled; session-matrix fixtures
reused one throttle source too often; and an overly broad SELECT fault hit role
checks rather than response persistence. These were corrected in new test code.
The assertions were retained, faults narrowed to their nominated phases, and
production authentication/session logic was not changed. A local audit repeat hit the
sandbox's read-only default cache; rerunning with an explicit private writable
`--cache-dir` fixes the environment issue without changing audit scope. Failed preliminary runs
are not represented as passing acceptance.

- Timers are availability protections, not authorization or guaranteed request,
  DNS, HTTP or COMMIT deadlines. Arbitrary external clients are outside this helper.
- Existing Django 400/500 and role-boundary 503 responses remain; classification,
  privacy-safe logging, renderer fallback and full failure routing await B1b–B1d.
  Existing logging is not claimed safe for public staging.
- Cleanup can partially complete across separate statements. Investigate failures;
  never retry security writes automatically or infer global rollback.
- PBKDF2/scheduling observations require later Stage C tuning and proxy/worker,
  TLS, pool/connection and provider compatibility evidence.
- No new role grants, migrations, recovery/email infrastructure, backups, staging,
  trusted-device enforcement or real-data acceptance is established here.
- Stop for independent Claude review of exact implementation and hosted evidence.
  Do not merge either PR #50 or this PR, deploy, or begin B1b without its own gate.
