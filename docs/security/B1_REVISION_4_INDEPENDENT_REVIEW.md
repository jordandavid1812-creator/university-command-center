# B1 Revision 4 independent design review

**Verdict: REQUEST CHANGES.** Review date: 12 November 2026. Reviewed PR #36 exactly at `e9178135aaf3636a3d49d1cd6d75df3b3e07d18e`, not a moving branch. This is a design review, not an audit of an implemented classifier or sanitizer. Findings below identify plan defects; they do not claim newly exploitable production vulnerabilities.

Revision 4 substantially improves exception classification, deletion-cookie handling, rendering, privacy coverage and incremental gates. However, its replacement session oracle is factually wrong, the proposed startup guard conflicts with offline profiles, and its commit taxonomy still applies an explicit-transaction guarantee to autocommit writes. Correct these before authorizing the affected implementation. Owner acceptance cannot make an incorrect oracle valid.

## Evidence and scope

Compared the exact plan with PR #37's original review and PR #38's six findings at `a908e12cd43c9e7574818091dcd48f027bb9502c`. Inspected Django **5.2.19**, psycopg **3.3.8**, existing accounts views/settings/session routing, and Stage C's `docs/LOCAL_STAGING_ARCHITECTURE.md` at `e3da0bf`. PR #36 changes only the plan relative to master `c19c1a335c6817e9eb2b359e5944a63eea3f3189`.

Ran three independent observation test methods on **PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2)** with separate migration, authentication and academic runtime roles. They cover four login entry states, two response-save failure states and autocommit persistence. All three passed. Two additional source/stdlib observations confirm the offline logging graph and syntax-only label acceptance. [Reproducible source, commands and results](B1_REVISION_4_REVIEW_PROBES.md) accompany this report.

The runtime under observation is PR #29 at `bec0a44`: `server/accounts`, `server/config` and `server/auth_tests` are unchanged at approved integrated head `42910ed`. This is the dependency the plan requires before B1; it is not a hypothetical implementation of Revision 4. Fault injection is expressly identified below. No B1 code was written and no full historical suite was rerun for this documentation review. Existing prior PostgreSQL observations remain evidence, not a claim that all proposed tests now exist.

## Disposition of R3-01 through R3-06

| Previous finding | Revision 4 disposition | Independent conclusion |
| --- | --- | --- |
| R3-01 — Medium, classification/400 defect | §6.4 defines transparent wrappers, bounded cause/context traversal, three whole-walk passes and one status table | **Addressed at design level.** Reachable driver `42703` is DEFECT and returns 500 at handler400. Actual implementation and routing tests remain required. Unknown/hidden nodes have explicitly narrower guarantees (RB-10). |
| R3-02 — Medium, account-switch rollback oracle | §6.3 distinguishes rollback, uncertain commit and response save | **Partly addressed, not closed.** Rollback preservation is correct, but the new account-switch and same-account tables misread `auth.login()`; R4-01 below. |
| R3-03 — Medium, legitimate cookie deletion | CK1/CK2 prohibit non-empty issue/renew headers while permitting deletion; F-CHG C2 separates browser deletion from server rollback | **Addressed at design level.** Keep deletion flags/max-age tests and prior-authority assertions; never strip deletion cookies to satisfy a blanket no-cookie assertion. |
| R3-04 — Medium, incomplete logging privacy | §6.8 covers security/CSRF, request metadata, handler propagation, lastResort and formatter failures | **Substantially improved, partly unresolved.** The unconditional ready guard breaks offline profiles (R4-02); label safety, category transport and deployment configuration need the clarifications below. |
| R3-05 — Medium, contradictory global blueprint/gates | §2 now permits status variants, prior authority, orphan rows and unknown commit; privacy precedes new error paths | **Global diagram corrected; not fully closed.** Wrong session tables/RB-1 and the autocommit taxonomy remain. B1b also depends on a walker scheduled in B1c. |
| R3-06 — Low, renderer/fatal exception wording | §6.7 catches Exception only; process-control exceptions propagate; DEBUG/propagation and no-active-exception cases are explicit | **Addressed at design level.** No promise to survive resource exhaustion; tests must exercise both auth and website roots. |

