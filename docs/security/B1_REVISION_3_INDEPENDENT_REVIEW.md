# Independent B1 Revision 3 security design review

**Overall verdict: REQUEST CHANGES.** Revision 3 corrects the main false COMMIT/HTTP assumptions and makes substantial progress on all eight findings. Remaining **Medium** design inconsistencies in classification, session-state test oracles and logging need correction before approving the complete B1 plan. No new High-severity implementation vulnerability is asserted: B1 remains unimplemented. The original High findings are not being repeated unchanged.

Exact reviewed head: **`e308a9a86ba43df6a04a2bb22c87ee3792de785e`**, [PR #36](https://github.com/jordandavid1812-creator/university-command-center/pull/36), [pinned plan](https://github.com/jordandavid1812-creator/university-command-center/blob/e308a9a86ba43df6a04a2bb22c87ee3792de785e/docs/security/STAGE_B_IMPLEMENTATION_PLAN.md). Compared directly with revision 2 `7f438b16` and the eight findings/evidence merged through PR #37, now on master `c19c1a335c6817e9eb2b359e5944a63eea3f3189`. Review date: 12 November 2026 (Africa/Lagos).

Seven additional observation probes passed using Django 5.2.19, psycopg 3.3.8 and actual **PostgreSQL 17.11**, with separate real migrator/runtime/auth LOGINs and synthetic data. They test existing framework/code behavior, not an implemented B1 classifier/filter. Evidence/source: [probe appendix](B1_REVISION_3_REVIEW_PROBES.md). Original PostgreSQL 17.11 evidence in PR #37 remains valid; no SQLite or provider testing was substituted.

## Disposition of all eight original findings

| Original finding | Revision 3 disposition | Independent assessment |
| --- | --- | --- |
| B1-01 / High: session-save errors bypass handler500 | Adds handler400 and chain walk; preserves genuine logout 400 | **Core routing corrected; partially addressed.** SQLSTATE-bearing driver defects still fall through to 400 under the proposed handler400 rule. Classifier precedence also needs a precise whole-chain rule (R3-01) |
| B1-02 / High: 5xx does not revoke sessions/prevent renewal or valid rows | Orphans, SA renewal, P5/header uncertainty acknowledged; no automatic retry | **Core false guarantee withdrawn; partially addressed.** DA rollback states and expiry/deletion-cookie distinction are still inconsistent (R3-02/03/05) |
| B1-03 / High: COMMIT/request bound false | Withdraws COMMIT/total deadline claim, adds per-attempt connect_timeout, defers worker/proxy values | **Addressed as a design correction.** Remaining duration/transport uncertainty is an explicitly accepted/deferred risk, not another required finite-time guarantee |
| B1-04 / Medium: failed change need not flush/logout | Distinguishes pre-flush, failed DELETE, post-flush and uncertain COMMIT; owner selects prior-access policy | **Substantively addressed.** SG1 must allow deletion cookies and the acceptance matrix must express the phase results consistently (R3-03) |
| B1-05 / Medium: unsafe/unavailable renderer in auth settings | Template-free accounts renderer, no user/session/context/reverse, both roots and last resort | **Substantively addressed.** Clarify fatal-exception and DEBUG fallback wording before B1b (R3-06, Low) |
| B1-06 / Medium: universal invariants invalid per flow | Nominated-token snapshots, distinct/same-secret handling, verification row and clean-connection reads | **Substantially corrected; not fully closed.** The DA oracle and per-increment acceptance scope still need correction (R3-02/05) |
| B1-07 / Medium: framework logs leak paths/details | Adds Django logger filters, removes admin email, documents proxy/retention scope | **Partially addressed, not closed.** Coverage misses actual Django security loggers and does not define removal of live request/extras or full sink/formatter behavior (R3-04) |
| B1-08 / Medium: classification conflicts with preserved handlers | Explicit P0/registration/academic precedence; class 28 and invalid DB policy; ambiguous-unavailable | **Substantially addressed.** Repair handler400 defect handling, deterministic chain fallbacks and remaining global shorthand (R3-01/05) |

“Addressed as design” means the proposed contract is technically supportable, not that the feature is implemented, tested in CI or authorized to activate.

## Design defects blocking approval of the complete plan

### R3-01 — Medium: handler400 drops database defects back to client 400; classification precedence remains ambiguous

**Affected:** §6.3 lines 267–281 and 292; §6.4 line 304; §6.9 lines 404–406; §2.2 line 93.

The plan classifies all other driver SQLSTATEs as **defect** and says defects stay 500. But handler400 returns 503 only for recoverable/misconfigured/ambiguous and otherwise preserves 400. Thus a session-save `UndefinedColumn(42703)` or another proven database defect becomes a misleading client 400.

**Reproduced framework path:** injected a driver `UndefinedColumn`, explicitly wrapped as Django ProgrammingError during the actual session UPDATE. The real SessionStore and Django handling produced:

```text
SessionInterrupted → UpdateError → ProgrammingError → UndefinedColumn(42703)
HTTP 400 at handler400
```

This is a confirmed existing routing observation; the defect in Revision 3 is its specified fall-through, not an executed B1 implementation.

**Required correction before B1b:** proven driver outage → 503 with the agreed Retry-After; proven driver configuration → 503 without it; proven driver defect → minimal 500; genuine concurrent deletion/non-DB BadRequest → original 400. Add a full-stack session-UPDATE 42703/42P01 test alongside 55P03 and genuine logout. Do not classify every SessionInterrupted as an outage.

Also make the algorithm unambiguous: §6.3 says “first decisive node”, but its class fallback inspects the whole chain; “anything else” must not stop at the initial SessionInterrupted wrapper. Search recognized transparent wrappers for decisive driver SQLSTATE before no-state/class fallbacks. Define explicit behavior for no-driver InterfaceError, bare Django OperationalError, a truncated/cyclic chain and an unrelated non-DB outer exception. The correction matrix calls bare OperationalError ambiguous, rule 2 requires a psycopg connection-class node, and handler400 says never reclassify without a driver node. These are different rules. Name allowed transparent wrappers and return metadata such as database-origin versus non-DB so database defects are not sent into the existing DB-dependent web renderer. Synthetic chain tests must resolve these cases, not merely assert that a walk occurred.

### R3-02 — Medium: different-account login incorrectly assumes flush committed on rollback/early failure

**Affected:** §6.2 line 232; F-LOGIN lines 237–243; §6.9 line 393; correction matrix B1-02 at 194; owner policy D-B1-1.

The R3 source probe covers a **committed** finalization/session-write failure when browser A tries to log in as B. Its result is credible: A's old session was deleted, B's new key was not delivered. It does not establish that result for P0/P1, finalization rollback, or the not-committed side of uncertain P3.

**Additional PG17.11 probes:**

- Hold B's Student row; login as B from a browser authenticated as A. A real 100ms lock timeout produces the existing 500 and **A's original session remains valid**; its protected follow-up is 200.
- Fail before finalization COMMIT after the real auth_login/flush work. Django rolls back the A-session DELETE; **A remains valid and no B session row survives**. The browser still has A's key.

A future 503 status conversion alone cannot change these states. This is preserved prior A authority, not unauthorized B authority.

**Required correction:** express DA outcomes by write unit/phase: before flush or rolled-back flush → prior A may remain valid; committed flush with failed key delivery → A invalid, B may be orphaned; uncertain COMMIT → allow the appropriate committed/not-committed set. Assert no B authority delivered in every pre-header handled failure, rather than demanding that A always becomes anonymous. Extend the owner acceptance text to prior legitimate authority in a failed **account-switch** attempt; it is not only same-account renewal. Keep no-logout-on-error as a policy choice rather than silently changing authentication behavior to satisfy the wrong oracle.

### R3-03 — Medium: SG1 still forbids legitimate cookie deletion, conflicting with F-CHG

**Affected:** §6.2 SG1 line 220 and F-CHG lines 253–259; §6.9 flow assertions.

SG1 says the error response carries **no Set-Cookie for a session**. Django legitimately sends Set-Cookie to **expire** a session cookie when flush completed in memory, even when the transaction rolled back and the response is 5xx. That is distinct from issuing an authenticated cookie.

**Additional PG17.11 probe:** complete password-change flush, fail before COMMIT and roll back. Response is 500 with `sessionid=""; Max-Age=0`, while the old server-side session is valid again after rollback. This agrees with the revised per-phase uncertainty, but violates the literal SG1 assertion. It grants no new authority.

**Required correction:** prohibit new authenticated session-key issuance/renewal headers on the B1-generated pre-header error response, **allowing expiry/deletion headers**. Separate response cookie values, the browser jar after receipt, server-side prior session validity and existing copies of the key. Add an explicit allowed-deletion regression; don't change flush/logout semantics or strip protective deletion headers merely to make SG1 pass. Retain the stated fact that a client that receives no response may not receive any deletion header.

### R3-04 — Medium: logging design leaves actual authentication log paths and raw metadata outside its privacy assertion

**Affected:** §6.7 lines 360–367; §6.9 line 410; §6.11 B1c; RB-4.

**Confirmed mechanics/observations:**

1. A CSRF-rejected POST to a token-bearing reset URL logs its secret in **django.security.csrf**, with status 403. Filters attached only to django.request and django.server cannot affect that separate namespace. Other django.security exception paths also need inventory rather than assuming all errors use django.request.
2. Django log_response stores the **live HttpRequest** in LogRecord.request. A captured record exposes its session Cookie header, Authorization header, raw query, path metadata and IP through request.META. Rewriting request.path alone does not remove those references and can mutate the live request. The proposed checks of message/args/exc_text/formatted traceback do not inspect them.
3. A Python logger filter is not inherited by propagated child records. A marker filter on a parent logger runs for a direct parent event but not an event emitted by a child delivered to the parent's handler. This proves a coverage mechanism limitation, not that a nonexistent B1 filter has already failed.

**Required correction before B1c:** define the actual Django logger/handler/sink coverage, including CSRF/security paths for token-bearing auth URLs; otherwise narrow the claim and explicitly keep B1-07 open. Use safe record copies and an explicit allowlist: remove/replace the live request with a minimal non-sensitive representation, discard arbitrary extras and sensitive metadata, and do not mutate the request used by Django. Dropping the request reference needs no cookie/body/header reads. Set exc_info/legacy exc_text/stack_info to valid safe values; put a bounded summary in separate safe fields rather than assigning an arbitrary string where a traceback tuple is expected. Test already-cached traceback text, all selected handlers and propagation, both URL roots, malformed/encoded token paths, metadata/extras, filters/formatters raising, and absence of exception escape or raw-data fallback. Record-level/privacy assertions should reach the final formatted or serialized sink, not stop at the default message format.

B1 can still defer Gunicorn/Caddy logs to Stage C, retention/export to Stage D, and the security-event taxonomy to B3. The uncovered **Django** security logger is not a proxy/WSGI residual and must not be hidden inside RB-4. Empty ADMINS is useful but does not remove sensitive data from other LogRecord consumers. No external telemetry leak or implemented-filter defect was claimed or tested.

### R3-05 — Medium: correction matrix and global blueprint still disagree; incremental evidence gates need qualification

**Affected:** §2.1 line 86 (“Rollback: 503, no session, no cookie” for any T2 DB error); §2.3 I1/I9; §6.0; §6.11; RB-1 line 460.

The global T2 failure edge repeats the old universal rollback/no-row/503 guarantee. Section 6 correctly permits committed rows and uncertain COMMIT, and proven defects are supposed to be 500. Labeling the diagram an end state does not fix this: putting session/device work inside T2 in B2 still does not prevent a real server COMMIT followed by acknowledgement loss, or guarantee that client delivery happened. RB-1's B2 mitigation improves group atomicity but cannot eliminate all orphan sessions under lost acknowledgement.

**Required correction:** propagate the per-unit known-rollback versus uncertain/committed states into the diagram and global invariants; qualify “new authenticated” authority and distinguish prior sessions/deletion cookies. State that B2 unifies related writes but cannot make COMMIT atomic with HTTP delivery. Make byte-identical-response claims scope-specific: §6.6 intentionally has route/outcome variants and Retry-After categories, and these do not by themselves prove account-enumeration resistance.

B1a–B1d are viable small scopes, but the full matrix must not be treated as unnecessary until B1d. B1a actively introduces new timeout failure paths with existing 400/500 behavior; B1b introduces routing/status changes before B1c redaction and B1d's complete oracle. Require each increment's relevant PG17 flow/cookie/rollback/security regressions before its own acceptance. Do not label an intermediate branch “B1 complete” or use it as an accepted staging release. Bring minimal sensitive-record protection before or alongside new error handling, or explicitly confine intermediates to trusted synthetic development until B1c/d pass. No successful-path authentication change is needed to correct these specifications.

## Low-severity clarification before coding

### R3-06 — Low: renderer fatal-exception and handler500 fallback wording

**Affected:** §6.3 line 291; §6.6 lines 354–356.

“try/except BaseException-safe logic” is ambiguous. A generic BaseException catch could swallow SystemExit, KeyboardInterrupt or GeneratorExit and interfere with worker shutdown. Specify ordinary renderer-failure handling with Exception and explicit propagation of process-control exceptions; do not promise a fallback can survive every MemoryError/resource failure. Also DEBUG/DEBUG_PROPAGATE_EXCEPTIONS bypass the normal Django handler500 path; they do not cause that handler to run without an active exception and emit plain 500. Keep manual/no-active-exception fallback as a separate supported case. The intended template-free/DB-independent renderer remains sound; this clarification alone would not require rejecting the plan.

## Correctly addressed and accepted/deferred residual risks

- **Exception entry points:** handler400 is the right additional place to see SessionInterrupted's nested database error. View process_exception and handler500 remain complementary. Placement after SessionMiddleware does not catch response exceptions by itself. The previous sync/async observations remain valid; Revision 3 appropriately claims only the synchronous WSGI path and a conservative fallback.
- **Timeout model:** query/lock/idle limits are useful availability controls, not COMMIT or end-to-end deadlines. Per-attempt connect_timeout, DNS/multiple-address caveats and removal of invented worker/proxy values are correct. No new PG17 transaction_timeout or pooling scheme is assumed. Existing 17.11 COMMIT/idle evidence was not invalidated by this documentation revision.
- **Settings/roles:** merging application OPTIONS while preserving verify-full/CA root, direct connections, explicit auth + academic aliases, offline/test-provisioning exclusions and effective SHOW checks are compatible with PR #35. The explicit Stage C check --deploy preflight fixes the previous mistaken assumption that WSGI automatically runs registered checks. Test idempotence versus true duplicate/conflicting values and preserve existing offline-role policy.
- **State/atomicity:** nominated reset/verify token pairs, same-secret resets, on_commit email limitations, clean-connection state reads and pre-/in-/post-flush distinctions are largely correct. Post-response valid orphan rows are not an anonymous bypass when their key was not delivered. Same-account renewal/retention is now openly described as existing behavior and an owner decision.
- **Residuals that can be accepted/deferred:** unknown COMMIT/transport outcomes; P5 cookie delivery before a failed body write; prior-access retention/renewal if approved; orphan cleanup; undelivered email invalidating older links until B7; provider/proxy/WSGI logging and deadlines before Stage C acceptance; retention/sinks before external export; generation-counter SQL monotonicity and persistent 0003 history. None permits public deployment or hard account enforcement.

PG16 runs are honestly labeled and useful corroboration, not PG17 certification. The local observation probes in this review used PG17.11. Eventual B1 implementation CI and Stage C TLS tests remain mandatory.

## B1a–B1d and project-owner decisions

| Increment | Assessment / prerequisite before its independent acceptance |
| --- | --- |
| B1a settings/limits | Small and independently testable after PR29's authorized integration and owner timer approval. Include effective SHOW, TLS preservation, offline exclusions, deliberate local connection-timeout test and relevant real-timeout auth/session regressions. A network-unreachable address that fails immediately does not alone prove timeout enforcement; use a controlled stalled handshake/known attempt count. No accepted full-B1 or production-readiness claim |
| B1b classification/rendering | Appropriate scope **after R3-01/02/03 and renderer clarifications are settled**. Add session-save driver-defect →500, genuine logout →400, routing tests, known-cookie rollback cases, allowed deletion and no-new-key tests in this increment, not only B1d |
| B1c privacy | Appropriate scope **after R3-04 defines coverage and safe records**. Handler/propagation/metadata/formatter/security-logger tests required. Keep broader B3 event taxonomy separate |
| B1d wording/full matrix | Final reconciliation and all flow × phase × cookie assertions after per-increment gates; update global diagram/RB statements per R3-05. Full historical PG17 suites and independent implementation review required |

Owner decisions remain: accept prior legitimate access (including account-switch rollback) and same-account renewal on failure; select failed-change browser-cookie policy without confusing it with server revocation; approve configurable timers with no finite COMMIT/HTTP guarantee; approve the minimal logging scope and release ordering; authorize each implementation increment separately. No owner acceptance should be used to excuse incorrect SQLSTATE routing, a false test oracle or an unsupported privacy claim. Stage A merge authorization and PR29 integration remain external prerequisites.

## Verification limits and delivery

- Exact-head document CI [43138056459](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43138056459): success. This is existing-code CI, not evidence that unimplemented Revision 3 handlers/filters pass.
- Seven new tests **passed** in 2.013s on PostgreSQL 17.11, with real restricted-role test routing. Four cover real application/session behavior (the Student lock timeout is actual PG; rollback/driver faults are controlled injections), three cover logging mechanics/actual CSRF emission. No B1 filter, classifier or timeout helper was implemented. Full historical suites and the old COMMIT probe were not rerun unnecessarily; their prior evidence remains in PR37.
- Runtime source: read-only post-PR29 worktree bec0a44, application behavior byte-identical at approved 42910ed; the new document contains no implementation changes. No combined security branch merge or accepted staging build was created. Test fixture was local, disposable and synthetic; no external infrastructure was purchased or provisioned and no deployment occurred.
- This report and source appendix are on the independent documentation-only branch `docs/b1-revision3-independent-review`. PR #36/#26/#29 and application/authentication/infrastructure files remain untouched. The verdict is a request for precise plan corrections, not implementation authorization.
