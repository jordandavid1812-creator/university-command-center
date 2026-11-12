# Post-merge security verification and B1a proposal

Verified **12 November 2026 (Africa/Lagos)**. **B1a is technically ready for separately owner-authorized implementation; not implemented or authorized by this document.** This is a documentation-only preparation slice, not launch/staging acceptance.

## Verified master release, not rehearsal substitution

Current master is **`2d811ab31b811fb5652dc4c9142a559e738ad6d0`**, the canonical PR26 merge. Canonical PR29 is merged as **`5bd3c42f2748da8b6b082b853b005e63cc869b78`**. Git ancestry and GitHub metadata confirm both.

The actual PR26 merge's **push-triggered** [Foundation quality run43249712131](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43249712131), head2d811ab31b811fb5652dc4c9142a559e738ad6d0, is completed/success. Every job and its logs were inspected:

| Job | Exact executed evidence |
| --- | --- |
| `tests` | Success;113 legacy CLI/Streamlit/academic tests |
| `database-tests` | Success;33 foundation +46 restricted-role isolation +149 authentication/device/password-race +91 website =319 DB-backed tests; **PostgreSQL17.11** |
| `frontend-browser` | Success; UI1 10 + premium-auth5 + UI2 12 =**27 browser methods**; Chromium158.0.8127.18 |
| `dependency-audit` | Success |

Total regression baseline: **432** (113+319). No skips reported in inspected test summaries. This is merged-master evidence, **not PR49 CI standing in for a missing merge run**. No failure or missing/pending required job was found.

## Security completion and dormancy

| Item | Current disposition |
| --- | --- |
| PR29 canonical implementation | Merged; reviewed head42910ed09ed1a20aee556e77666cf6e347c724cd; CAS password upgrades and row-lock credential revalidation present |
| PR26 canonical implementation | Merged; final head e6549de5cbb9f31a3967775047af40ed63a28201 adds only D-1 docs to reviewed44c515f903cc35f1dfdd3d1c2b777a8d1a873222 |
| PR48 | Open draft, unmerged, **evidence only**, head f2a350b84c3c337586c1d1d8b976d8517df9c6b4; not a deployment artifact or source PR to merge instead of29 |
| PR49 | Open draft, unmerged, **noncanonical evidence only**, head c198a44d2e2412fa4bf3d2ebf7fc515caf8563ec; its21 evidence methods are not silently counted in the432 master baseline |
| Device/counter activation | **Dormant**. Actual merged Python source has primitive imports only in offline `clear_auth_artifacts`; views/backends/middleware do not issue device cookies, call admission primitives or enforce LoginLimit rows. Master compatibility/isolation tests passed |
| Auth/roles/academic boundary | Current432 tests cover existing CSRF/session/token/race protections, real separate runtime/auth LOGINs, grant guards, PG17 MAINTAIN rejection, forced academic RLS and exact math/ownership. No broad new assurance beyond these tested boundaries |
| B1 / accepted staging / operations | Incomplete. No dbsafety/classifier/sanitizing handler implemented; no accepted B1 or production release |

Merged `server/` bytes equal the independently rehearsed application candidate4593af40635833d9a7574333cbf7d656c9469136; later D-1 changes were documentation only. Actual source checks corroborate the dormant import boundary. Existing device primitives can produce a signed string when called explicitly by trusted test/internal code; that is not live HTTP cookie issuance or authentication.

**Deployment evidence boundary:** this task performs no deployment, provisioning or persistent/production migration. Reviewed CI contains quality jobs with disposable PostgreSQL; `production.py` still deliberately refuses startup, and no deployment workflow is present in that inspected quality pipeline. Repository/CI evidence does not independently attest to all external operator actions or production database histories. No external deployment/production migration is established or claimed by this verification. Before any real environment work, inventory it separately; a Git merge is not a production migration.