## Required corrections

### R4-01 — Medium, blocking: session lifecycle and acceptance oracle are incorrect

**Affected:** §6.3.1 lines 271–276; §6.3.2 L2/L4; §6.3.3 SA L4 and explanatory paragraph; §6.10 login matrix; RB-1's “SA L4” orphan claim; correction matrix's source claim.

Django `contrib/auth/__init__.py:175–187` has an `if SESSION_KEY ...` branch and an **else** calling `cycle_key()`. A different authenticated account causes `flush()` in the first branch; it does not subsequently execute that else. A valid same-account session neither flushes nor cycles. Only N/AN execute `cycle_key()` during login. The plan explicitly states that all four paths do so.

Database-backed `SessionStore.save()` (`contrib/sessions/backends/db.py:114–138`) calls `create()` when the key is None. Therefore the account-switch response performs a fresh INSERT of authenticated data, not an UPDATE of an anonymous row inserted during finalization. CREATE errors can reach handler500 directly rather than the UPDATE → UpdateError → SessionInterrupted → handler400 path.

**Reproduction:** independent real-PostgreSQL observations:

| State | cycle calls during login | Rows after auth_login inside finalizer | Existing key retained? |
| --- | --- | --- | --- |
| N / no session | 1 | 1 anonymous row, authentication data still in memory | No |
| AN / anonymous session | 1 | 1 anonymous row | No |
| SA / same authenticated account | 0 | 1 existing authenticated row | **Yes** |
| DA / different authenticated account | 0 | **0**, key is None | No |

Injected failure **before response-time save**, after successful finalizer commit: SA returns 500, retains its valid original row/key, creates no orphan, sends no session cookie. DA returns 500 with **zero** session rows: A was deleted, B has not been inserted. This directly contradicts SA L4 (“K deleted; new authenticated orphan”) and DA L4 (“B anonymous row”). Successful SA also retains its known key, so the prior evidence of expiry extension on a committed-but-unacknowledged response UPDATE applies to this exact path, not merely “other requests.”

**Correction:** repair source explanation, phase labels, tables, tests and RB-1 together. Split response INSERT and UPDATE outcomes; include key generation/exists/INSERT failures for DA. Retain the correct DA rollback union and F-CHG deletion distinction. Do **not** change successful authentication behavior to make the false table pass. Add the observation assertions to the first implementation PR before accepting its phase coverage.

### R4-02 — Medium, blocking B1b: startup handler enforcement lacks a profile boundary

**Affected:** §6.8 points 1–2; §6.9 apps.py/checks.py; §6.10 profile compatibility; §6.11 B1b.

LOGGING is configured only by `auth_common.configure`, but `AccountsConfig.ready()` is described as unconditionally rejecting every non-sanitizing root/Django handler. `base.INSTALLED_APPS` includes accounts; `auth_migration` imports base without auth_common. A fresh process using that profile actually has `LOGGING={}` and Django handlers `StreamHandler` and `AdminEmailHandler`. The proposed ready check would reject it before migration/provisioning commands can run. Historical foundation/security profiles share this compatibility concern.

**Correction:** define an explicit authentication/web privacy-policy setting or equivalent exact profile scope, including lastResort mutation and E102–E104 registration/evaluation. Enforce the graph fail-closed in protected web processes; preserve offline migration/foundation behavior. Do not solve this by putting runtime policy or runtime credentials in the migration profile. Test each profile in a **fresh subprocess**, because Django setup/global logging cannot be safely reset by override_settings alone. Prove offline checks, migrations/provisioning and historical suites still start, and that an unsafe handler in each protected web profile prevents startup.

### R4-03 — Medium, blocking the state-model acceptance: implicit autocommit is omitted

**Affected:** §6.1 unit list and P2 (“a transaction never commits without COMMIT”); tests and write-outcome language derived from it.

