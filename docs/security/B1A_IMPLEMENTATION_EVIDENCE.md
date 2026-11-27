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
plus **4** explicit mutation-control methods (15 controls, see below); these are not
counted as new baseline regressions. Browser baseline stays **27** (10 UI1 +
5 premium-auth + 12 UI2). No historical assertion or test is edited. The L-1 to L-6
hardening changed only B1a test, mutation-control and evidence files; it added no
regression methods, so the regression total remains **455**.

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

### Local acceptance result (original implementation commit `c100f21`)

All suites passed: legacy 113, foundation 33, isolation 46, auth 172, website 91,
website-root B1a/mutation 25, UI1 10, premium-auth 5 and UI2 12. Audit of all three
hashed locks reports no known vulnerabilities; pip check, migration drift,
repository safety, Python/YAML parsing, relative links and whitespace checks pass.

The original local auth-root PBKDF2 observations were 0.268951 s (login recheck,
1 hash), 0.515573 s (password change, 2 hashes), and 0.337611 s (reset confirm,
1 hash). The concurrent website-root run observed 0.414983 s, 0.626651 s and
0.203276 s respectively. Variation is expected; these are observations only.

### Mutation controls (rewritten for L-1)

`tools/b1a_negative_controls.py` mutates **production behaviour only**, never a
test-module name, through two isolated mechanisms:

* **In-memory:** a context-managed patch of a production object, restored on exit,
  with a hit counter proving that the mutated code ran during the target test.
  Database targets run as complete Django `TransactionTestCase`s (setup and flush),
  and connections are closed after every run.
* **Disposable checkout:** `server/` and the top-level shared modules are copied into
  a `TemporaryDirectory`. Each replacement must apply exactly once. The real target
  test then runs in a fresh subprocess whose imports are verified to come from the
  copy. Tracked files are never written, and the copy is discarded afterwards.

A control is **DETECTED** only if all four hold:

1. the same target passes unmutated, through the same mechanism;
2. the mutation was exercised;
3. the mutated run records at least one assertion failure;
4. no infrastructure error occurs.

Anything else prints `B1A_MUTATION_UNDETECTED=<id>` with the evidence, and the
control method fails. A scratch-only self-check (not committed) confirmed that a
behaviour-preserving mutation, an unexercised mutation and a replacement that
does not apply are each reported UNDETECTED, and that an escaped mutation fails
the runner.

| Control | Production change | Target assertion |
| --- | --- | --- |
| `in_memory.options_missing_lock_timeout` | `dbsafety.options_for` drops `lock_timeout` | exact options string |
| `in_memory.timers_leak_to_migrator` | `dbsafety.expected` also configures the migrator `default` | migrator unchanged |
| `in_memory.pgoptions_ignored` | `dbsafety.expected` hides `PGOPTIONS` | PGOPTIONS rejection |
| `in_memory.e101_validation_removed` | `checks.validate_db_safety` is a no-op | E101 reported for missing options |
| `checkout.apply_helper_call_removed` | `auth_common.configure` no longer calls `apply_db_safety` | protected-profile flag and options (subprocesses) |
| `checkout.e101_runs_in_inactive_profiles` | Both E101 gates removed (`apps.py` registration, `checks.py` guard) | no E101 in excluded profiles |
| `checkout.tls_options_overwritten` | `apply_db_safety` replaces the whole `OPTIONS` dict | `sslmode`/`sslrootcert` retained |
| `checkout.float_decimal_silently_coerced` | `integer()` coerces `float`/`Decimal` | type rejection |
| `checkout.conflicting_options_overwritten` | Conflict check removed | conflicting options rejected unchanged |
| `in_memory.same_account_login_cycles_key` | Same-account (SA) login cycles the session key | A1: SA `cycle_key` 0 and key retained |
| `in_memory.flush_keeps_prior_session_row` | `SessionStore.flush` keeps the prior row (cycles instead) | A1: SX/DA 0 rows inside finalizer |
| `in_memory.throttle_write_retried` | The view retries `rate_limit` after a database error | exactly one throttle dispatch |
| `in_memory.commit_hook_without_real_commit` | auth `_commit` raises without committing | real-COMMIT-then-error persists |
| `in_memory.autocommit_writes_rolled_back_with_request` | `ATOMIC_REQUESTS` on `auth` (view really wrapped) | throttle increment persists |
| `real_connection.missing_lock_timeout` | Live auth connection opened without `lock_timeout` | `SHOW lock_timeout` is `0`, not `3s` |

