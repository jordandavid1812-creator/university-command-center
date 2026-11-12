# Independent B1 Revision 5 review

**Overall verdict: APPROVE WITH CONDITIONS.** Reviewed 12 November 2026 (Africa/Lagos). Exact PR #36 commit: `9b8cca56253526c770082b8b5bb9e41d9915ee7f`. Comparison: Revision 4 at `e9178135aaf3636a3d49d1cd6d75df3b3e07d18e` and PR #40's independent report/evidence at `e713a1e0f83ee06ea931f34326afbf3c09ddbb3b`.

The three previous Medium findings are resolved **at the design level**. The three Low corrections are also technically supportable. There is no remaining architecture blocker to owner-authorized **B1a**, subject to the plan's PR #29 integration prerequisite. Two Low test-construction clarifications below must be satisfied during the relevant implementation reviews; neither requires changing application behavior or restarting the architecture design.

This is not authorization to implement or merge, and not an approval of code that does not yet exist. Documentation CI cannot validate a future sanitizer, classifier or timeout helper.

## Independent evidence

Inspected the exact Revision 5 document, its diff, the existing profiles/views/backends/throttling code, Django **5.2.19**, psycopg **3.3.8** and CPython 3.12 logging behavior. Re-ran the Revision 4 observation tests and added three new methods against real **PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2)** using separate migration, auth and runtime LOGINs. **Six methods passed**, including the inherited four-state login observation and response-save failure cases. Synthetic identities only; the disposable test database was destroyed.

Runtime source: PR #29 `bec0a44`; accounts/config/auth_tests match approved integrated head `42910ed`. This is the dependency explicitly reviewed by the plan. The observations do not execute an implementation of Revision 5. [Reproducible probe source and results](B1_REVISION_5_REVIEW_PROBES.md) accompany this report. No full historical suites or new native COMMIT-duration experiment were needed for this documentation-only comparison; previous PG17.11 COMMIT evidence remains applicable.

## Finding-by-finding disposition

References below are to `docs/security/STAGE_B_IMPLEMENTATION_PLAN.md` at the exact reviewed commit.

| Previous finding | Disposition | Exact design/source/probe evidence |
| --- | --- | --- |
| **R4-01 — Medium: session lifecycle** | **Resolved in design.** | §6.3.1–6.3.3 (lines 319–400), §6.5, A1/A2 and RB-1/RB-6 now distinguish N/AN/SA UPDATE from DA/SX INSERT. Django auth `__init__.py:175–187` calls cycle_key only in the no-user else branch; sessions/db.py:68–78,114–138 creates on a None key. Reproduced N/AN cycle count 1, SA/DA 0; finalizer row counts 1/1/1/0; SA retains K; DA response save not applied leaves 0 rows. New SX observation: stale same-user hash causes flush, zero finalizer rows, zero cycle calls and **one response-phase INSERT**. No false SA orphan or DA anonymous replacement row remains. |
| **R4-02 — Medium: logging profile boundary** | **Resolved in design.** | §6.8.1–6.8.2 (614–678), G and B1b: UCC_LOG_PRIVACY=enforce controls LOGGING, lastResort, ready guard and E102/E103. auth/web profiles opt in; migration/base/runtime/foundation/security profiles stay excluded. Fresh-process inspection reconfirmed auth_migration currently has no privacy flag, LOGGING={}, and default StreamHandler/AdminEmailHandler; the proposed conditional guard no longer rejects that graph. Implementation must prove this with fresh subprocesses and real offline commands. |
| **R4-03 — Medium: implicit autocommit** | **Resolved in design.** | §6.1 (240–290) separates S0–S3 implicit units from E0–E4 explicit units. A successful autocommit statement persists; later rollback does not undo it. Existing throttling.py upsert and backends.py CAS are outside atomic blocks; QuerySet.update uses mark_for_rollback_on_error, which does not create a transaction in autocommit. Reproduced persistence with **zero _commit calls**, and real throttle plus real password-hash CAS persisting while a later login finalizer rolls back. A post-execute fault persists in autocommit but rolls back inside atomic (new probe). See R5-T1 for test injection precision. |
| **R4-04 — Low: label provenance** | **Resolved in design.** | §6.8.3 (679–730) replaces regex copying with fixed logger/method/route/level tables, identity-keyed exception labels, known SQLSTATE lookup and typed enum events; raw name/levelname/qualname are not emitted. Sink-level sentinel/fallback tests are explicit. RB-12 now accurately limits the startup graph snapshot. This is a sound specification, not a tested sanitizer. |
| **R4-05 — Low: walker sequencing/category transport** | **Resolved in design.** | §6.4, §6.8.3, §6.9 and §6.11 put exception_chain plus tests in **B1b**; B1c reuses it. FailureEvent is a typed extra, and the fixed output explicitly includes event/category/sqlstate. The dependency gap and missing category field are removed. |
| **R4-06 — Low: Stage C profile flag** | **Resolved in design; integration remains a gate.** | §6.7, §6.8.1 and §6.12 use UCC_SECURE_PROFILE=True rather than a filename suffix. local_staging must set it, opt into log_privacy.configure, run E101–E104 under its exact module and prove unsafe startup rejection. This matches Stage C's explicit fail-closed profile architecture. |