The same section includes autocommit throttle/CAS writes. PostgreSQL commits a successful standalone statement implicitly: no explicit client COMMIT is needed. The PostgreSQL probe inserted a session row using the auth alias with autocommit enabled; a different connection saw it persisted while Django `_commit()` was called **zero** times. This is normal server behavior, not an uncertain-COMMIT injection.

Consequently “COMMIT was not sent” establishes rollback only for an explicitly begun transaction known not to have committed. Dispatch of an autocommit UPDATE/INSERT can already cause persistence; response loss makes its outcome unknown even though no explicit COMMIT was sent.

**Correction:** distinguish explicit atomic units from implicit statement transactions, and define dispatch/acknowledgement phases for the latter. Add a real autocommit persistence test and an explicitly labeled post-execute/lost-ack fault observation. Do not infer throttle/CAS rollback from a later finalizer rollback or a missing client COMMIT. No automatic retries of either kind of security mutation.

## Further implementation hazards and clarifications

### R4-04 — Low, privacy hardening before B1b: labels need a trust policy, not just a character regex

§6.8 copies logger names and exception class qualnames accepted by regex, plus unvalidated `levelname`. A synthetic logger `accounts.SYNTHETIC_SESSION_SENTINEL` and an allowed Django Error subclass named `SYNTHETIC_SESSION_SENTINEL` both pass the documented regex. A custom LogRecord can also carry arbitrary levelname. This is a reproducible counterexample to an unconditional “secrets cannot reach the sink” claim, **not evidence that current request inputs control repository logger names or exception classes**; current ordinary names are static.

Map names to reviewed fixed namespaces, levels to a numeric-to-fixed-name table, and exceptions to fixed categories/known class labels (unknown → OTHER); or explicitly limit the guarantee to immutable trusted labels and enforce/review that constraint. Test sentinel-bearing names/classes/levelname and sanitizer-error fallback as well as msg/args/request. Startup graph validation is a snapshot: document that trusted runtime logging reconfiguration must be prohibited or revalidated; it cannot stop a later raw child handler from emitting before the root sink.

### R4-05 — Low, sequencing/observability clarification before B1b/B1c

§6.8's exception summary uses the §6.4 walker, while the walker/classifier is scheduled for B1c after B1b. Put the shared bounded traversal utility with its tests in B1b, and reuse it in B1c (or specify a deliberately smaller independent B1b summary). Avoid two divergent traversals or an import of a file that does not yet exist.

§6.4 promises category/SQLSTATE for consumed exceptions, and RB-9 repeats that promise; §6.8 drops arbitrary extras and its output template has **no category field**. Define a small typed, fixed allowlist for those fields and the emission call, or revise the diagnosability claim. This does not require the wider B3 event taxonomy.

### R4-06 — Low, Stage C integration gate before accepted staging

E104 explicitly covers `*_secure` profiles, while Stage C specifies `local_staging.py`. Use an explicit secure/staging policy flag rather than relying on a filename suffix, and require E101–E104 under that exact module. Stage C already requires DEBUG false, but document that its profile actually activates these guards. This can be verified during integration; it does not require implementing Stage C in B1.

## Classification, failures and renderer assessment

The bounded traversal is now deterministic: explicit cause takes precedence over context; suppression blocks implicit context; only transparent subclasses are walked; object-identity cycle detection and a 16-node cap bound traversal. SQLSTATE-bearing driver nodes across the whole bounded walk precede no-state driver fallbacks. An unrelated outer template/BadRequest does not inherit an outage classification just because a DB error happened earlier. This is a defensible, limited policy.

A **reached** UndefinedColumn(42703) gives DEFECT → 500 at all B1 boundaries, including handler400. No-SQLSTATE psycopg Operational/Interface errors give CONNECTION_UNAVAILABLE → 503 without Retry-After. Bare Django errors do not magically prove an outage. The role-check middleware and already-handled academic/registration exceptions are explicitly preserved exceptions to the new routing table.

