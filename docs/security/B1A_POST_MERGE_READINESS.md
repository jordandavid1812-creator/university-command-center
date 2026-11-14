# Post-merge security verification and B1a proposal

Verified **12 November 2026 (Africa/Lagos)**. **B1a design corrections await focused independent re-review and owner decisions; not implemented or authorized by this document.** This is a documentation-only preparation slice, not launch/staging acceptance.

## Verified master release, not rehearsal substitution

Current master is **`2d811ab31b811fb5652dc4c9142a559e738ad6d0`**, the canonical PR #26 merge. Canonical PR #29 is merged as **`5bd3c42f2748da8b6b082b853b005e63cc869b78`**. Git ancestry and GitHub metadata confirm both.

The actual PR #26 merge's **push-triggered** [Foundation quality run 43249712131](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43249712131), head 2d811ab31b811fb5652dc4c9142a559e738ad6d0, is completed/success. Every job and its logs were inspected:

| Job | Exact executed evidence |
| --- | --- |
| `tests` | Success; 113 legacy CLI/Streamlit/academic tests |
| `database-tests` | Success; 33 foundation + 46 restricted-role isolation + 149 authentication/device/password-race + 91 website = 319 DB-backed tests; **PostgreSQL 17.11** |
| `frontend-browser` | Success; UI1 10 + premium-auth 5 + UI2 12 = **27 browser methods**; Chromium 158.0.8127.18 |
| `dependency-audit` | Success |

Total regression baseline: **432** (113 + 319). No skips reported in inspected test summaries. This is merged-master evidence, **not PR #49 CI standing in for a missing merge run**. No failure or missing/pending required job was found.

## Security completion and dormancy

| Item | Current disposition |
| --- | --- |
| PR #29 canonical implementation | Merged; reviewed head 42910ed09ed1a20aee556e77666cf6e347c724cd; CAS password upgrades and row-lock credential revalidation present |
| PR #26 canonical implementation | Merged; final head e6549de5cbb9f31a3967775047af40ed63a28201 adds only D-1 docs to reviewed 44c515f903cc35f1dfdd3d1c2b777a8d1a873222 |
| PR #48 | Open draft, unmerged, **evidence only**, head f2a350b84c3c337586c1d1d8b976d8517df9c6b4; not a deployment artifact or source PR to merge instead of #29 |
| PR #49 | Open draft, unmerged, **noncanonical evidence only**, head c198a44d2e2412fa4bf3d2ebf7fc515caf8563ec; its 21 evidence methods are not silently counted in the 432 master baseline |
| Device/counter activation | **Dormant**. Actual merged Python source has primitive imports only in offline `clear_auth_artifacts`; views/backends/middleware do not issue device cookies, call admission primitives or enforce LoginLimit rows. Master compatibility/isolation tests passed |
| Auth/roles/academic boundary | Current 432 tests cover existing CSRF/session/token/race protections, real separate runtime/auth LOGINs, grant guards, PG 17 MAINTAIN rejection, forced academic RLS and exact math/ownership. No broad new assurance beyond these tested boundaries |
| B1 / accepted staging / operations | Incomplete. No dbsafety/classifier/sanitizing handler implemented; no accepted B1 or production release |

Merged `server/` bytes equal the independently rehearsed application candidate 4593af40635833d9a7574333cbf7d656c9469136; later D-1 changes were documentation only. Actual source checks corroborate the dormant import boundary. Existing device primitives can produce a signed string when called explicitly by trusted test/internal code; that is not live HTTP cookie issuance or authentication.

**Deployment evidence boundary:** this task performs no deployment, provisioning or persistent/production migration. Reviewed CI contains quality jobs with disposable PostgreSQL; `production.py` still deliberately refuses startup, and no deployment workflow is present in that inspected quality pipeline. Repository/CI evidence does not independently attest to all external operator actions or production database histories. No external deployment/production migration is established or claimed by this verification. Before any real environment work, inventory it separately; a Git merge is not a production migration.

Remaining reviewed limits stay open: auth SQL can lower DeviceGeneration despite normal service increments; automatic reset/device revocation is deliberately unwired while dormant; old applied 0003 revisions require history/forward-plan review; migration→provisioning temporarily returns 503; real email/recovery, logs outside the future protected sink, backups/restores, keys, privacy, AT/physical-device/actual-zoom testing and provider operations remain unaccepted. Neither merger activates S0-02B/C or authorizes B1.

## Authoritative B1 scope and independent conditions