Remaining reviewed limits stay open: auth SQL can lower DeviceGeneration despite normal service increments; automatic reset/device revocation is deliberately unwired while dormant; old applied0003 revisions require history/forward-plan review; migration→provisioning temporarily returns503; real email/recovery, logs outside the future protected sink, backups/restores, keys, privacy, AT/physical-device/actual-zoom testing and provider operations remain unaccepted. Neither merger activates S0-02B/C or authorizes B1.

## Authoritative B1 scope and independent conditions

Use merged [Stage B Revision5](STAGE_B_IMPLEMENTATION_PLAN.md), head9b8cca56253526c770082b8b5bb9e41d9915ee7f, especially §6.6/6.9/6.10/6.11/6.14. Independent [PR42 review](https://github.com/jordandavid1812-creator/university-command-center/pull/42), head642df7909afc882e5ed61a62f232113c560a5e08, is **APPROVE WITH CONDITIONS for design**, not permission to implement. Its two implementation-test conditions remain mandatory:

- **R5-T1 / B1a:** an exception after an UPDATE inside `atomic` is a pre-COMMIT rollback control, not a committed/lost-acknowledgement probe. For committed-side evidence, call real `_commit` and then inject, or inject after real `SessionStore.save` returns; use a clean observer connection to prove row/expiry persistence. Label real faults, injected driver faults, pre-commit and post-commit hooks accurately. Do not infer rollback or commit from HTTP status.
- **R5-T2 / B1b:** unsafe-handler fixtures must survive logging configuration (include them in test LOGGING or inject between configuration and ready). Assert the unsafe graph exists at the guard boundary and that removing the guard fails the test. Merely adding a child handler during settings import can be undone by dictConfig.

## Smallest safe B1a slice — settings, validation and timer observations only

One implementation PR after separate authorization, from the then-current approved master. First reviewable production scope is the plan's **B1a as a whole**, with its minimum tests; a parser-only unit pass is not B1a acceptance. Internal commits may separate helper/parser, profile wiring/check and PG17 evidence without expanding scope.

| Proposed file | Intended change |
| --- | --- |
| `server/accounts/dbsafety.py` (new) | `apply_db_safety` merges validated timeout options for approved application aliases; preserves TLS/unrelated options, rejects duplicates/conflicts and is idempotent |
| `server/config/settings/auth_common.py` | Wire helper after auth alias creation; act on `auth` and `STUDENT_DB_ALIAS` only |
| `server/accounts/checks.py`, `apps.py` (new) | Register timer check **accounts.E101**; startup registration itself must not query DB or install B1b logging guards |
| New focused `auth_tests/test_b1_*.py` / test-only profile fixtures | Full §6.11 B1a acceptance evidence below; preserve historical test files |
| `docs/AUTHENTICATION.md` | Document application-only options, tuning limits, startup preflight and rollback |

Actual current `auth_common.configure` deep-copies `default` into `auth`. In auth/web test profiles, `default` is the test migrator and `STUDENT_DB_ALIAS` already equals `runtime` via `security_test`; only `auth`/`runtime` may change. In auth/web serving profiles, the academic application alias is `default`; it and `auth` receive options. Test both orders/copies explicitly: no accidental inherited migrator timers or shared mutable dictionaries. `auth_test`/`web_test` import paths must not conceal alias leakage.

**Exclude** `auth_migration`, foundation `test`, `security_test` alone, `development`, `runtime` alone and offline/provisioning commands. Do not edit base/production profiles to install global defaults. Preserve existing operator-supplied offline settings rather than erase them. No ALTER ROLE/DATABASE timeout policy, migration, grant change, dependency, middleware/handler/view change, session-engine change, counters/device wiring, academic change or new retry belongs in B1a. E102–E104/privacy flags remain B1b, not this slice.

## Timer candidates — owner approval and synthetic tuning only

| Setting | Candidate from approved plan | Meaning / limits |
| --- | --- | --- |
| `lock_timeout` |3 seconds, auth and academic runtime | Each lock acquisition wait; must remain below the statement limit. Not a request/COMMIT budget |
| `statement_timeout` |5 seconds auth;10 seconds academic runtime | Statement execution; not COMMIT-time work, Python hashing, established-connection transport or total request |
| `idle_in_transaction_session_timeout` |15 seconds | Idle gap inside a transaction; real25P03 terminates the session; verify safe reconnection. Not total transaction duration |
| `connect_timeout` |5 seconds | libpq connection attempt; attempts/addresses/DNS can extend overall time. Verify a single-address stalled-handshake listener; no DNS or end-to-end guarantee |

No PG17 `transaction_timeout`, pool, worker/proxy or HTTP deadline is introduced. Final values require measured Stage C work, not guessed production tuning. Preserve `sslmode`, `sslrootcert` and unrelated libpq options; reject duplicate/conflicting `-c` settings, including attempts to hide a second assignment. Reapplying identical settings must not append duplicates. Direct connections built from approved alias parameters must carry these options; arbitrary unconfigured external psycopg clients are not magically governed.

Settings validation rejects malformed/out-of-policy inputs safely. E101 must be exercised by real `manage.py check --deploy` in the secure test profile. WSGI does not automatically execute Django system checks; later Stage C preflight must invoke them explicitly.

## Transaction, status and privacy boundaries

- Preserve current atomic boundaries and password-race behavior. Real statement/lock failure inside an explicit block requires rollback before reuse; a later finalizer failure does not undo earlier autocommit throttle/CAS writes. CAS may legitimately be skipped for a current hash or affect zero rows; use an old-hasher fixture when observing that unit.
- Lost acknowledgement can mean persisted or not. Test controlled pre-COMMIT rollback separately from real-COMMIT-then-error persistence on a clean connection. Do not add compensating password/session writes or security-write retries. Preserve only Django's existing session-key collision retry.
- **No classifier/status conversion in B1a.** Preserve current view/INSERT500, session UPDATE `SessionInterrupted`400 and existing role-boundary503 where applicable. Later B1c must distinguish proven programming defects (500), outages/configuration (503), and genuine concurrent deletion (existing400), walking bounded allowed cause/context chains; that implementation is not authorized here.
- Observe all five login starting states N/AN/SA/SX/DA; do not assume every login cycles a key or every response save is UPDATE. Same-account K may remain valid/renew; account-switch rollback can preserve A; failed change can delete the browser cookie while a server copy remains valid. New-authority-delivery/deletion and per-phase state tests must use §6.3's actual oracles, not a blanket “500 means no rows/session.”
- B1a adds no sensitive logging. Use synthetic fault data, bounded observations (SQLSTATE/class/role flags/counts), and private captured logs; do not publish passwords, token paths, SQL parameters, cookies, raw student identifiers, IPs or headers. Existing logging gaps are **not fixed by timers**. B1b installs protected-profile sink sanitation **before B1c** introduces new failure routing; excluded offline logs and Gunicorn/proxy/raw stderr remain separately handled risks. No new privacy claim before those gates pass.

## Minimum acceptance tests and negative controls

Require real **PostgreSQL17**, actual separated LOGINs and forced RLS, under both URL roots where applicable. No SQLite substitution, privileged web alias or relaxed historical assertion. Observe real blockers with `pg_blocking_pids`; bound waits and inspect post-failure state through a clean connection.

1. **E in full:** TLS/options preservation; duplicate rejection/idempotence; actual SHOW values on fresh/reused auth/runtime and direct connections; no B1 options on the test migrator/excluded profiles (fresh subprocesses plus real check/offline commands); E101 through check --deploy; stalled TCP handshake; restricted-role57014 statement timeout,55P03 lock wait and25P03 idle termination/reconnection; deferred-trigger regression proving statement timeout is not a COMMIT bound.
2. **H in full:** real autocommit throttle/CAS persistence without `_commit`, persistence despite later finalizer failure, real failed statement nonpersistence, explicit rollback versus correctly placed post-COMMIT injection, no added write retry. Apply R5-T1; test real CAS only when fixture exercises it.
3. **A1:** N/AN cycle once; SA/SX/DA do not. Finalizer row/key snapshots and response UPDATE (N/AN/SA) versus INSERT (SX/DA) match actual Django behavior; preserve same-account key, flush semantics and expiry observations.
4. **Nominated A2:** L0, L1, L4u55P03, L4i, L5u, L5i; **A5 C0**; existing statuses, CK1/CK2, no new non-empty authenticated-session delivery, allowed legitimate deletion, prior-key validity/expiry and DA row counts. Do not silently pull B1c/B1d's full classifier/reset/verify matrix into B1a or claim it completed.
5. **F:** preserve all current432 regressions and27 browsers, including PR29 races, device dormancy/grants/MAINTAIN, academic/ownership/query budgets and UI1/premium-auth/UI2. Audit locks and run migration drift/safety. Re-run website and authentication suites plus all3 browsers after **each** B1 increment. Record genuine additions, skips, versions, exact head and hosted results; no fixed guessed future total.
6. **Negative/mutation controls:** remove one timeout/helper call, leak timers onto migrator, overwrite TLS, allow duplicate `-c`, remove E101 or substitute the wrong commit-fault hook: at least one meaningful assertion must fail. Verify lifecycle controls detect wrong SA/DA key/row assumptions, false rollback of autocommit writes and added retry. Do not count an infrastructure error as a successful negative control.

## Operational impact, rollback and owner decisions

No schema/grant/role migration is needed. New per-connection options affect newly opened app connections; an eventual release must control worker/connection recycling and assess long-running work and transient failures. No accepted staging from B1a–B1c: trusted synthetic development only until complete B1d independent acceptance. This proposal performs no infrastructure work.

Rollback means reverting the authorized B1a settings/helper/check integration and replacing affected app connections/workers through the approved local process, leaving existing operator-owned DB defaults alone. It does not rewind committed writes or authorize reversing accounts0003. Stop acceptance for alias leakage, TLS loss, wrong SQLSTATE/lifecycle oracle, new retry, query/math/role/dormancy regression, leaked sentinels or missing hosted evidence. Preserve failed-run evidence; never tune by suppressing assertions.

| Owner decision | Required timing / recommendation |
| --- | --- |
| **D-B1-1** prior authority | Acknowledge existing SA retention/possible renewal and rolled-back account-switch A validity **before B1a**; revocation/no-renewal would be separate policy work |
| **D-B1-2** failed change | Acknowledge allowed browser deletion with server-side prior validity **before B1a**; no compensating-write behavior |
| **D-B1-3** timer candidates | Explicitly approve the listed values for synthetic tests/tuning **before B1a**, not production guarantees |
| **D-B1-5** sequence/scope | Explicitly authorize B1a and the separately reviewed B1a→b→c→d gates; no intermediate staging/real data |
| **D-B1-4** logging tradeoff | Decide before B1b: protected-profile fixed-label sink, diagnostic loss/stderr changes, offline exclusions and immutable-at-runtime graph |
| **D-B1-6** classification policy | Decide before B1c: bounded chain/SQLSTATE rules, defect500, documented handler400 exception and opaque-chain limits |

Both code-merge prerequisites are now satisfied; their merge approval does **not** imply these policy/scope decisions. No new explicit B1a authorization is established by this task. Recommendations do not accept residual risks for the owner.

**Next exact safe action:** owner reviews this proposal and explicitly authorizes the B1a scope/timer experiments (D3/D5), acknowledging D1/D2; then create a fresh small implementation branch from verified current master, implement only the helper/wiring/E101 and nominated tests, run exact-head PG17/browser evidence and stop for independent review. Until then remain in documentation/preparation. No B1 code, security activation, merge, closure, purchase or deployment is performed here.
