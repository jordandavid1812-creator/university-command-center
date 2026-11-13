# Post-B1c reconciliation and B1d owner-decision package

**13 November 2026 (Africa/Lagos). Documentation only. B1d NOT authorized.**
This report records the completed B1c merge and proposes decisions; it changes no
policy, code, grants, email backend or activation state. Open proposals remain
historical source documents, not executable work orders. Codex authored B1c and
this report; no independent approval is claimed.

## 1. Verified master and merge authority

The owner explicitly authorized only PR #58 at
`9e7f81606a06b4a0877fcbbb2a930a276d4ad4bb`, conditional on live checks. Before
merging, master was still `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6`; all four
head checks passed in [43427190382](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43427190382).
The supplied C1–C6 review approved that exact head, disclosing Claude's Revision5,
PR #57 and earlier review/test-hardening involvement. It was an **involved-author
review**, not verified organizational separation. No GitHub-submitted review or
new inline findings existed at inspection; the supplied review is conversation
evidence, not a fabricated GitHub approval.

The draft was marked ready, GitHub reported `mergeable_state=clean`, and the
normal merge API accepted the exact expected head using a merge commit. Branch
protection administration reads returned403; no protection was disabled, required
review dismissed, administrator override or force merge used.

- **Merge/current master:** `556738b221af050f5598bf5caaac45489f75363f`.
- **Parents:** `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6` and
  `9e7f81606a06b4a0877fcbbb2a930a276d4ad4bb`.
- The merge tree exactly equals the reviewed head (`git diff --exit-code` passed).
- PR #29 and dormant PR #26 merge commits remain ancestors; no substitution of
  rehearsal/evidence branches occurred. PR #58 is merged; no other PR was merged
  or closed by this work order.

### Actual push evidence, not substituted PR evidence

[Master run 43430204426](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43430204426)
reports event **push**, head exactly the merge above, completed/success. Its four
jobs and decoded logs were checked after completion:

| Evidence | Result |
| --- | --- |
| tests |113 legacy tests passed |
| database-tests |33 foundation +46 isolation +241 auth +91 website =411; with legacy, **524 regressions** |
| Additional website-root executions |27 B1a,34 B1b,44 B1c; these include mutation-runner cases, not additional unique regression counts |
| PostgreSQL |**17.12**, separated migrator/auth/runtime fixtures; historical foundation fixtures retain their existing DBA arrangement, not RLS evidence |
| Mutation scenarios |15 B1a +14 B1b +19 B1c =**48 detected**, none undetected |
| frontend-browser |10 UI1 +5 premium-auth +12 UI2 =**27 passed** |
| dependency-audit / drift |No known vulnerabilities; no migration changes detected |
| Failures/skips |No failed or skipped summaries in the inspected runs |

These are B1c baseline results, **not B1d implementation or complete remaining
A-matrix evidence**. The new documentation PR's exact-head checks are recorded
in its description, avoiding a new commit merely to embed its own CI SHA.

## 2. Live documentation PR disposition

Snapshot after the B1c merge. All four are **open, draft, unmerged**. GitHub reports
original base `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6`; their target is master,
now `556738b221af050f5598bf5caaac45489f75363f`. Their checked head runs are
historical pull_request runs, not current-master integration acceptance.

