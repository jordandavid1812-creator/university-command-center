# Independent implementation review — draft PR #26 (S0-02A)

**Recommendation: request revisions to the dormant foundation before merge; do not
activate S0-02B/C from this review.** No fix or source change was made on Claude's
branch. This report accompanies [the independent design review](S0_02_INDEPENDENT_REVIEW.md)
in documentation PR #27.

## Scope and evidence

Reviewed 11 November 2026:

- PR: [#26](https://github.com/jordandavid1812-creator/university-command-center/pull/26).
- Exact implementation HEAD: `0e9e478fd4ed4249cbb81501a75ffda5e2744fd4`.
- Base: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`.
- Isolated detached worktree; all commands read this revision. Temporary test drivers
  and synthetic PostgreSQL data lived outside its source tree and are not deliverables.
- Current login/reset/password-change code is unchanged, and the module is dormant:
  [isolation test, lines 563–575][tests-isolation]. This limits present exposure but
  does not make an incorrect primitive a safe future integration contract.

Tests independently executed with Python 3.12.14, Django 5.2.19, psycopg 3.3.8 and
**PostgreSQL 17.11**, using real distinct non-superuser migrator/runtime/auth LOGIN
roles. No SQLite or privileged SET ROLE impersonation was substituted. The test
migrator had test-only CREATEDB; application-role grants came from PR provisioning.

| Suite at the pinned HEAD | Result |
| --- | --- |
| Legacy CLI/Streamlit/calculation/storage | 113 passed |
| Foundation accounts/academics | 33 passed |
| Academic security | 46 passed |
| Authentication | **111 passed** (76 historical + 35 new) |
| Website | 69 passed |
| Total supplied tests | **372 passed** |

The PR description's 104 auth / 365 total / 28 new figures lag the reviewed source.
This is a reporting discrepancy, not a failing suite. Five supplementary observational
probes also completed on a separate PG17 test DB. They record behavior, not successful
security regressions: their completion does not mean the defects below are fixed.
Initial scratch harness attempts had setup/import/email-fixture errors; those were
corrected without relaxing application checks before collecting the observations.

GitHub now confirms [run 43102150178][ci] **success** for this exact HEAD: tests,
dependency-audit and database-tests all succeeded. The workflow uses postgres:17.
The draft body still says hosted verification is missing; that warning is stale for
this reviewed commit. A future changed HEAD needs fresh verification.

## Findings requiring changes or an explicit contract decision

### P26-01 — High latent risk: checking/rotation still equates distinct case-sensitive accounts

**References:** [devices.py:104–121][normalization], [185–212][classify],
[215–249][rotate], [test_trusted_devices.py:98–104][case-test];
[unchanged backend:7–20][backend].

`issue()` now locks the Student UUID and requires the **exact stored username** and
current credential stamp ([147–182][issue]). That addresses mismatched issuance,
but it does not fix the other half of design finding F02:

- `_normalized()` calls `.casefold()`.
- `_classify()` returns `trusted` based on `_username_matches`, with no exact stored
  Student username/target-UUID comparison.
- `rotate()` uses the same classification and can rotate the device for a different
  case-sensitive target. The row's immutable `student_id` FK does not itself make
  classification account-correct.
- The supplied test explicitly expects `check(cookie_for_alpha, 'ALPHA')` to be
  trusted, without creating the distinct uppercase account.

**Observed on PG17:** created separate verified `alpha` and `ALPHA` students with
separate normalized email addresses; issue for `alpha`; checking for `ALPHA` returned
`trusted`, `selects_trusted_limits=True`; rotation for `ALPHA` returned `rotated`.
No passwordless login occurred: no view currently invokes this primitive. The risk
is choosing the wrong account's protection lane when 02B is wired in.

**Suggested regression:** create both real accounts and independently issue each
cookie; cross-check/rotate must not select trust, rotate or revoke the other account.
Test NFKC/whitespace according to the **actual** AuthenticationForm/backend semantics,
not a new case-insensitive policy. Bind classification to the immutable server-side
Student identity, not just a deliberately over-grouped attack-correlation key.

### P26-02 — Medium: new role guards do not cover PG17 MAINTAIN or every required UPDATE

**References:** [ownership.py:95–123][runtime-guard],
[boundary.py:24–43][auth-guard], [configure_auth_role.py:55–67][grants],
[role tests:459–534][role-tests].

Default provisioning is narrow: identity columns are not updatable and runtime
receives no rights. Positive and negative tests are valuable. The **drift detector**,
however, checks an incomplete set rather than the advertised exact allowlist:

1. PostgreSQL 17 includes the table privilege **MAINTAIN**, which allows operations
   including VACUUM, ANALYZE, REINDEX and LOCK TABLE. Neither new table guard enumerates
   it. [Official PG17 privilege documentation](https://www.postgresql.org/docs/17/ddl-priv.html)
   defines it; this is one reason PG16 results alone were insufficient.
2. The auth guard requires UPDATE on `current_digest`, but not all of
   `previous_digest`, `rotated_at`, `last_used_at`, `expires_at`; the LoginLimit check
   likewise does not require its `expires_at` UPDATE. Missing grants can pass startup
   and fail a later primitive rather than returning the promised boundary failure.
3. Auth excess REFERENCES/grant-option drift and one-table-only partial schema states
   also deserve explicit allowlist policy; older-schema tolerance must be intentional.

**Observed on PG17:** grant MAINTAIN on accounts_trusteddevice to runtime, then auth,
using the disposable migrator; each guard accepted the role. Revoke only auth's
UPDATE(rotated_at); `require_auth_role()` still accepted it. Grants were restored
between probes. No destructive maintenance operation was needed or attempted.
This is a configuration-drift gap, not a claim that the PR grants MAINTAIN by default
or that runtime can read student rows with it.

**Suggested regressions:** PG17 direct MAINTAIN grants on each support table must
cause the appropriate guard to reject; individually remove every required column
privilege; test unexpected REFERENCES/grant option and partial schema if forbidden.
Keep checks on actual separate connections, not superuser credentials.

### P26-03 — Medium integrity gap: rotation CHECK permits previous_digest=NULL with rotated_at set

**References:** [models.py:90–101][models],
[migration 0003][migration], [constraint tests:285–305][constraint-tests].

The intended rotation invariant is both previous_digest/rotated_at absent, or both
present with a different valid previous digest. PostgreSQL CHECK rejects FALSE but
accepts UNKNOWN. The second disjunct can evaluate to NULL when previous_digest is
NULL and rotated_at is non-NULL; the first disjunct is FALSE, so the total is UNKNOWN.

**Observed on PG17 as auth:** a row with valid owner/digests/dates,
`previous_digest=None` and non-NULL rotated_at was inserted successfully. Normal
`rotate()` writes both fields, so this is an incomplete database integrity promise,
not evidence of a reachable password bypass. The test covers the reverse malformed
pair (previous set, rotation time missing), but misses this NULL combination.

**Suggested regression:** test the full nullable-field truth table through actual SQL/
ORM INSERT and UPDATE. Require explicit non-nullness in the populated branch of the
constraint. Also decide whether the database's 31-day upper bound should enforce
exactly the agreed 30-day lifetime; normal issuance currently sets 30 days and signed
cookie validation independently enforces a 30-day maximum.

### P26-04 — Medium policy gap: password-reset issuance race is improved; forget-all freshness is weaker

**References:** [issue:147–182][issue], [revoke_all:256–268][revoke],
[revocation tests:353–434][revocation-tests].

The new Student lock and under-lock credential stamp check genuinely prevent an
issuance verified before a committed password change/reset from being recreated with
that old stamp. Supplied real-lock tests cover waiting issuers, revocation waiting
for issuance, concurrent rotation and rollback. Credit this fix to design F04.

But the stamp does not change on **forget-all without password replacement**. A
previously captured stamp can still issue after forget-all completes. The probe
`old_stamp → revoke_all → issue(old_stamp)` produced a trusted record. The code's
comment explicitly allows someone who knows the password to authenticate again;
that is different from proving an already-in-flight verification happened **after**
revocation. Do not describe row serialization alone as an epoch/fresh-admission barrier.

**Decision/test:** either define forget-all as removing only records whose issuance
committed before its ordering point, with clear UI/incident guidance, or add a proven
freshness/generation contract so pre-revocation proofs cannot create later trust.
For 02B, test an issuer that waits **behind** a password-unchanged revoke-all, not only
the existing opposite ordering. Still require credential reset for known-password
compromise. This is not a dormant endpoint exploit or a request to implement an epoch
on Claude's branch without agreement.

## Rotation, failure handling and existing auth: what is and is not verified

- Rotation is materially improved: `SELECT ... FOR UPDATE OF self`, expected-digest
  conditional UPDATE, no cookie for a lost update/grace result, and a 60-second
  previous-token grace. `Check.selects_trusted_limits` is true **only for current**
  evidence. Those behaviors and the real two-tab tests passed on PG17.
- Previous-token use after grace still deletes the record before exact target-account
  matching. More than one generation old becomes absent. A copied token remains portable;
  this is not hardware-bound identity. A delayed valid request beyond grace can still
  cause denial, and arrival timestamps are captured before lock waits. Add expiry-at-
  lock-acquisition and wrong-account replay tests before activation.
- A.19.C has contradictory wording: the earlier paragraph/table says grace is trusted,
  while its final rule and actual Check property say **unfamiliar**. Reconcile the
  spec. Distinguish grace seen before admission from `rotate()` returning grace
  **after** an already-admitted trusted request; do not hash twice or silently switch
  a completed request's quota lane.
- Device functions propagate DB errors. Missing/excess-grant tests show existing
  middleware returns 503 for its initial boundary check. No live login finalization
  invokes these functions, so a stage-specific 503/session guarantee is **not yet
  implemented**. Default fallback from an error to an unfamiliar/accepted login must
  not be added in 02B. Atomic auth-session persistence must include response-time
  SessionMiddleware behavior, not just `auth_login()` inside a transaction.
- The actual login, reset, change-password, registration and academic calculations
  are preserved. Existing 337 tests passed. Dormancy is deliberate: the compatibility
  test at [320–332][compat-tests] expects devices to survive current password flows
  until future integration. Do not call that production-ready device revocation.
- `issue()`/`_live()` currently enforce active status but not verified-email eligibility.
  Both assume trusted callers, not public authorization. Define verified eligibility
  and owned revoke-one/revoke-all adapters before adding routes; `revoke(device_id)`
  itself accepts just an ID. Existing login backend still rejects unverified accounts.
- No atomic **new multi-bucket counter** implementation exists here. LoginLimit is a
  schema; current source limiter retains its existing atomic upsert. New race tests
  must exercise actual 02B reservation/refund/finalization code when authorized.

## Mapping to all 12 independent design findings

| Design finding | PR #26 disposition at reviewed HEAD | Next requirement |
| --- | --- | --- |
| F01 failures consuming successful quota | A.19.A proposes release on failure; no counters integrated | Test failed, successful, in-flight, crash and later-window releases. Do not certify merely from design text |
| F02 case-sensitive binding | Issuance partially fixed; classification/rotation still wrong (P26-01) | Correct exact target/UUID binding and the test that currently expects casefold acceptance |
| F03 campus denial | A.19.B separates unfamiliar/trusted ceilings; schema still has `ip_ceiling` only | A new kind migration may be needed. Size/test real campus bursts; trusted floods can come from attacker-owned legitimate accounts, not only compromised accounts |
| F04 stale issuance/revocation | Password-change barrier improved and PG17-tested; forget-all policy remains P26-04 | Decide freshness semantics; automatic hasher-upgrade/reset race and complete session finalization remain 02B work |
| F05 concurrent rotation | Lock/CAS/grace improves it and tests pass | Resolve spec contradiction and grace-before-vs-after-admission; test delayed response/expiry/mismatch cases |
| F06 DB failure conflict | A.19.D now specifies rollback/503 on finalization failure | Actual exception handling/session persistence absent; test every failure boundary in 02B |
| F07 recovery independence | Not implemented, correctly outside 02A | Independent valid-proof redemption under saturated NAT/account limits, safe resends, real delivery/outage support before any hard gate |
| F08 cross-account deletion/caps | No cross-account deletion inside issue(); deletes/eviction scope the given Student | Preserve this improvement; public caller must authorize revoke IDs; test LRU and mixed-account lock behavior |
| F09 keys/schema/restore | Opaque IDs, max signed age, digest constraints and fallback support implemented | Independent device-key policy/retirement, restore invalidation and constraint/guard findings P26-02/03 unresolved |
| F10 logging bounds/dedup | Not implemented | Durable/bounded dedup and sink/cardinality limits; rollback-to-limit cannot alone make once/window event logging true |
| F11 enumeration/privacy | Not implemented beyond opaque payload | No identity prefill, no sensitive URLs/params; measure responses/timing without claiming constant-time SMTP behavior |
| F12 Codex recovery/compatibility complexity | Alternative proposal, not Claude implementation | No requirement to adopt that entire design. Choose accessible bounded recovery retries and explicit enabled/OFF-profile contracts before 02C |

Corrections documented for future work do not retroactively rewrite dormant behavior.
The incomplete old sections alongside A.19 should be consolidated by the implementer
so integration tests have one authoritative contract. This review does not edit S1.

## Suggested regression additions, in priority order

1. **Before foundation approval:** two real case-distinct accounts; wrong UUID/username
   classification and rotation; PG17 MAINTAIN drift; all required column-grant removals;
   NULL rotation truth table; exact expiry bound. These address P26-01/02/03.
2. **Before 02B:** explicit forget-all ordering contract; pre-reset/hasher-upgrade proof
   finalization; trusted/current vs grace admission; no valid cookie on a lost update;
   acquire-lock-after-expiry; wrong-account old-cookie deletion; mixed issuance/rotation/
   cleanup/revocation on multiple connections. Test both orderings with barriers and
   bounded waits rather than assuming one successful stress run proves no deadlocks.
3. **Counter integration:** failure must not permanently spend successful-session quota;
   successful logins must not drain failure quota; old-window refunds, duplicates,
   crashed workers, multi-bucket all-or-none, N+1 admissions, and separate 61/601-user
   source pools. Hard success restrictions need the same recovery approval discussion.
4. **Failure/privilege integration:** inject lookup/reserve/release/issue/commit/session-
   save errors and missing grants; no unadmitted hash, no new session/cookie on failed
   security finalization, only explicit retries of known rolled-back pre-hash units.
   Confirm all requests use runtime/auth, never migration credentials.
5. **Before 02C enforcement:** actual recovery under continuous account/IP attack,
   request/resend poisoning, token replay/expiry/concurrent consumption, same-browser
   nonce and cross-mail-client journeys, provider outage and accessible retry/opt-out.
   Preserve privacy and safe logging across provider/HTTP/worker/database layers.

## Disposition and limits

Positive PG17/CI results close the earlier **verification-environment** uncertainty
for this HEAD; they do not close the independently observed findings. Request targeted
revisions/tests for P26-01–03 and an explicit P26-04 contract decision. Keep the PR
and any schema rollout separate from permission to enable device/IP-bypass/account
restrictions. No fixes, commits, pushes or merges to Claude's branch were performed.
Only review documents are published by this assignment.

[ci]: https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43102150178
[normalization]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/devices.py#L104-L121
[classify]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/devices.py#L185-L212
[issue]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/devices.py#L147-L182
[rotate]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/devices.py#L215-L249
[revoke]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/devices.py#L252-L268
[models]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/models.py#L90-L101
[migration]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/migrations/0003_trusted_device_foundation.py
[auth-guard]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/boundary.py#L24-L43
[runtime-guard]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/academics/ownership.py#L95-L123
[grants]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/management/commands/configure_auth_role.py#L55-L67
[case-test]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/auth_tests/test_trusted_devices.py#L98-L104
[constraint-tests]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/auth_tests/test_trusted_devices.py#L285-L305
[compat-tests]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/auth_tests/test_trusted_devices.py#L308-L332
[revocation-tests]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/auth_tests/test_trusted_devices.py#L353-L434
[role-tests]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/auth_tests/test_trusted_devices.py#L459-L534
[tests-isolation]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/auth_tests/test_trusted_devices.py#L563-L575
[backend]: https://github.com/jordandavid1812-creator/university-command-center/blob/0e9e478fd4ed4249cbb81501a75ffda5e2744fd4/server/accounts/backends.py#L7-L20