Do not generalize “proven defect never 400” to a driver hidden beyond the depth cap, suppression or an unrecognized wrapper: the plan intentionally has no such proof. A Django-only session failure can remain 400; this is not evidence of a reached SQLSTATE defect. Test unknown/opaque wrappers, suppression, cause-versus-context, mixed driver nodes, malformed states, truncation and cycles. Confirm the exact driver exception classes under real timeout/termination tests; constructed driver instances prove traversal only.

handler400 has its exception argument; handler500 can inspect the active exception in Django's current synchronous exception conversion path, including middleware errors, but sys.exc_info remains an upgrade-sensitive boundary. process_exception covers view exceptions, not arbitrary middleware/response exceptions. Both handlers are needed. Unrecognized/non-DB exceptions preserve their existing path. The template-free accounts renderer, zero user/session/reverse/context access, no-store response, constant per-variant bodies and Exception-only fallback are appropriate. Test fallback with no active exception, recursive rendering failure, both URL roots, both DEBUG flags, and propagation of SystemExit/KeyboardInterrupt/GeneratorExit. Do not claim constant bodies alone defeat enumeration or that a response status proves rollback.

Cookie rules are now appropriately narrower: prohibit unintended **non-empty** authenticated-session delivery before headers; permit legitimate expiry/deletion; distinguish response headers, browser jar, server rows and prior known keys. No B1 status conversion revokes previous legitimate authority. DA response INSERT can create an undelivered authenticated row after commit. SA response UPDATE can renew a known key despite response failure. A password-change rollback may delete the browser cookie while restoring server-side access; successful reset/change hash invalidation and same-plaintext reset must be tested separately. Post-header failures cannot be repaired by a handler.

## Residual-risk register review

| Risk | Disposition / required evidence |
| --- | --- |
| RB-1 undelivered rows | Accept in principle with bounded expiry/cleanup, but **remove SA L4** and use corrected INSERT/UPDATE phases. B2 grouping cannot make HTTP delivery atomic with commit. |
| RB-2 headers already delivered | Accept/defer transport boundary to Stage C. Explicit tests before headers do not establish post-header guarantees. |
| RB-3 no total COMMIT/request bound | Accept only as documented availability risk. Lock/statement/idle/connection timers are not an HTTP deadline. Measure worker/proxy budgets and unknown outcomes in Stage C. |
| RB-4 non-B1 logs | Stage C/D dependency, no sensitive URLs in Gunicorn/Caddy/crash logs. Gunicorn may share the OS process and Python logging system; exclusion is a **named logger/configuration boundary**, not literally a different-process guarantee. |
| RB-5 token issue without delivery | Recovery availability risk deferred to B7. Verify mail failure/retry behavior; do not claim B1 repairs revoked older links or delivered emails. |
| RB-6 retained prior authority | Accept only with owner D1/D2 approval and corrected SA/DA/change tables. Browser deletion and server revocation differ. |
| RB-7 PG16 evidence | Keep historical attribution. This review adds PG17.11 observations, but **each implementation increment still needs real PG17 CI** and restricted-role tests; PG16 or SQLite cannot substitute. |
| RB-8 sys.exc_info boundary | Accept with real middleware/view/response integration tests, no-active-exception fallback and upgrade regression tests. |
| RB-9 reduced diagnosis | Owner logging-policy decision. Repair category transport; demonstrate safe output and operational usefulness, not merely silence. |
| RB-10 exception layouts | Accept with explicit bounded/opaque-chain limitations and pinned-version tests; unknown does not prove outage. Upgrade review required. |
| RB-11 DEBUG tooling | Local synthetic use only. Explicitly activate fail-closed flags in Stage C's actual profile and test both propagation/debug flags. |

## Owner decisions D-B1-1 through D-B1-6