The earlier deterministic classifier/handler400 defect correction, allowed deletion-cookie rule, renderer Exception-only fallback and process-control propagation remain intact. A reachable driver 42703 is DEFECT→500 at handler400; no-driver/opaque/capped chains retain the expressly limited policy. No broad guarantee that every buried driver error is discoverable is made. B1 does not revoke prior authority merely by returning 500/503.

## Remaining Low test-construction conditions

### R5-T1 — Low: distinguish a post-statement fault from a post-COMMIT fault

**Affected:** §6.10 fault labels (758 onward), A2 at line 781, B1a L5u/L5i acceptance.

A2 calls L5u/L5i “real save, then lost acknowledgement (injected-post-execute).” A true callback after the whole SessionStore.save has returned is after its atomic block and commit; that is a valid committed-side observation. An execute_wrapper raising immediately after the SQL UPDATE/INSERT, however, is **inside** that atomic block and causes rollback. It is E1, not E3.

**Reproduced:** the same real Student UPDATE followed by an injected OperationalError persisted in autocommit; inside transaction.atomic it rolled back. This is not an uncertain-COMMIT simulation. Existing §6.1 is correct; the fault-placement label must not undermine its tests.

**Required during B1a:** use an injected-commit hook that calls the real _commit and then raises, or an explicitly labelled post-save hook after the real save returns. Assert the committed row/expiry using a clean connection. Keep the pre-COMMIT statement-fault case as the rollback control. Do not pass an L5 test by accepting rollback from a fault that never reached COMMIT. Real backend termination must likewise record whether dispatch was actually controlled; a pre-COMMIT kill proves rollback, not an uncertain commit.

### R5-T2 — Low: place unsafe-logging fixtures after configuration, or in the configuration dictionary

**Affected:** §6.10 G `test_protected_profile_with_raw_handler_fails_startup`, line 862; B1b guard mutation evidence.

Adding a StreamHandler directly to django.security while importing a test settings module can be undone by the subsequent dictConfig. Python logging.config._handle_existing_loggers clears child handlers when configuring their parent. The same applies to a root filter removed by root configuration. Therefore that particular fixture construction does not necessarily present an unsafe graph to AccountsConfig.ready().

**Reproduced:** after django.setup(), added a raw handler to django.security and applied the planned graph shape using a standard NullHandler in place of the unimplemented sanitizer. The raw handler was removed. This tests stdlib configuration order, not any B1 implementation.

**Required during B1b:** include the raw child handler/filter in the test-only LOGGING dictionary so it survives configure_logging, or inject after configure_logging but before ready. Assert that the unsafe object exists at the guard boundary, then that startup fails. Mutation-removing the guard must make the test fail. Do not weaken the production guard or edit historical tests.

Both conditions can be fulfilled in the implementation test PRs without another architecture revision. No remaining Medium/High blocker is confirmed.

## Acceptance gates and B1a readiness

**B1a is technically ready for owner-authorized implementation, not presently authorized.** Before starting: satisfy the plan's PR #29-on-master prerequisite; obtain separate owner authorization for the B1a scope/timer experiments and increment sequence (D3/D5), with acknowledgement of the prior-authority behavior in D1/D2. D4 and D6 must be explicitly accepted before their respective logging/classification increments. No merge is authorized by this review.

B1a's §6.11 gate is appropriately limited to settings, validation, E101 and documentation. Keep existing statuses and successful authentication/session behavior unchanged. Required evidence remains:

- E: actual auth/runtime SHOW values, new/reused/direct connections, TLS options preserved, duplicate rejection/idempotence, connect handshake stall, real lock/statement/idle timeouts, offline/migrator exclusions and check command execution. No request/COMMIT/DNS bound claim.
- H: actual implicit throttle/CAS persistence, real statement error rollback, per-unit snapshots, explicit rollback versus post-COMMIT fault and no added retries. CAS assertions require an old-hasher fixture **when the CAS is executed**; a normal current-hash login may skip that unit or a concurrent CAS may affect zero rows. Do not change the backend to force every login to upgrade.
- A1 and the nominated A2/A5 cases: all five initial session states; UPDATE and INSERT paths; clean-connection old-key validity/expiry, no new non-empty session cookie, allowed legitimate deletion and orphan accounting. Apply R5-T1 when testing L5.
- F: every historical suite on PostgreSQL 17 with restricted roles/forced RLS, independently reviewed before acceptance. Documentation CI is insufficient.