| PR / exact head | Complete changed files | CI / review evidence | Recommendation (not an action) |
| --- | --- | --- | --- |
| [54](https://github.com/jordandavid1812-creator/university-command-center/pull/54), `5a8429a456a0fe7d8be25c51dfc16fd5f6eb3753` | `docs/security/B1C_IMPLEMENTATION_PROPOSAL.md` |[43415021105](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43415021105), all four passed. Owner-supplied design APPROVE with identity limitation; Claude involved-author reviews; no submitted GitHub review. Codex authored proposal. |**Needs documentation correction/recheck before owner merge decision**: preserve the approved design as a historical snapshot, but identify B1c as implemented/merged and the later work order as implementation authority. Do not leave “implementation NOT authorized” looking like current project status. |
| [55](https://github.com/jordandavid1812-creator/university-command-center/pull/55), `715ef7e7582ac9ea8c75d485eebd9ff5f38af584` | `docs/security/B1D_IMPLEMENTATION_PROPOSAL.md` |[43384192126](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43384192126), all four passed. No submitted review/owner comment returned; Codex-authored proposal, not independent approval. |**Needs corrections/review; blocked on owner wording/scope decisions**. Baseline484 and “no classifier implemented” are historical. Keep its full matrix; use this report as a readiness addendum, not a silent replacement. |
| [56](https://github.com/jordandavid1812-creator/university-command-center/pull/56), `9ab7f82c380e4cfd3ecb4198239a8f7932554adb` | `docs/security/SECURITY_ACTIVATION_READINESS.md` |[43384208874](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43384208874), all four passed. No submitted review/owner comment returned; Codex-authored. |**Needs separate design review/status reconciliation**. B1c is now merged, but B1d and protocol/recovery/operational prerequisites remain incomplete. No activation approval. |
| [57](https://github.com/jordandavid1812-creator/university-command-center/pull/57), `ef661d0cd984334101944b42f16c54abfeaaa582` | `docs/security/B1C_CLASSIFICATION_DECISION_RECORD.md`; `docs/security/STAGE_B_IMPLEMENTATION_PLAN.md` |[43398287666](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43398287666), all four passed. Claude authored it and Revision5; no submitted review/owner comment returned. |**Superseded competing record; recommend closure without merge only if separately owner-authorized**. Preserve its provenance links. Alternatively owner can request a narrow corrected archival record, not merge its superseded classifier guidance. |

All four `git merge-tree --write-tree <master> <head>` checks returned clean text
merges. **That is not runtime or policy safety evidence.** None of their new
proposal files is in master; only #57's existing Stage B path is already present,
with its proposed changes still unmerged. No PR is falsely reported implemented
because its planning topics overlap merged code.

### D-B1-6 authority reconciliation

Keep the exact original policy quotation in
[canonical #54](https://github.com/jordandavid1812-creator/university-command-center/blob/5a8429a456a0fe7d8be25c51dfc16fd5f6eb3753/docs/security/B1C_IMPLEMENTATION_PROPOSAL.md)
unchanged. In particular:

> Return HTTP 500 for reachable programming defects except the existing role-boundary contract.

Revision5 §6.4 separately says “Programming errors at the role check stay 503.”
Do not insert “handling” into the owner's quotation to match explanatory wording.
The [owner confirmation #6851072382](https://github.com/jordandavid1812-creator/university-command-center/pull/54#issuecomment-6851072382)
confirms the seven principles and later academic-wrapper503, existing400,
query/template-independent new500/503, synthetic Retry-After5/1–300 and guarded
node.sqlstate clarifications. That comment is design-only; the later explicit
work orders separately authorized implementation and this exact merge.

#57's class-first plus diag fallback, broad truncated-chain prohibition,
classifier-error-to-unproven fallback and “no duplicate django.request” guidance
must not overwrite the implemented guarded instance-read/minimal500/sanitized
framework-record contracts. Genuine deletion also does not prove every DB query
will work. Retain provenance, not conflicting instructions. Stage B §6.14 still
uses historical “Approve” decision-request wording; it is not evidence that the
owner's confirmed D-B1-6 remains pending.

No existing proposal or shared plan is rewritten here: resolving those branches
needs separate authority. A single cross-PR addendum avoids conflicting edits and
points to canonical source instead of duplicating their complete specifications.

## 3. B1d proposal — decisions required BEFORE implementation

Use [merged Revision5](STAGE_B_IMPLEMENTATION_PLAN.md) §§6.1–6.14,
[actual B1c evidence](B1C_IMPLEMENTATION_EVIDENCE.md), and the full matrix in
[PR55 at its inspected head](https://github.com/jordandavid1812-creator/university-command-center/blob/715ef7e7582ac9ea8c75d485eebd9ff5f38af584/docs/security/B1D_IMPLEMENTATION_PROPOSAL.md).
The following is proposed wording/scope, **not owner-approved copy**.

| ID | Exact trigger | Exact proposed text |
| --- | --- | --- |
| W1 | Resolved `accounts:reset-confirm`, POST, B1-handled DB-origin500/503, whether before, during or after an uncertain write | We could not confirm whether your password changed. Try signing in with the password you submitted. If needed, request a new reset link. |
| W2 | Resolved `accounts:verify`, POST, same DB-origin failures | We could not confirm whether verification completed. Try signing in. If verification is still required, request another verification email. |
| W3 | Resolved `accounts:password-change`, POST, same DB-origin failures | We could not confirm whether your password changed. Sign in again using the password you submitted. If needed, use password recovery. |
| W0 | GET/form-load failures for those resolved routes | This page is unavailable. Try again later. |
| W4 (additional target requiring explicit approval) | Existing web-root `student_web.views.server_error` on those three resolved POST routes after a non-DB failure | Select the corresponding W1–W3 text, retaining its existing500/template route; replace only its false “operation could not be completed” claim. All other routes remain unchanged. |

W2 is explicitly **POST only**, narrowing #55's ambiguous “verification request”
phrase. GET cannot claim a submitted password or completed verification attempt.
Confirm these triggers and exact text, including recovery advice, with the owner.
No automatic resubmission, success/failure assertion or recovery-delivery promise.
The default auth-root non-DB500 already makes no completion claim; preserve it.
W4 is outside the original accounts-only wording target and must be approved
explicitly or redesigned/reviewed before implementation, not hidden in B1c routing.

### Narrow code boundary for a future authorized PR

- Pass only a fixed operation-group label from already-resolved, allowlisted view
  names and method; no raw path/token kwargs, new URL resolution, reverse, headers,
  username lookup, request.user/session/messages or database reads for selection.
  Renderer accepts constants/group, not a request object or untrusted free text.
- Change only the applicable B1-generated body variants; status, category,
  no-store/charset, valid OUTAGE-only Retry-After and safe runtime-header omission
  remain. A classifier failure with no proven DB origin keeps B1c generic500;
  route copy must not invent provenance or change classification.
- Preserve successful messages/redirects, validation/form errors, invalid/expired
  token400, CSRF403, existing429 contracts, generic registration/email requests,
  role-boundary503, academic wrappers and existing400 rendering.
- W4, if approved, is a wording-only change to the existing handler, with its
  existing template risks; do not claim that it has B1's zero-query guarantee.
- No session engine, Student/token locking, transaction/CAS, device, quota,
  privilege, migration, logging policy or academic change. If new copy cannot be
  implemented within this boundary, stop for revised scope.

### Complete remaining failure-matrix gate

Existing tests are partial evidence, not labels that certify every cell. A future
PR must produce a manifest per applicable flow × phase × entry state, naming the
actual test/subcase, mechanism, SQLSTATE/driver class, O1–O4/CK assertions and result.
Use symbolic fixture labels/booleans/counts, never raw cookies, hashes or tokens.
N/A needs a lifecycle reason; it is not a skipped required test.

| Flow | Remaining/full required evidence beyond B1c's nominated subset |
| --- | --- |
| A1 login success | Rerun N,AN,SA,SX,DA; retain cycle counts, same-key versus replacement, explicit finalizer observations and response UPDATE(N/AN/SA)/INSERT(SX/DA). |
| A2 login | Full L0–L3 across all five states: throttle real statement error and dispatched/post-execute loss, Student lock, last_login/pre-COMMIT and termination/real-COMMIT-then-error. L4u/L5u only N/AN/SA; L4i/L5i only SX/DA; prove actual statement/handler, row authority/expiry and no new delivered key. L6 transport/header handoff is observation under CK5, not a retroactive no-cookie promise. |
| A3 reset | N and SA, S1/E1–E4: real Student/token/throttle locks as applicable, statement failures, termination and real committed acknowledgement loss, confirmed commit/later error. Assert password+nominated-token pair through fresh observers; distinct secrets and same-plaintext reset separately. Other tokens are not assumed consumed. |
| A4 verify | N, E1–E4: Student/token and email_verified_at write faults, uncertain COMMIT and confirmed update/later failure; verified iff nominated token consumed; never authenticates. GET read failures use W0. |
| A5 change | SA C0–C4: lock, flush DELETE fault, deletion header with valid server key after pre-COMMIT rollback, uncertain and committed cases, other-session hash validity. Same W3 for possible outcomes, no compensating writes. |
| A6 issuance | N E1/E3 and confirmed outcomes: old-link revocation/new-token commit may occur without on_commit email callback; count synthetic deliveries separately. Generic wording is not proof of mail delivery. No new provider/outbox semantics. |
| A7 registration | Generic handled IntegrityError, success/invalid-form contracts, no authenticated authority or invented mail-delivery claim. |

Record O1 issue/renew/delete/none, O2 resulting browser jar, O3 committed **valid**
sessions and orphan rows, O4 prior keys internally. Assert CK1 no new non-empty
issue/renew, CK2 no newly acquired authority, CK3 prior validity/expiry against
the phase oracle, CK4 orphan enumeration; retain legitimate deletion. SA may
retain/renew K; DA rollback may retain A; SX already had invalid authority. CK5
explicitly excludes a no-response/post-header delivery guarantee.

Distinguish autocommit S0–S3 (including implicit commits with zero `_commit` calls)
from atomic E0–E4. Read final state only after controlled transactions finish via
clean restricted auth observers. No outcome follows from500/503/400 alone.
Pre-dispatch backend termination proves that observed rollback case, not uncertain
COMMIT coverage. Require a positive persisted control that calls **real** COMMIT
then raises, plus controlled concurrent termination/network probes reporting the
actual dispatch/acknowledgement boundary and allowed committed/rollback outcomes.

Real PostgreSQL17, separate roles, forced RLS and both URL roots are mandatory.
Keep real55P03/57014/25P03, negative grants/MAINTAIN, connection reuse and cleanup,
unknown SQLSTATEs, zero-query rendering/fallback headers, process controls and
final-sink sentinels. Compare known/unknown status, side effects and timing
observations without declaring enumeration resistance from constant text.

Mutation controls must detect wrong GET/POST/route text, false success/rollback or
password-unchanged claims, phase-based certainty, stripped deletion, false prior
revocation/orphan assumptions, incorrect DA INSERT behavior, new authority,
password/token non-atomicity, fake post-COMMIT control and added retries. Each needs
baseline success, actual production-path exercise, assertion failure (not an
infrastructure error), no skip, bounded completion and restoration.

Acceptance: complete manifest, all current524 regressions plus genuine additions,
27 browsers, existing15/14/19 controls, website-root suites, audit/drift/privacy,
exact-head CI and separately disclosed code review. No B1-complete claim before
that gate. Rollback only wording/tests to accepted B1c; no data/migration reversal,
credential compensation or retry. That rollback restores less precise wording,
not production readiness.

## 4. Deferred work: concrete separate slices

### Academic wrappers

[accounts.views.academic_errors](../../server/accounts/views.py) converts every
caught Django DatabaseError, including defects, to JSON503 on the academic API.
[student_web.views.protected/error_page](../../server/student_web/views.py)
converts them to a templated503 and may itself fail when rendering needs a DB.
C3 now tests the web compatibility exception, including42703; that is evidence
of preserved behavior, **not proof of a safe outage renderer**.

**Recommendation:** retain the confirmed B1c compatibility behavior during B1d.
Do not treat that as indefinite production risk acceptance. Propose a separate
wrapper-security design after B1d: reuse classification at the caught boundary,
minimal database-independent500 for defects and503 for proven availability/
configuration, while preserving JSON/HTML client contracts, service-error statuses,
CSRF/ownership and no new reads. Owner must approve changing the current exception
and response-format contracts before code. Test all protected routes/methods,
42703/42P01/55P03/42501/no-driver chains, failed rendering, no-store, enumeration,
query budgets and final sink; negative controls must distinguish wrong generic503
from correct routing. No auth transaction or academic formula changes.

### C5 test-hardening slice

B1c's C5 remains explicit deferral, not an unnoticed completed gate. Recommend a
small **test-only** PR, with owner scheduling approval, adding three production
mutants restored in memory/disposable copies:

1. Wrong UPDATE/INSERT handler: drive actual N/AN/SA update and SX/DA exists/insert
   paths; redirect application adapter behavior with correct signatures, so
   Django-only400 versus500 and statement/handler hit assertions fail. Do not
   count a TypeError from an invalid mock signature as detection.
2. Wrong COMMIT hook: prove the real auth connection/transaction is exercised and
   real-COMMIT-then-error persists through a fresh observer. A production no-op or
   wrong-connection commit must fail the persisted-state assertion, with cleanup
   closing failed connections/locks; no fake post-COMMIT evidence accepted.
3. Added retry: introduce a bounded retry in a disposable production path; assert
   attempts/writes/hash calls and already committed throttle/CAS units, rejecting
   duplicate security writes or authority. Do not weaken statuses to allow retry.

Existing B1a commit/retry controls and B1c response tests remain useful but are not
claimed equivalent to these omitted adversarial scenarios. Apply the same
baseline/exercise/assertion/error/skip guards and fail on a no-op/unexercised mutant.
Do not alter canonical production behavior. The owner can instead explicitly
retain deferral; no such new decision is presumed here.

## 5. Remaining security dependencies — dormant until separately authorized

| Area | Actual current state | Unfinished requirement / decision |
| --- | --- | --- |
| Completion | B1a/B1b/B1c merged; B1d not implemented | Full B1d matrix/copy and review before B1 completion or accepted staging release |
| Transaction/session protocol | PR29 CAS/hash revalidation and Django response saves remain; B1c observes outcomes | B2 must handle explicit T2 save, all five states, later SessionMiddleware writes and cookie delivery. Clearing session.modified alone can suppress Set-Cookie; COMMIT is never atomic with HTTP delivery. |
| Lock order | devices.py uses Student→device; recovery uses Student→AccountToken. StageB I8 proposes Student→device→token→sorted counters | S1 A.20 updates success/release counters before rotate/issue. Review one unified pre-lock/settlement schedule, including revocation/recovery/cap eviction, and test PG17 deadlocks before future implementation. atomic alone does not reconcile conflicting orders. |
| Quotas/identity | Current AuthThrottle counts **all** login attempts before password verification; LoginLimit is schema-only | Failures must never consume successful-session allowance. Older reserve/refund-success text conflicts with A.20's T2 committed-success accounting. Exact account identity must follow existing normalization/exact lookup and immutable UUID, not merge case-distinct accounts. Resolve crash/overcount/DoS and same-window release semantics. |
| Device HTTP integration | Primitives only; no calls from login/backend/reset/change, no live cookie writer or bypass/enforcement settings | Separately review default-off wiring and owner eligibility, HttpOnly/Secure/SameSite/path/host, one-account browser slot,30-day lifecycle/10-device cap/60-second grace and rotation loss/replay. A cookie never authenticates or gives unlimited guessing. |
| Generation/revocation | Student-locked application increment/issuance barrier; auth has UPDATE(generation), no DELETE/TRUNCATE | Direct auth SQL can decrease a nonnegative generation; DB monotonicity is not proved. Decide threat boundary and any forward hardening separately. Reset/change revocation is not wired. Single revoke(id) is not an owner-authorized endpoint. Test revoke-all/in-flight issuance, key retirement and restore resurrection before activation. |
| Schema taxonomy | LoginLimit kinds include only one ip_ceiling | Proposed trusted/unfamiliar source lanes need reviewed domain-separated keys or an explicitly approved forward migration; never edit/fake0003 history. |
| Recovery/email | Existing issuance revokes old links; E105's exact-class backend approval list remains empty; no real transport approved | Reliable approved transport plus verification/support, independently bounded redemption, coalesced/non-invalidating issuance, replay/expiry/concurrent recovery, email-outage and token misuse tests. Requesting recovery never grants trust. |
| Campus/NAT | Existing10-per900s login throttle and IPv6/64 source grouping remain; trusted proxies empty | Measure finite trusted/unfamiliar ceilings and aggregate stolen-cookie guessing limits. Shared NAT can still deny legitimate students; never treat a campus NAT as a trusted proxy. No universal60/600 thresholds; optional daily100 limit remains deferred. |
| Privacy/monitoring | B1b fixed sink and B1c classified events; event is not delivery acknowledgement | B3 reviewed pseudonym key, bounded retention/sink/alerts/drop accounting, raw server/proxy/bootstrap/command/email channels and operator access. External retention is not implemented by design text. |
| Stage C / recovery operations | No deployment or provisioning performed here | Provider PG17/pgcrypto/TLS/forced-RLS/role/MAINTAIN compatibility, exact secure-profile preflight(E101–E105), proxy deadlines from measurement, migrations/provisioning window, encrypted backup and independent restoration drills, secret/key rotation, privacy/cohort/support and operational rollback evidence. |

The stale rollback/no-session/no-cookie assertions in
[S0_02_RECONCILIATION](S0_02_RECONCILIATION.md) and older S1 sections cannot override
S0–S3/E0–E4/CK5. Proposed flags, observe/enforce lanes and structured event types
are **not implemented switches**. No cookie issuance, hard account restriction,
IP bypass or automatic fail-open is authorized by this report. B1d completion
would still not authorize any of them or approve email transport.

## 6. Owner decisions and exact next action

| Decision | Recommendation / current status |
| --- | --- |
| Documentation #54 | Authorize a historical-status banner/update and focused recheck, then decide its exact-head merge separately |
| Documentation #55/#56 | Authorize status reconciliation and separate design review; no merge or execution yet |
| Competing #57 | Authorize closure without merge after preserving canonical54/owner-comment provenance, or request a corrected archival alternative |
| B1d W0–W3 | Approve/revise exact text, POST/GET triggers and narrow provenance/constant-group scope above; pending |
| B1d W4 | Explicitly approve the wording-only existing web500 target or request a reviewed alternative; pending |
| C5 | Schedule the small test-only slice or explicitly continue deferral; pending scheduling/risk decision |
| Academic wrappers | Retain B1c exception during B1d, separately commission correction design before launch; not new indefinite risk acceptance |
| Future activation/operations | Separate protocol, provider/email/privacy, thresholds/cohort and exact activation work orders; all pending |

**Next safe action:** review this documentation PR, resolve the B1d copy/W4 and
scope decisions, then issue a separate, bounded B1d implementation work order.
Do not start B2/device/counter integration to “help” B1d. Each later implementation
needs its own draft PR, real restricted PG17 evidence, disclosed review and owner
exact-head merge decision. Only PR58 merge was authorized and executed here.