The first fourteen run in three methods that require every control to be DETECTED. The real-connection control is the fourth method.
Local result: **15/15 DETECTED** (PostgreSQL 16.15 cluster; see limitations below);
hosted exact-head results are recorded in the draft PR.

## Independent review findings L-1 to L-6 (test hardening)

The independent review of `c100f21` approved B1a with six Low findings. All six
were resolved in test and evidence files only. No production, settings,
migration, role, grant, workflow or timer value changed.

| Finding | Resolution |
| --- | --- |
| L-1 mutation controls | Rewritten as above: production mutations only, exercise proof, unmutated baselines, explicit DETECTED/UNDETECTED output and a failing runner on any escape. Added helper-call removal, E101 leakage, SA key cycling, flush row retention, throttle retry, fake COMMIT and request-wide transaction controls. |
| L-2 connect timeout | The stalled-handshake test builds its connection from `connections['auth'].get_connection_params()`. It asserts that the configured `connect_timeout`, options and `sslmode` match settings, and overrides only host and port (plus a synthetic password, so the real credential never reaches the listener). Elapsed time is bounded relative to the configured value. |
| L-3 SQLSTATE | L4u, L0 and L1 record each failing auth statement (SQL with placeholders only, never parameters) through a thread-local `execute_wrapper`. They assert exactly one failure, on the nominated statement, with SQLSTATE `55P03`. L0/L1 also use a `got_request_exception` receiver, connected per request and always disconnected, to prove that this exception produced the 500. L4u's `SessionInterrupted` 400 does not emit that signal, so the statement-level capture is its evidence. |
| L-4 deferred COMMIT | Only the real `_commit` is timed (monotonic clock), and it must be at least 0.2 s with the deferred trigger under a 100 ms `statement_timeout`. There is no upper bound. Printed as `B1A_DEFERRED_COMMIT_SECONDS`. |
| L-5 SA expiry | The SA response-save case records expiry before and after. A pre-COMMIT failure must leave it `preserved`. A committed save must never shorten it, and the observed outcome (`renewed` locally) is printed as `B1A_SA_L5U_EXPIRY`. Renewal remains allowed under D-B1-1. No session policy changed. |
| L-6 reliability | The idle test reads the backend PID, waits until just before the configured timeout, then polls `pg_stat_activity` from the migrator connection until the server terminates the backend. The window is bounded to the timeout + 5 s; termination must not come earlier than the timeout − 0.5 s, and the next statement must report `25P03`. PBKDF2 records now separate `hash_calls_under_lock`, `lock_hold_seconds`, `observer_overhead_seconds` and `lock_hold_excluding_observer_seconds`. |

Local verification of the hardened tests: legacy 113, foundation 33, isolation 46, auth
172, website 91 and website-root B1a/mutation 27 all passed. Browsers 10/5/12 passed
(local Chromium 153.0.8010.12). The dependency audit found no known vulnerabilities.
Migration drift, repository safety and whitespace checks passed. Local hardened PBKDF2
observations (auth root): login re-check 0.179358 s (observer 0.001911 s, 1 hash),
password change 0.415752 s (observer 0.001258 s, 2 hashes).

**Local limitations:** the local cluster is PostgreSQL **16.15** and the local
interpreter for database suites is Python 3.13. The PostgreSQL 17-only MAINTAIN test
is skipped locally by design. Hosted CI on the exact head (PostgreSQL 17.11, Python
3.12) is the acceptance evidence, not these local runs.

### PBKDF2 observation

The test uses Django's real PBKDF2 SHA-256 hasher at **1,000,000 iterations**.
The login case commits a fixture-only same-secret/different-salt hash between
initial verification and the actual finalizer lock. A real NOWAIT row-lock
observer proves contention; actual hashing calls under that lock are counted.
The measurement covers lock acquisition through real commit return. Since L-6 the
record separates `hash_calls_under_lock`, `lock_hold_seconds`,
`observer_overhead_seconds` (time spent waiting for the NOWAIT observer that proves
the lock) and `lock_hold_excluding_observer_seconds`. That last figure still includes
thread scheduling and other non-hash work, so it is an upper bound on hashing time,
not a hash benchmark. It is evidence for Stage C tuning,
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