B1b privacy before B1c routing is the correct order. Require fixed-label sink bytes, unchanged source records, cached traceback/extras/CSRF/token-path tests, formatter/sanitizer/stream failures, lastResort, shared walker and fresh-process profile/command tests, including R5-T2. Historical assertLogs can intentionally attach a test-only handler after startup; this is not permission for runtime application reconfiguration.

B1c must cover real handler400 UPDATE errors and handler500 INSERT errors, reachable defect→500, genuine deletion→400, outage→503, no-SQLSTATE policy, bounded chain edge cases, typed consumed events, zero-query/template rendering and fatal propagation in both roots. B1d completes all flow/phase/token/cookie matrices, mutation tests and uncertain-outcome wording. Each increment needs independent review. No intermediate is accepted staging, B1-complete or real-data-ready.

## Residual risks and Stage C

| Risk | Assessment |
| --- | --- |
| RB-1 orphans | Corrected: N/AN committed UPDATE or DA/SX committed INSERT can create an undelivered authenticated row; SA is renewal of a known key, not an orphan. Expiry/cleanup mitigate; B2 cannot make HTTP delivery atomic. |
| RB-2 post-header failure | Valid explicit boundary; accept only as a documented transport risk. |
| RB-3 unbounded COMMIT/request | Valid availability residual. Stage C must measure worker/proxy/client budgets and failure outcomes; statement_timeout is not a COMMIT deadline. |
| RB-4 external/named log sinks | Corrected configuration boundary, including Gunicorn in the same process. Stage C must redact access/error paths, queries and request bodies; raw stderr/export/retention remain separate. |
| RB-5 issued token without email | Existing recovery-availability dependency; remains deferred to B7. Not repaired by status conversion. |
| RB-6 prior authority | Correctly distinguishes SA retention/renewal, DA rollback and failed-change browser deletion/server validity. Requires D1/D2 acceptance. |
| RB-7 PG16/documentation evidence limits | Accurate attribution. This review adds PG17.11 observations, but implementation tests on PG17 remain mandatory. |
| RB-8 active exception in handler500 | Upgrade-sensitive framework boundary; test middleware/view/response origins and no-active-exception fallback. |
| RB-9 restricted diagnostics | Fixed typed fields now support the claimed output. Owner must accept loss of free text and new sanitized stderr before B1b. |
| RB-10 exception layouts | Accept with bounded/opaque-chain limitations, pinned framework versions and upgrade tests. Unknown is not proven outage. |
| RB-11 DEBUG tools | Local synthetic use only; secure staging must activate the explicit flag and reject both DEBUG flags. |
| RB-12 mutable logger graph | Honest startup-snapshot limitation. Source scan is a review guard, not a Python sandbox; third-party/configuration changes still need review. |
| RB-13 excluded profiles | Deliberate compatibility boundary. Offline commands may still process sensitive data: empty URLconf is not proof that their logs are harmless. Restrict operator access/log handling; reassess before real-data operations or adding routes. |

Stage C compatibility is sound in direction: exact local_staging flags/preflight, role separation, forced RLS, pgcrypto, database TLS verify-full, controlled local synthetic lab, safe Gunicorn/Caddy logs and measured failure budgets. Stage C must explicitly wire both safety/options and privacy helpers without overwriting TLS options; merely calling the privacy helper does not install timeout options. Test the final module and both real aliases. No accepted Stage C environment from B1a–B1c.

## Owner decisions

- **D1/D2:** recommend accepting existing prior-authority/rollback semantics for B1; any failure revocation/no-renewal policy is separate work.
- **D3:** recommend candidate timers for synthetic tuning only; no total request/COMMIT guarantee.
- **D4:** recommend fixed-label protected-profile logging with explicit offline and runtime-reconfiguration limits; approve the diagnostic/stderr tradeoff before B1b.
- **D5:** recommend the four small separately authorized/reviewed increments with the specified evidence and no intermediate staging.
- **D6:** recommend the bounded SQLSTATE policy and preserved handled contracts, including the deliberate Django-only handler400 exception.

These recommendations do not accept residual risks on the owner's behalf. Only the independent documentation branch was changed. PR #36 and all implementation/security branches remain untouched; no implementation, merge, purchase or deployment occurred.
