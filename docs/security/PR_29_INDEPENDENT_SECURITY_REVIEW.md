# PR #29 independent security review

**Verdict: APPROVE, limited to the pinned authentication fix.** No confirmed authentication bypass, stale-password overwrite, or privilege regression was found. The recommendations below are non-blocking hardening and regression-coverage work, not production/deployment approval.

Reviewed PR: https://github.com/jordandavid1812-creator/university-command-center/pull/29

Head: `bec0a4423f73d4172d366d399fcb3540c7235e84`; base: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`. Review completed 12 November 2026 (Africa/Lagos). Claude's branch was not modified. Original audit/probe commit: `e889a3c` on local `docs/pr29-independent-audit`. This documentation-only publication preserves the report and embeds the executed probes in [PR_29_INDEPENDENT_PROBES.md](PR_29_INDEPENDENT_PROBES.md). A subsequently requested unrelated date-test correction is on `test/fix-overdue-date-assumption`.

## Evidence and findings

### 1. Stale password-hash upgrades: fixed

`server/accounts/backends.py:47` verifies without the automatic Django model-saving setter. Lines 14–32 perform a single `UPDATE` matching both immutable student primary key and the exact previously verified password hash. A successful update changes only the password column; a zero-row update does not mutate the in-memory hash.

On PostgreSQL's tested READ COMMITTED isolation, a competing update waits on the row and rechecks its predicate against the committed row version. Independent probe `test_cas_rechecks_predicate_after_waiting_for_committed_reset` holds the row on a separate connection, observes a real blocker through `pg_blocking_pids`, commits a new password, then confirms the waiting CAS returns false. Only the new password remains valid. This tests actual PostgreSQL locking, not merely sequential mocks. PR tests also interleave the real reset and password-change endpoints before/after password verification.

If the CAS wins first, a later reset/change replaces its hash. If reset/change wins first, CAS cannot replace that new hash. The hash is not treated as a monotonically increasing credential epoch: a reset deliberately reusing the same secret can still accept that secret. No separate epoch/reuse prohibition is introduced by this PR.

### 2. Stale successful verification: rejected before login finalization

`server/accounts/views.py:56–67` locks and reloads the current Student. It rechecks active/verified status and requires either the exact verified hash or a fresh setter-free verification of the submitted password against the current hash. The latter preserves concurrent same-secret upgrades without accepting a different new password.

The independent waiting-login probe forces the SELECT FOR UPDATE to wait behind a credential replacement and confirms the old password receives the generic invalid-login form with no authenticated session. The deactivation probe confirms an account disabled after initial verification is rejected. Supplied tests exercise password reset/change through their real endpoints; the independent SQL replacement probes specifically isolate lock semantics.

Reset (`views.py:121` onward) and password change (`views.py:157` onward in the reviewed head) already use the same auth connection/Student row lock. PasswordChangeForm's old-password auto-upgrade occurs inside that lock. No other production `authenticate`/`auth_login` call site bypassing the finalizer was found. A future login endpoint must preserve this finalization step: `authenticate()` alone is not a race-free authorization capability.

### 3. Low: document the session persistence boundary precisely

Affected: `server/accounts/views.py:51–66`, `docs/AUTHENTICATION.md:147` onward; Django 5.2.19 session middleware `process_response`.

`auth_login()` chooses the session's password-derived authentication hash under the Student lock. It does **not** persist the final authenticated session payload there. On a new anonymous login, key cycling can create an empty session row inside the transaction; middleware writes the authenticated payload after the view's transaction commits. With an existing session, persistence is likewise deferred.

Confirmed independent interleaving: login transaction commits; the real reset endpoint commits a new password; SessionMiddleware then saves the old authentication payload and returns the login redirect/cookie. The obsolete payload exists in `django_session`, but `accounts.principals.session_student()` returns None, and the next protected request redirects and flushes it. Therefore this is **not a usable post-reset session or an authentication bypass**. A login that finalized before the reset can still receive its redirect after the reset.

Recommendation: explicitly describe this distinction and retain the middleware-gap regression. Do not claim that authenticated session persistence occurs atomically under the Student lock, or that no obsolete session row/cookie can ever be emitted after reset. No custom session engine or extra persistence write is required to fix the reviewed security issue.

### 4. Low: locking failures deny access but currently return generic 500

Affected: `server/accounts/views.py:56–66`; existing `server/accounts/middleware.py:13–25`.

Independent probes inject an OperationalError at the Student lock and a failure after Django's login signal; another uses a real PostgreSQL `lock_timeout` while a separate connection holds the Student row. All return 500 and persist no authentication. The post-signal failure rolls back the newly created session row and `last_login`; middleware skips saving authentication on 5xx. No permissive fallback was observed.

The boundary middleware only handles errors in its initial role checks. It does not convert later view/session failures into 503. This general behavior predates the PR; the new locking query adds another place it can occur. No explicit lock/statement timeout is added. A stalled transaction can delay correct-password logins and credential changes for the same account. Wrong passwords do not reach the new row lock. A changed-hash recheck can perform a password hash while holding the lock; bounded input length does not bound database wait time.

Recommendation: before deployment, configure and test transaction/lock/request time budgets and safe generic availability responses, with no retry that restores a failed login. Include commit failure, session-save failure and connection loss. Preserve rollback and the 5xx session-save safeguard. This review proves denial for the tested errors, not every network/commit-failure interleaving.

### 5. Informational: simultaneous logins and role boundaries preserved

Supplied tests run five weak-hash logins and six logins racing a reset. Independent probes additionally verify every session from four simultaneous weak-hash logins remains usable, rather than checking only HTTP 302. Algorithm migration from PBKDF2-SHA1 to PBKDF2-SHA256 also passes.

All new account reads, CAS updates and transaction locks explicitly use `auth`. Session routing remains through `accounts.routing.AuthenticationRouter`. Existing column-level UPDATE(password, last_login, email_verified_at, updated_at) and SELECT privileges support the new SQL and locks; no new grant, migration, role membership or schema ownership is required. Existing restricted-role/security tests pass with distinct actual migrator, auth and runtime LOGIN roles. The author test also observes zero default/migrator queries during login. This is preservation of the existing boundary, not a new guarantee against a compromised auth database credential or a fresh full audit of role-guard completeness.

## Enumeration, timing and denial-of-service assessment

Wrong usernames/passwords retain the existing generic form; missing accounts retain dummy hashing; case-sensitive exact username lookup is unchanged. Stale credentials receive the same invalid-login error as incorrect credentials. No new plaintext credential logging or new account-state response was found.

The new lock path follows successful initial verification. A generic 500 there is principally an availability signal to someone who has already passed that check, not a demonstrated account-enumeration oracle for arbitrary wrong-password guesses. Existing hash-version/eligibility timing distinctions and shared-source throttling remain; this is not proof of constant response time or complete enumeration resistance. The supplied distributed/account-aware throttle proposal is outside this PR. Shared-NAT denial of service and account-aware throttling remain separate security work.

The CAS can commit its legitimate hash upgrade before a later login-finalization failure, as Django hash upgrades could before this PR. It cannot overwrite a newer different hash. Hash upgrades continue to invalidate password-hash-bound sessions/tokens; this patch does not redesign credential epochs or recovery tokens.

## Executed verification

Local environment: Python 3.12.14, Django 5.2.19, PostgreSQL **17.11 (Debian 17.11-1.pgdg13+2)**, READ COMMITTED, disposable loopback-only cluster, synthetic identities. No SQLite. Separate real database LOGIN credentials; web operations do not use the migration role.

| Suite on pristine pinned head | Result |
| --- | --- |
| Legacy unittest suite with Streamlit installed | 113 passed |
| Foundation accounts/academics, separate destructive test DB | 33 passed |
| Restricted-role security | 46 passed |
| Authentication including author's nine new regressions | 85 passed |
| Website | 68 passed, 1 pre-existing calendar-dependent failure |
| Additional independent PostgreSQL probes | 9 passed |

Pinned-head total: **345 passed, 1 failed** across the 346 supplied tests, plus **9 independent passes**. Do not describe the pristine pinned head as locally all green.

The website failure is `web_tests.test_polish.WebsitePolishTests.test_existing_workspace_does_not_repeat_first_time_onboarding`, line 26: it assumes a seeded assignment due 11 November 2026 is not overdue. Once Lagos reaches 12 November it is overdue. The same single test was independently rerun and failed on unchanged base/master `64fe874`. No auth behavior caused it. The user subsequently requested its correction. A separate test-only branch freezes the dashboard clock to the seeded assignment's due date. On a separate detached verification checkout, the pinned head plus that test-only correction passed **all 69 website tests**. Together with the unchanged passing suites, this gives 346 supplied passes with the explicit test overlay, plus nine independent passes. This does not change Claude's branch or production code.

Both lockfiles passed `pip-audit --strict --require-hashes --disable-pip`: no known vulnerabilities reported. The first local audit invocation could not create its default cache in the read-only home directory; rerunning with an explicit writable /tmp cache succeeded.

GitHub Actions at this exact head: [Foundation quality run 43106446577](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43106446577), **success**, all three jobs successful: tests (130810913713), dependency-audit (130810914236), database-tests (130810914294). Workflow config uses `postgres:17` and runs foundation, security, auth and web suites separately. Hosted success predates the local calendar rollover; it does not disprove the reproduced date failure. The independent probes are not in that hosted CI run.

## Independent probe reproduction and missing coverage

Source: the Python block in [PR_29_INDEPENDENT_PROBES.md](PR_29_INDEPENDENT_PROBES.md), originally executed from `tools/review_tests/pr29_independent.py`. Extract it to a private temporary directory as `pr29_independent.py` before running the command below. It imports the implementation under test through the target's manage.py. Supply the documented ephemeral PostgreSQL test variables (`PG*`, `UCC_AUTH_ROLE/PASSWORD`, `UCC_RUNTIME_ROLE/PASSWORD`, `UCC_CONTEXT_SIGNING_KEY`, `DJANGO_SECRET_KEY`), then run from the pinned source checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/absolute/path/to/review/tools/review_tests \
PGTESTDATABASE=test_pr29_independent \
python server/manage.py test pr29_independent --settings=config.settings.auth_test -v 2
```