Use merged [Stage B Revision 5](STAGE_B_IMPLEMENTATION_PLAN.md), head 9b8cca56253526c770082b8b5bb9e41d9915ee7f, especially §6.6/6.9/6.10/6.11/6.14. Independent [PR #42 review](https://github.com/jordandavid1812-creator/university-command-center/pull/42), head 642df7909afc882e5ed61a62f232113c560a5e08, is **APPROVE WITH CONDITIONS for design**, not permission to implement. Its two implementation-test conditions remain mandatory:

- **R5-T1 / B1a:** an exception after an UPDATE inside `atomic` is a pre-COMMIT rollback control, not a committed/lost-acknowledgement probe. For committed-side evidence, call real `_commit` and then inject, or inject after real `SessionStore.save` returns; use a clean observer connection to prove row/expiry persistence. Label real faults, injected driver faults, pre-commit and post-commit hooks accurately. Do not infer rollback or commit from HTTP status.
- **R5-T2 / B1b:** unsafe-handler fixtures must survive logging configuration (include them in test LOGGING or inject between configuration and ready). Assert the unsafe graph exists at the guard boundary and that removing the guard fails the test. Merely adding a child handler during settings import can be undone by dictConfig.

## Smallest safe B1a slice — settings, validation and timer observations only

One implementation PR after separate authorization, from the then-current approved master. First reviewable production scope is the plan's **B1a as a whole**, with its minimum tests; a parser-only unit pass is not B1a acceptance. Internal commits may separate helper/parser, profile wiring/check and PG 17 evidence without expanding scope.

| Proposed file | Intended change |
| --- | --- |
| `server/accounts/dbsafety.py` (new) | `apply_db_safety` owns protected aliases' `OPTIONS["options"]` field using a deterministic fixed string, validates integer limits, preserves other connection settings, rejects conflicts/PGOPTIONS and marks safety configured |
| `server/config/settings/auth_common.py` | Wire helper after auth alias creation; act on `auth` and `STUDENT_DB_ALIAS` only |
| `server/accounts/checks.py`, `apps.py` (new) | Register/check **accounts.E101 only when `UCC_DB_SAFETY_CONFIGURED is True`**; preserve `AccountsConfig.name = "accounts"` and `label = "accounts"`. No startup DB query or B1b logging guard |
| New focused `auth_tests/test_b1_*.py` / test-only profile fixtures | Full §6.11 B1a acceptance evidence below; preserve historical test files |
| `docs/AUTHENTICATION.md` | Document application-only options, tuning limits, startup preflight and rollback |

Actual current `auth_common.configure` deep-copies `default` into `auth`. In auth/web test profiles, `default` is the test migrator and `STUDENT_DB_ALIAS` already equals `runtime` via `security_test`; only `auth`/`runtime` may change. In auth/web serving profiles, the academic application alias is `default`; it and `auth` receive options. Test both orders/copies explicitly: no accidental inherited migrator timers or shared mutable dictionaries. `auth_test`/`web_test` import paths must not conceal alias leakage.

**Explicit opt-in and E101 gating (B1A-1):** `apply_db_safety` alone sets `UCC_DB_SAFETY_CONFIGURED = True` after successful safety configuration. This is not an environment switch or a flag added manually in base/offline profiles. `AccountsConfig` must retain both **name and label as `"accounts"`**, preserving app/migration identity. Its `ready()` registers E101 only when this flag is True; the check itself also guards on the flag to handle settings overrides safely. With the flag absent/False, E101 must not run or fail an inactive profile. Registration performs no database query or B1b logging setup. Fresh-process tests verify protected flags/check registration and inactive profile startup; removing the helper/flag must fail the protected-profile assertions, not turn every inactive profile into an error.

**Profile exclusions:** `auth_migration`, foundation `test`, `security_test` alone, `development` and `runtime` alone do not opt in; their migration/provisioning processes must not acquire B1a options or E101 failures merely because the accounts app is installed. Preserve their operator-supplied settings. Scope follows the selected **profile**, not an assumption that every command is exempt. Do not edit base/production profiles to install global defaults. No ALTER ROLE/DATABASE timeout policy, migration, grant change, dependency, middleware/handler/view change, session-engine change, counters/device wiring, academic change or new retry belongs in B1a. E102–E104/privacy flags remain B1b.

**Offline cleanup exception to the old blanket wording (B1A-2):** the documented `clear_auth_artifacts --settings=config.settings.auth_development` command uses the protected auth profile and performs its deletes through `auth`; it therefore **inherits the auth connection timers**. **Cleanup option 1 — OWNER-APPROVED on 12 November 2026:** run cleanup under the existing protected auth database timeout configuration. The owner's explicit B1A-2 instruction in this conversation approves this design/documentation decision only; it does not authorize B1a implementation or approve the other pending policies. Do not invent a cleanup exemption, switch it to a migration/privileged login, or silently alter successful cleanup semantics. Required real PG 17 tests must demonstrate **(1) database timeout behavior during cleanup, (2) rollback of the timed-out statement, (3) no unintended data modification, (4) accurate command failure reporting and (5) preservation of restricted database privileges**. Hold a lock on the first cleanup DELETE until timeout; observe the expected database error, verify the timed-out statement changed no rows and compare relevant before/after data through a clean connection. Assert a failing command result/non-success report (never the success message), then successful normal cleanup after releasing the lock. Verify the command still uses the restricted auth LOGIN with unchanged grants and no migration/runtime privilege escalation; it must not use a privileged fallback or added retry. Capture failure reporting with synthetic data and no sensitive values. The current command has several separate deletes, not one overall atomic transaction: this first-statement control must not be mislabelled as proof that later failures undo earlier committed cleanup. Preserve that distinction and do not add command-wide transactions/retries under this scope.

## Timer candidates — owner approval and synthetic tuning only

| Setting | Exact candidate validation | Proposed value |
| --- | --- | --- |
| `connect_timeout` | Integer **seconds, 2–30 inclusive** | **5 seconds** on each application alias |
| `lock_timeout` | Integer **milliseconds, at least 1000 and strictly less than that alias's statement timeout** | **3000 ms** |
| `statement_timeout` | Integer **milliseconds, strictly greater than lock timeout and at most 60000** | **5000 ms auth; 10000 ms runtime** |
| `idle_in_transaction_session_timeout` | Integer **milliseconds, 5000–300000 inclusive** | **15000 ms** |

**Validation (B1A-4):** accept exact integer values (never Python booleans); an environment input may be an ASCII digits-only integer string parsed exactly. Reject booleans, floats/Decimal values even if integral, decimal/exponent notation, unit-bearing strings, whitespace/sign-bearing strings, zero, out-of-range values and silent rounding/coercion. Validate the lock/statement relationship independently for **auth and academic runtime**. The test migrator/default and excluded-profile connections are not configured. Require actual `SHOW` values on **fresh and reused** auth/runtime connections, not only settings-dictionary inspection; verify no timer injection on the migrator.

**Owned options contract (B1A-3):** B1a owns `OPTIONS["options"]` on protected application aliases. Use a deterministic fixed template/order built only from validated integers. Proposed exact strings are:

```text
auth:    -c lock_timeout=3000 -c statement_timeout=5000 -c idle_in_transaction_session_timeout=15000
runtime: -c lock_timeout=3000 -c statement_timeout=10000 -c idle_in_transaction_session_timeout=15000
```

Set the separate `OPTIONS["connect_timeout"]` integer to 5 for the proposed candidates. Accept an absent options field or an empty string (`""`) on first application or an **identical** string on reapplication; reject every conflicting/nonidentical existing options string, including non-string values, duplicate assignments or additional arbitrary GUCs, rather than parse/merge/overwrite operator intent. Conflicting existing connect_timeout also fails validation; identical reapplication is idempotent. Reject **presence of environment `PGOPTIONS` in protected profiles**, including an empty value, to eliminate a second uncontrolled options source. Inactive/offline profiles retain their existing environment/settings; do not globally clear PGOPTIONS.

Preserve **sslmode, sslrootcert and all unrelated connection settings/OPTIONS keys** exactly. Ownership of the options string is not permission to erase another setting; unsupported existing options require an explicit configuration decision. Direct connections built from approved alias parameters must use the same validated options and controlled environment. Arbitrary external clients or later environment changes are not automatically governed.

These **connection-level timers are availability protections, not a complete security boundary**. Lock waits/statements/idle gaps have different scopes. Idle expiry can terminate the connection (25P03); verify reconnection. libpq connect_timeout applies per attempt and cannot guarantee bounded DNS/multiple-address time. No guaranteed end-to-end **request or COMMIT deadline**, PG 17 transaction_timeout, pool, worker/proxy or HTTP deadline is introduced. Final tuning belongs to measured Stage C work.

**E101 command evidence (B1A-6):** run `python server/manage.py check --deploy --settings=config.settings.web_secure` with a synthetic environment and the explicit safety flag intact; removing/corrupting timer settings must report **accounts.E101 specifically**. Unrelated deployment warnings may appear, so do not require zero warnings or attribute a nonzero command exit to E101 without inspecting its check ID. Inactive profiles without the flag must not produce E101. WSGI does not automatically execute Django system checks; future Stage C preflight invokes them explicitly.

**Real PBKDF2 observation (B1A-5):** add an **evidence-only** PG 17 test using Django's real PBKDF2 password hasher, including the concurrent same-secret-upgrade/reverification branch that hashes while the finalizer holds the Student row lock. Use a real lock observer/controlled schedule and record the observed lock-hold duration, hasher/iteration count and environment without credentials or student identifiers. Do not substitute the fast fixture hasher or make the measured duration an arbitrary pass/fail threshold. Synchronization/correctness checks may fail if the intended branch/lock was never exercised; the duration itself informs **future Stage C tuning**, not a performance SLA or new timeout policy.

## Transaction, status and privacy boundaries

- Preserve current atomic boundaries and password-race behavior. Real statement/lock failure inside an explicit block requires rollback before reuse; a later finalizer failure does not undo earlier autocommit throttle/CAS writes. CAS may legitimately be skipped for a current hash or affect zero rows; use an old-hasher fixture when observing that unit.
- Lost acknowledgement can mean persisted or not. Test controlled pre-COMMIT rollback separately from real-COMMIT-then-error persistence on a clean connection. Do not add compensating password/session writes or security-write retries. Preserve only Django's existing session-key collision retry.
- **No classifier/status conversion in B1a.** Preserve current view/INSERT 500, session UPDATE `SessionInterrupted` 400 and existing role-boundary 503 where applicable. Later B1c must distinguish proven programming defects (500), outages/configuration (503), and genuine concurrent deletion (existing 400), walking bounded allowed cause/context chains; that implementation is not authorized here.
- Observe all five login starting states N/AN/SA/SX/DA; do not assume every login cycles a key or every response save is UPDATE. Same-account K may remain valid/renew; account-switch rollback can preserve A; failed change can delete the browser cookie while a server copy remains valid. New-authority-delivery/deletion and per-phase state tests must use §6.3's actual oracles, not a blanket “500 means no rows/session.”
- B1a adds no sensitive logging. Use synthetic fault data, bounded observations (SQLSTATE/class/role flags/counts), and private captured logs; do not publish passwords, token paths, SQL parameters, cookies, raw student identifiers, IPs or headers. Existing logging gaps are **not fixed by timers**. B1b installs protected-profile sink sanitation **before B1c** introduces new failure routing; excluded offline logs and Gunicorn/proxy/raw stderr remain separately handled risks. No new privacy claim before those gates pass.

## Minimum acceptance tests and negative controls

Require real **PostgreSQL 17**, actual separated LOGINs and forced RLS, under both URL roots where applicable. No SQLite substitution, privileged web alias or relaxed historical assertion. Observe real blockers with `pg_blocking_pids`; bound waits and inspect post-failure state through a clean connection.

1. **E in full:** fixed owned-options/TLS preservation; exact reapplication and conflicting options/PGOPTIONS rejection; integer-type/range/cross-field boundary negatives; actual SHOW values on fresh/reused auth/runtime and direct connections; no B1 options on the test migrator/excluded profiles (fresh subprocesses plus real check/offline commands); flag-gated E101 specifically through `check --deploy --settings=config.settings.web_secure` (unrelated warnings allowed); protected flag/AccountsConfig identity and inactive-profile controls; owner-approved cleanup option 1 tests for database timeout, timed-out-statement rollback, no unintended data modification, accurate failure reporting and preserved restricted privileges; real PBKDF2 row-lock duration evidence without a timing threshold; stalled TCP handshake; restricted-role 57014 statement timeout, 55P03 lock wait and 25P03 idle termination/reconnection; deferred-trigger regression proving statement timeout is not a COMMIT bound.
2. **H in full:** real autocommit throttle/CAS persistence without `_commit`, persistence despite later finalizer failure, real failed statement nonpersistence, explicit rollback versus correctly placed post-COMMIT injection, no added write retry. Apply R5-T1; test real CAS only when fixture exercises it.
3. **A1:** N/AN cycle once; SA/SX/DA do not. Finalizer row/key snapshots and response UPDATE (N/AN/SA) versus INSERT (SX/DA) match actual Django behavior; preserve same-account key, flush semantics and expiry observations.
4. **Nominated A2:** L0, L1, L4u (55P03), L4i, L5u, L5i; **A5 C0**; existing statuses, CK1/CK2, no new non-empty authenticated-session delivery, allowed legitimate deletion, prior-key validity/expiry and DA row counts. Do not silently pull B1c/B1d's full classifier/reset/verify matrix into B1a or claim it completed.
5. **F:** preserve all current 432 regressions and 27 browsers, including PR #29 races, device dormancy/grants/MAINTAIN, academic/ownership/query budgets and UI1/premium-auth/UI2. Audit locks and run migration drift/safety. Re-run website and authentication suites plus all 3 browsers after **each** B1 increment. Record genuine additions, skips, versions, exact head and hosted results; no fixed guessed future total.
6. **Negative/mutation controls:** remove one timeout/helper call, leak timers onto migrator, overwrite TLS, accept conflicting options or PGOPTIONS, accept booleans/decimals/units/zero/out-of-range values, leak E101 to inactive profiles or remove its protected flag/check or substitute the wrong commit-fault hook: at least one meaningful assertion must fail. Verify lifecycle controls detect wrong SA/DA key/row assumptions, false rollback of autocommit writes and added retry. Do not count an infrastructure error as a successful negative control.

## Operational impact, rollback and owner decisions

No schema/grant/role migration is needed. New per-connection options affect newly opened app connections; an eventual release must control worker/connection recycling and assess long-running work and transient failures. No accepted staging from B1a–B1c: trusted synthetic development only until complete B1d independent acceptance. This proposal performs no infrastructure work.

Rollback means reverting the authorized B1a settings/helper/check integration and replacing affected app connections/workers through the approved local process, leaving existing operator-owned DB defaults alone. It does not rewind committed writes or authorize reversing accounts 0003. Stop acceptance for alias leakage, TLS loss, wrong SQLSTATE/lifecycle oracle, new retry, query/math/role/dormancy regression, leaked sentinels or missing hosted evidence. Preserve failed-run evidence; never tune by suppressing assertions.

| Owner decision | Required timing / recommendation |
| --- | --- |
| **D-B1-1 — PENDING** prior authority | Acknowledge existing SA retention/possible renewal and rolled-back account-switch A validity **before B1a**; revocation/no-renewal would be separate policy work |
| **D-B1-2 — PENDING** failed change | Acknowledge allowed browser deletion with server-side prior validity **before B1a**; no compensating-write behavior |
| **D-B1-3 — PENDING** timer candidates | Explicitly approve the listed values for synthetic tests/tuning **before B1a**, not production guarantees |
| **D-B1-5 — PENDING** sequence/scope | Explicitly authorize B1a and the separately reviewed B1a→b→c→d gates; no intermediate staging/real data |
| **D-B1-4 — later decision** logging tradeoff | Decide before B1b: protected-profile fixed-label sink, diagnostic loss/stderr changes, offline exclusions and immutable-at-runtime graph |
| **D-B1-6 — later decision** classification policy | Decide before B1c: bounded chain/SQLSTATE rules, defect 500, documented handler400 exception and opaque-chain limits |

**Cleanup option 1 — OWNER-APPROVED (B1A-2, 12 November 2026):** `clear_auth_artifacts` runs under the existing protected auth timeout configuration and must satisfy all five required test outcomes above. Approval source: the project owner's explicit “OWNER DECISION — B1A-2” instruction in this conversation. This approves design and documentation only, not implementation, merges, authentication changes or deployment. **All other B1a owner decisions remain pending**, including D-B1-1, D-B1-2, D-B1-3 and D-B1-5; D-B1-4 and D-B1-6 remain later pending decisions. This does not approve numeric timer candidates or broaden the statement rollback guarantee into command-wide atomicity.

Both code-merge prerequisites are now satisfied; their merge approval does **not** imply these policy/scope decisions. No new explicit B1a authorization is established by this task. Recommendations do not accept residual risks for the owner.

**Next exact safe action:** focused Claude re-review of these design corrections, then owner reviews this proposal and explicitly authorizes the B1a scope/timer experiments (D3/D5), acknowledging D1/D2; then create a fresh small implementation branch from verified current master, implement only the helper/wiring/E101 and nominated tests, run exact-head PG 17/browser evidence and stop for independent review. Until then remain in documentation/preparation. No B1 code, security activation, merge, closure, purchase or deployment is performed here.
