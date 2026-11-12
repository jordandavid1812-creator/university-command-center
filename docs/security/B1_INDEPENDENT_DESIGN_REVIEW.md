# Independent B1 security design review — PR #36

**Verdict: REQUEST CHANGES before approving implementation.** Bounded waits, no automatic retry, explicit uncertain-COMMIT handling and preservation of separate roles are sound objectives. Section 6 nevertheless relies on several false framework/database guarantees and specifies tests that the proposed implementation cannot satisfy. These are findings about the plan and existing behavior, **not newly introduced B1 application vulnerabilities**: B1 is not implemented.

Reviewed document: [STAGE_B_IMPLEMENTATION_PLAN.md at 7f438b16f6ed92f5e1714a87396044af76afb20b](https://github.com/jordandavid1812-creator/university-command-center/blob/7f438b16f6ed92f5e1714a87396044af76afb20b/docs/security/STAGE_B_IMPLEMENTATION_PLAN.md), especially lines 176–355. [PR #36](https://github.com/jordandavid1812-creator/university-command-center/pull/36) remains unchanged. Review date: 12 November 2026 (Africa/Lagos).

Runtime inspected: Python 3.12.14, Django **5.2.19**, psycopg **3.3.8**, PostgreSQL **17.11 (Debian 17.11-1.pgdg13+2)**. Fourteen independent probes ran against the existing post-PR29 authentication implementation, plus a standalone native-psycopg COMMIT experiment. All assertions observing the behaviors below passed. No SQLite, real student data, B1 implementation, security-branch modification or branch integration was used.

## Findings ranked by severity

### B1-01 — High: session-update database errors bypass the proposed handler500 boundary

**Plan:** lines 217, 227–241, 292–296, 329 and 351. **Affected framework:** Django `contrib/sessions/backends/db.py:114–137`, `contrib/sessions/middleware.py:58–65`, `core/handlers/exception.py:96–112`.

A normal response-phase session UPDATE calls `SessionStore.save(must_create=False)`. It converts **any DatabaseError**, not merely concurrent logout, into `UpdateError`. SessionMiddleware converts that into `SessionInterrupted`, a BadRequest. Django sends it through **handler400**, never handler500 or view process_exception.

**Reproduced on PG17:** hold the existing session row on a separate connection, set auth `lock_timeout=100ms`, then perform a same-account login. The actual UPDATE times out; response is **400** and the observer handler500 is called **zero times**. The exception chain is:

```text
SessionInterrupted
  __context__ → UpdateError
    __context__ → django.db.OperationalError
      __cause__ → psycopg.errors.LockNotAvailable (55P03)
```

The proposed single-hop `exc.__cause__.sqlstate` misses this chain. Classifying all SessionInterrupted instances as outages would also be wrong: a genuine concurrent session deletion is an existing expected 400.

**Required correction:** specify a boundary that actually sees database-origin session-save failures, including this 400 path, before promising 503. Retain distinct handling of true concurrent logout. Define a bounded/cycle-safe cause/context traversal with precedence for an explicit cause, then context, and SQLSTATE before generic exception-class fallback. Test nested/suppressed causes, wrapper-only errors, driver SQLSTATE and no-SQLSTATE connection loss. Do not indiscriminately reclassify all BadRequest/400 responses or infer a database outage from an arbitrary nested unrelated exception.

### B1-02 — High: 5xx does not guarantee no valid session row, no existing access, or no expiry extension

**Plan:** lines 180, 209, 238–243, A1–A3 at 311–313, P4 tests at 329–330, acceptance at 350. **Affected code:** PR29 `accounts/views.py:56–66`; Django session middleware/backends above; `accounts/principals.py:21–33`.

The skip-save rule applies when middleware is **given a 5xx before saving**. It does not undo a session write already committed while processing an initially successful response, invalidate a previously authenticated cookie, or retract headers already delivered.

**Reproduced:**

- New anonymous login: let the real response-phase session save commit, then simulate lost acknowledgement by raising OperationalError. Final response is 500 and no cookie is returned, **but one live session row contains valid authentication**. This refutes universal A3. Its new random key is not delivered by this test; this observation alone is **not an anonymous authentication bypass**.
- Previously authenticated same-account browser: use its known key, shorten the stored expiry, let the real session UPDATE commit, then raise the same acknowledgement fault. Response is 500 with no new session cookie, **the old key remains usable and expiry is extended**. A1/A2 and the objective “cannot ... extend access” are false for this case. No stolen/forged key was used; this demonstrates retention/extension of prior authority, not new cross-account authority.

`test_response_write_failure_after_commit` additionally conflates no response with no headers delivered. A client may receive Set-Cookie before the body/write fails. WSGI/socket write failures after header handoff are outside Django's handler500 lifecycle. That protocol limitation is not tested by simply discarding a response. No live packet-loss/partial-header experiment was performed in this review.

**Required correction:** define separate cases for an initially anonymous browser, a known anonymous key that is rotated, an already authenticated same-account key, and a different-account existing session. Separate failure before session write, during its COMMIT, after session commit and after header delivery. State allowed orphan rows/known-key access explicitly. If B1 must prohibit any renewal or require revocation of pre-existing access, approve the necessary login/session policy change and test it; process_exception plus handler500 alone cannot provide that contract. Otherwise narrow B1 to precise pre-header/no-new-authority guarantees, retain honest uncertain outcomes and move stronger finalization work to B2. Do not silently weaken the stated objective by changing failing assertions alone.

### B1-03 — High: statement_timeout does not reliably bound COMMIT; the Stage C timeout budget is unsupported

**Plan:** line 265 (“including COMMIT”), lines 180 and 284; 3/5–10/15-second candidates and proposed Gunicorn ≥30 seconds.

**Standalone PG17 reproduction with actual startup options:** connect using `options='-c statement_timeout=100ms'`; SHOW confirms 100ms. A control SELECT pg_sleep(0.35) raises **57014 at approximately 105ms**. Install a synthetic temporary table and DEFERRABLE INITIALLY DEFERRED constraint trigger calling pg_sleep(0.35), insert a row and call native **psycopg Connection.commit()**. It succeeds after approximately **353ms**, and the row is committed. This independently refutes the claimed COMMIT bound. It does not imply every possible COMMIT wait behaves identically; it proves the proposed bound is not universal.

Server query/lock/idle timeouts also do not sum to a request deadline or bound every network wait. Installed psycopg's `conninfo.timeout_from_conninfo({})` returns **130 seconds**, before considering multiple connection attempts; B1 proposes no explicit connect_timeout. Multiple statements/aliases, hashing, rollback, callbacks and transport waits can exceed the proposed worker limit. `idle_in_transaction_session_timeout` is an idle-session killer, not a total transaction/runtime timer. A 504 or killed worker cannot be ruled out by setting proxy timeout to worker+5 seconds.

**Required correction:** remove the universal COMMIT/request-bound claim. Specify exactly which waits B1 bounds and which remain transport/worker/uncertain-COMMIT hazards. Include explicit connection-budget policy, multi-statement worst-case analysis and separately agreed Stage C request/worker/proxy deadlines; do not confirm 30/35 seconds from per-statement values alone. Keep uncertain-outcome safety even when a worker/socket is lost. Add the deferred-trigger COMMIT experiment and simulated long/multiple connection attempts to the acceptance evidence. Any broader cancellation/transaction-timeout design requires its own PostgreSQL 17 behavior and privilege review; do not add one by assumption here.

### B1-04 — Medium: failed password change does not always reach flush or delete the browser cookie

**Plan:** lines 208, 239 and 324. **Source:** PR29 `accounts/views.py:156–162`; Django `contrib/sessions/backends/base.py:177–190,412–419`.

**Reproduced:** an injected failure at Student SELECT FOR UPDATE occurs before auth_logout/flush; 500 has no deletion cookie, the old session remains valid and the follow-up password-change page returns 200. Another probe fails session DELETE inside flush. clear() has run, but `_session_key=None` has **not** run; `is_empty()` is false because the key remains. The transaction rolls back the password write, and again no deletion cookie is emitted and the original session is valid. Merely converting these errors to 503 does not change that outcome.

**Required correction:** split pre-flush, during-delete, post-flush/pre-COMMIT and uncertain-COMMIT cases. Decide whether failure should preserve prior access or explicitly expire the browser cookie. If logout-on-any-change-failure is required, it is a deliberate response/session policy that must be specified, not claimed as Django's automatic behavior. Browser cookie deletion is also different from server-side revocation of copies and is not possible if no response is received. Reconcile this with A1/A2 and the stated unchanged-view scope.

### B1-05 — Medium: the shared error renderer is unavailable in historical auth profiles and is too dependent on request context

**Plan:** lines 230 and 292–297. **Source:** `student_web/views.py:18–21,275–276`, `student_web/templates/student_web/error.html`, `accounts/templates/accounts/base.html`, `config/settings/auth_common.py`, `config/auth_urls.py`.

**Reproduced:** calling the existing student_web.views.server_error under auth_test raises **TemplateDoesNotExist**. Historical auth profiles do not install student_web or search its templates. Adding only its handler500 URL declaration does not make that template available. Its template also reverses student_web:dashboard, a namespace absent from the auth-only URLconf. In web profiles, shared layouts/context can evaluate request.user, messages and navigation and issue more DB work during an outage; this is a source-level hazard, not separately reproduced as a recursive failure here.

**Required correction:** specify a minimal auth-available, DB-independent error response and a tested last-resort plain response. Do not depend on lazy users, sessions/messages, dashboard URLs or failing context processors. Exercise handler500, handler400-origin database errors, response-phase failures, auth-only and full web roots with DEBUG false/DEBUG_PROPAGATE_EXCEPTIONS false. Preserve generic content, no-store and Retry-After policy even when rendering fails. Do not fix this by installing the entire student website into historical auth settings without a separate scope decision.

### B1-06 — Medium: universal A4/A5 and the fault matrix do not define valid per-flow states

**Plan:** lines 309–335 and 350–354.

A1/A2 fail for pre-existing sessions as above; A3 fails on acknowledged-lost session commits. A4 (“exactly one old/new password”) needs **distinct submitted secrets** and a password-changing flow. Existing forms allow a reset to the same plaintext secret: an independent real reset succeeds, consumes the token and leaves that secret valid, so old/new labels cannot be asserted exclusive. Verification is not a password replacement. A5 must refer to the nominated active redemption token and a before/after snapshot, not all tokens: token issuance currently marks older tokens consumed for revocation without changing the password. Login has no redemption token at all.

Verify-confirm needs its own explicit lock/statement/idle/before-COMMIT/after-COMMIT matrix; the proposed named tests mostly cover login/reset/change. Email issuance has an on_commit callback; reset/verify/change redemption does not. “No email hook ran” is meaningful at issuance, not a common assertion for all routes. A4 token/password checks must wait for any controlled concurrent transaction and use a clean connection, not the aborted auth connection.

**Required correction:** replace “A1–A6 after every failure” with a flow × phase × initial-cookie-state matrix. Specify allowed committed/rolled-back pairs per reset, verify, change and issuance, and separate pre-existing session policy from newly delivered authority. Preserve same-secret reset behavior unless the owner separately approves changing it. Before-COMMIT failure injection must explicitly raise a realistic failure after terminating the native connection; simply closing a Django wrapper and invoking its now-no-op _commit is not evidence of a raised commit error. Add SQLSTATE/response/header assertions through the full stack, not only a pure classifier unit test.

### B1-07 — Medium: generic bodies/custom SQLSTATE-only events do not sanitize Django's error logs

**Plan:** lines 221–225, 335 and 352. **Source:** Django `core/handlers/exception.py:139–151`, `utils/log.py:log_response`, repository error handlers.

**Reproduced:** a synthetic reset-confirm failure produces a django.request LogRecord containing the **reset secret in request.path** and the exception's private-detail sentinel via exc_info. Only booleans are retained in the review output; no real tokens were used. A custom handler500 returning 503 does not prevent Django from constructing the subsequent log record with the originating exception. A view exception consumed by process_exception can still produce path-bearing status logs. This probe proves record contents, not external delivery or retention under an unconfigured logging sink.

**Required correction:** state whether the promise applies to new dbsafety events only or to the entire error path. Before claiming sanitized failures, include Django/proxy/server logging and a minimal redaction/suppression boundary with tests for path tokens, queries, exception text/tracebacks, request/body/header/cookie data and admin-email handlers. Do not call logger.exception or export raw LogRecords while deferring all privacy to B3/Stage D. Keep broader event taxonomy/retention out of B1 if necessary, but make that limitation explicit and prevent new sensitive output.

### B1-08 — Medium: classification coverage is inconsistent with unchanged existing handlers

**Plan:** P0 at 186, classification table at 219–225, “not changed” at 301, acceptance 351–354. **Source:** `accounts/middleware.py:13–25`, `accounts/tokens.py:44–53`, academic error wrappers.

The existing role middleware catches all DatabaseError, including programming errors, and returns 503 before the new process_exception hook can see them. Existing registration treats a handled IntegrityError as generic success. Academic wrappers already turn database exceptions into 503. These intentional pre-existing paths contradict unconditional “defects stay 500” / “no status below 500 on any database failure path” unless the contract is explicitly limited to unexpected, unhandled authentication exceptions. The plan already acknowledges handled IntegrityError in one table but not its universal acceptance criterion.

**Required correction:** enumerate classification precedence and exceptions by stage, preserving or deliberately changing each existing contract. Add P0 role-check/no-connection/privilege/programming-error tests and handler-consumed expected-constraint cases. SQLSTATE unit mappings alone do not verify end-to-end status behavior. Treat a bare OperationalError with no diagnostic state as an ambiguous operational symptom; it cannot prove the cause is transient rather than credentials/TLS/configuration. Add class 28/invalid-database diagnostics to the policy or explicitly document their conservative fallback.

## Handler500 inspection: what is correct

The proposed sys.exc_info approach is **not inherently broken** on the reviewed stack. Django's normal synchronous exception conversion calls handler500 while the original exception is active; the independent observer saw the expected OperationalError and its psycopg 55P03 cause. The async adapter probe also preserves the original exception: installed asgiref.SyncToAsync.thread_handler re-raises supplied exception information before running the callback. No blanket claim that async necessarily loses sys.exc_info is justified here.

That is conditional evidence, not a public handler500 exception argument/API guarantee: DEBUG or DEBUG_PROPAGATE_EXCEPTIONS bypasses the normal handler, direct/manual invocation can have no active exception, a handler/signal/rendering failure can replace it, 400 conversion follows another path, and a post-header server write is outside it. Specify a conservative no-exception fallback and lock down the tested WSGI/full-stack path. A process_exception-only middleware after SessionMiddleware correctly receives view exceptions before response processing; its position does **not** make it catch SessionMiddleware.process_response exceptions.

## Transaction/uncertain-COMMIT model: retain these correct parts

Reset password + nominated token consumption, and verification + nominated token consumption, are in single auth transactions. Password change + current-session DELETE is atomic when flush is reached. Under the tested reset `_commit` hook, the real server commit completes then an injected OperationalError is raised: **new password remains valid, old is invalid and token is consumed**, despite the 500 response. Django's subsequent rollback attempt cannot undo that completed commit. The plan correctly avoids automatic replay of uncertain security writes.

A separate real token-issuance COMMIT followed by acknowledgement fault leaves the token stored but sends **zero on_commit email** in this stack; Django's commit-success bookkeeping/hook execution occurs after _commit returns. Do not generalize that to failures that happen after a successfully returned commit and already-run callbacks. A token committed without delivered mail can also revoke earlier links under current semantics; “harmless” is too strong as an availability claim. Preserve the B7 recovery dependency.

The phase taxonomy must be applied **per transaction/write**, including autocommit throttle/CAS/session statements, not as a promise that the entire request rolled back. Earlier throttle increments or a legitimate hash upgrade can persist before finalization fails. A network loss does not necessarily terminate the server transaction immediately; distinguish known server cancellation/rollback from timeout while the outcome is still in flight. Do not inspect ambiguous state through a broken connection or emit success based on a speculative read.

## Timeout/alias and Stage C compatibility

The proposed application-only composition point and merging of OPTIONS are appropriate for PR #35's direct-connection local architecture. Preserve sslmode=verify-full, CA root and all unrelated libpq options on **both** actual app aliases. In operational profiles these are auth + STUDENT_DB_ALIAS=default; in restricted-role tests auth + runtime. Never apply helper defaults to offline auth_migration or test-provisioning default. Test duplicate/conflicting startup options and idempotent application so an appended override cannot silently set a timeout to zero while a string-presence check passes.

A registered Django system check is not automatically executed by Gunicorn/get_wsgi_application. Stage C must explicitly run the check in its startup/preflight gate (or add separately specified settings validation). Combine structural validation with effective SHOW on actual connections. “No B1 override on migrator” is the primary exclusion assertion; SHOW=0 is valid for the controlled fixture but should not cause a future implementation to erase an operator's existing offline-role timeout policy.

Keep pooling out of B1. “PgBouncer drops options” is overbroad: version/configuration may reject or explicitly ignore unsupported startup parameters. A connection_created SET on a transaction-pooled client connection does **not** by itself pin settings to every subsequently borrowed backend. Do not present that as an approved fallback; pooled endpoint/role-default/SET LOCAL design needs a separate review. Current direct connections with CONN_MAX_AGE=0 are the appropriate limited target.

Neither the proposed Gunicorn/Caddy deadlines nor complete rollback-before-504 can be approved from the supplied timing arithmetic. Stage C implementation remains separately unauthorized; the corrected B1 contract should be a shared prerequisite for its deadline/failure tests, not an assumption that a local lab already exists.

## Required revised acceptance matrix before implementation approval

| Area | Required cases / evidence |
| --- | --- |
| Exception routing | Real 55P03/57014 session UPDATE through SessionStore → SessionInterrupted → 400 boundary; true concurrent logout remains distinct; nested cause/context and no-SQLSTATE loss |
| Originating exceptions | DEBUG false sync view, sync middleware request/response, handler observer, no-active-exception fallback, auth-only/web templates and failure while rendering; async only if claimed supported |
| Cookie/session state | Initially no cookie, known anonymous key, existing same-account auth key, different-account auth key; failures before save, during session COMMIT, after commit, before headers and after possible headers |
| Mutating routes | Reset, verify, change, email issue, login; prior state snapshots, distinct/same raw password, active/consumed/revoked/expired token distinctions; test unrelated student unaffected |
| Commit | Known rollback, actual committed-then-ack-fault for each relevant atomic group, session update commit ambiguity, on_commit callback timing, deferred-trigger COMMIT exceeding statement timeout |
| Time budgets | Startup options/SHOW on both aliases, offline exclusion, duplicate override rejection, connect budgets, multiple statements, Python work/idle termination, broken wire/worker cancellation with uncertain outcomes |
| Failure response/privacy | Correct status/no-store/Retry-After by explicit stage policy; no SQL or secret in bodies, logs, headers, queries, path/exception exports; no DB-dependent rendering |
| Compatibility | Existing normal/wrong login, reset/verify/change/registration contracts and all historical suites on real PG17 after approved PR29 integration; no active devices, quota/recovery changes, schema/grant/RLS changes |

Use mutation checks only against valid corrected invariants. A mutation test cannot rescue an assertion the real framework cannot satisfy. Hosted CI and the Stage C lab should execute the same corrected independent cases once implementation is authorized; no Stage C lab result exists yet.

## Scope recommendation and owner decisions

B1 is a sensible small first implementation **after revision**: application-only query/lock/idle settings, correct failure routing/classification, a minimal safe renderer and honest per-flow uncertain-outcome wording. It does not need PR26 device activation, new quotas, schema, grants or RLS changes. Keep B2 transactional session finalization, B3 event logging, B7 recovery/outbox and infrastructure separate. Note that the roadmap's B0 “no live behavior change” description is inaccurate for merging PR29's authentication race fix.

Owner should choose whether B1 preserves existing authenticated access on failed requests or intentionally introduces logout/no-renewal semantics. The latter expands the current file/scope contract and cannot be approved as a mere error-page change. Approve concrete timeout candidates only with their limited guarantees and explicit remaining transport/COMMIT risks; defer final worker/proxy limits until a complete budget and lab evidence exist. Revised handling of the session-origin 400 path and minimal log/privacy protections must be specified before coding. This review requests a revised plan, not authorization to implement the corrections.

## Verification and artifacts

- **14 independent Django probes passed** (they assert existing behavior, not B1 compliance), using the repository AuthenticationTestRunner and actual distinct test-migrator/runtime/auth LOGINs on PostgreSQL 17.11. The 100ms session lock timeout and 25P03 idle kill are real PostgreSQL events. Ack-loss faults are deterministic injections **after real commits**, not a claim of a physically disrupted network.
- **Standalone COMMIT experiment passed:** startup statement_timeout=100ms; control 57014 ≈105ms; native commit with deferred trigger ≈353ms, row count 1. Values are observed local timings, not SLAs.
- Source and reproduction commands: [B1_INDEPENDENT_PROBE_APPENDIX.md](B1_INDEPENDENT_PROBE_APPENDIX.md). Runtime target was the read-only PR29 worktree at bec0a44, whose application implementation is unchanged at approved 42910ed; PR30's website-test delta is irrelevant to these probes. No local combined merge was created and no full combined release is certified.
- Pinned document CI [43134525846](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43134525846) is successful. It tests the existing repository, **not the unimplemented B1 specification**. Historical full suites were not rerun for this documentation-only review; prior exact-head results remain in PR32/33.
- Inspection covered the pinned plan; repository views/tokens/principals/middleware/settings/routing/templates; Django transaction/base-backend/session/handler sources; psycopg connection/commit/conninfo behavior; and PR35 architecture. No provider, proxy, live email, partial-network-delivery or real-student tests are claimed.

Review/probe documentation is kept on an independent branch. PR36, authentication implementation branches and all application files are untouched. No merge, purchase, implementation or deployment was performed.