Use the repository's AuthenticationTestRunner, not a generic test runner: it provisions the real role grants. Never point these destructive test commands at student data or production. The tests are intentionally external to ordinary discovery on the documentation branch; that branch's application code is baseline, not the reviewed implementation.

Suggested additions to the normal auth CI suite, in priority order:

1. The real waiting-CAS and waiting-SELECT probes, plus middleware-after-reset persistence/denial. These pin the essential PostgreSQL and Django lifecycle boundaries.
2. Real lock timeout and post-login failure rollback, then session persistence/commit failures and loss of connection. A stale password must never acquire academic authority on recovery/retry.
3. Usability of every concurrent weak-hash-login session, algorithm migration, and deactivation between verification and lock.
4. An already-authenticated/reused browser session racing reset, plus repeat barrier stress runs. Current probes cover the new anonymous-browser middleware gap; the general password-hash check is shared, but that exact reused-session schedule has not been independently exercised.

No deployment, merge, auth fix, academic calculation change or real-data migration was performed. Approval applies to this SHA only; re-review after rebasing/integrating the separate S0-02 implementation, especially session/device side effects, signals and lock ordering.

Publication note: master is now `8295fbd` and includes PR #30's separate date-test correction. Historical results above remain specifically for reviewed head `bec0a44`. No authentication changes are included in this PR.