| Decision | Recommendation |
| --- | --- |
| D1 prior authority on failed login | Accept retention/possible SA renewal and A retention after DA rollback **after correcting the oracle**. Requiring failure revocation/no-renewal is a separate B2 policy change. |
| D2 failed change | Accept valid server rows after rollback, with possible browser deletion. Do not add an unsafe compensating write/retry to pretend otherwise. |
| D3 timers | Approve candidate values only for initial synthetic testing/tuning: connect 5s, lock 3s, auth statement 5s/runtime 10s, idle 15s as proposed. Require evidence and measured Stage C deadlines; none is a COMMIT/request bound. |
| D4 logging | Approve direction, defer final consent until protected/offline scope, safe labels, typed category and immutable graph policy are explicit. New stderr and lost development request lines are real operator tradeoffs. |
| D5 increments | Approve a→b privacy→c routing→d wording in principle, with walker dependency resolved and each PR independently authorized/reviewed. No intermediate accepted staging or real-data use. |
| D6 classification | Recommend the stated bounded SQLSTATE policy with preserved handled contracts and reachable-defect→500 tests. Document the deliberate Django-only handler400 exception and opaque-chain limits. |

These are recommendations, not owner approvals or authorization to merge PR #29/#26, implement B1, provision or deploy.

## First safe increment and minimum evidence

**B1a (settings/timeouts only)** is the first sensible implementation, after R4-01/R4-03 correct its acceptance model and the owner authorizes it; the plan's PR #29-on-master prerequisite remains external. B1b must wait for R4-02 and the privacy/sequencing corrections. Do not sneak cookie/session lifecycle changes into B1a.

Minimum B1a PR evidence on real PostgreSQL 17:

1. SHOW/connection inspection for auth/runtime aliases, direct connections and fresh/reused connections: expected options and connect_timeout; preserve TLS verify-full/root CA and existing options. Reject duplicate/conflicting options; repeated application is idempotent. Offline migration/DBA profiles are excluded. E101 runs via the actual check command, not an assumption that WSGI invokes checks.
2. Held-lock and sleep timeout observations with the restricted roles; idle-in-transaction termination/reconnect; locally stalled TCP handshake demonstrates connection timeout without claiming a DNS/multi-host/request/COMMIT bound. No privileged role is used for web requests. No role/RLS/grant changes.
3. Correct N/AN/SA/DA baseline assertions above. Real lock failures before finalization and response-save failures for **both INSERT and UPDATE**, separate injected commit/ack-loss observations, old-key validity/expiry snapshots, browser jar plus Set-Cookie inspection, no new non-empty auth cookie before failed response. Test legitimate deletion after change rollback, never require its absence.
4. Per-unit clean-connection checks: throttle/CAS implicit autocommit, finalizer explicit transaction and response save are distinct; known rollback versus known commit versus unknown. No automatic retry and no universal “500 means nothing persisted” oracle.
5. Existing response behavior stays unchanged in this increment; no promise that B1c's classifier already exists. Full legacy, foundation, restricted-role, authentication and website suites on PG17 CI; synthetic fixtures only, no migration/dependency/authentication success-path changes. Independent review of the increment before acceptance.

B1b must then prove sink bytes (not just assertLogs), root/child/security/CSRF/lastResort paths, malicious metadata and fallback failures, unchanged source records, fresh-process offline/protected profiles and fatal propagation. B1c needs the full classifier matrix and real handler400 UndefinedColumn→500, timeout→503, genuine concurrent logout→400, view versus middleware/response routing, zero-query renderer/fallback and enumeration comparisons. B1d must finish the full flow/phase matrix (login, change, reset, verify, issue), mutation-tested assertions, wording review and all historical PG17 suites. Every increment needs hosted CI and an independent review; none establishes Stage C acceptance on its own.

Stage C remains compatible in direction: localhost synthetic lab, separate runtime/auth/migration identities, forced RLS, pgcrypto, verified database TLS, exact secure settings preflight, bounded proxy/worker budgets, sanitized logs and restore tests. No extra infrastructure is needed for this review. Correct the profile gate and record the logging/deadline dependencies rather than implementing them here.
