# Package B — B1d wording and complete failure matrix

**DESIGN ONLY. No implementation/merge/activation approval.**
Base `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6`. B1a/B1b are merged. All four
jobs in master push [43380783580](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43380783580)
passed on PostgreSQL 17.12: **484 regressions**, **27 browsers**, additional
website-root **27/34**, existing mutations **15/14**, no skipped/failing summaries.
455 is the historical pre-B1b total, not the current preservation target.
Proposal CI is baseline compatibility, never execution of the planned B1d matrix.

Use [Revision 5 §6.1–6.14](STAGE_B_IMPLEMENTATION_PLAN.md),
[B1b evidence](B1B_IMPLEMENTATION_EVIDENCE.md) and the approved
[privacy amendment](B1B_LOGGING_DESIGN_AMENDMENT.md). Package A/B1c must be separately
reviewed, authorized, implemented, accepted and integrated first. D-B1-6 is not
approved by this package. B1d does not repair or redefine B1c routing policy.

## Threat model and actual behavior

A timeout/lost response can follow a completed security write. “Failed” and
“rolled back” are therefore unsafe generic UI claims. Conversely a credential
change may genuinely roll back; reporting success would mislead a student.
Cookie deletion is not server revocation; previous SA authority can survive or
renew. A DA switch rollback can preserve A. Response saves can create undelivered
valid rows. These are existing semantics, not defects B1d may silently change.

Actual accounts/views.py resets password and consumes the nominated token in one
auth transaction, then logs out and renders a success message. Verification uses
tokens.verify_email with Student/token locking. Password change locks Student,
updates the hash, flushes the current session and redirects. Login still has
response-phase SessionMiddleware saves, not a new explicit-session B2 protocol.
No failure wording/classifier for B1c/B1d is yet implemented. B1a/B1b observations
are partial failure evidence, not coverage of all cells below.

## Minimal future wording change inventory — owner review required

Select text only from fixed route names (`accounts:reset-confirm`, `accounts:verify`,
`accounts:password-change`) and already chosen error variant. Never inspect a
selector/secret, account existence, password, query string or Referer to choose copy.
Do not infer commit outcome from category, status or missing COMMIT acknowledgement.

| ID / exact trigger | Proposed fixed wording and location |
| --- | --- |
| W1: reset-confirm POST, B1-handled DB-origin 503/500, any phase E0–E4 | “We could not confirm whether your password changed. Try signing in with the password you submitted. If needed, request a new reset link.” Replace only this route group's B1c failure_response body constants; preserve status/headers. |
| W2: verification request, B1-handled DB-origin 503/500, including later response failure | “We could not confirm whether verification completed. Try signing in. If verification is still required, request another verification email.” Fixed failure_response variant; no claim that the token is still usable. |
| W3: password-change POST, B1-handled DB-origin 503/500, C0–C4 | “We could not confirm whether your password changed. Sign in again using the password you submitted. If needed, use password recovery.” Fixed failure_response variant; do not promise old sessions are invalid. |
| W4: existing web handler500 for those same three resolved routes after a non-DB post-commit failure | Its current server_error text says the operation “could not be completed”, which can be false after commit. Propose the corresponding W1–W3 uncertainty text **within that existing handler**, preserving its routing/status/render path and other routes. This is a narrow additional wording-only file target requiring explicit owner approval below, not a B1c classifier change. |
| Preserved cases | Successful reset message “Password changed. Please log in again.”, successful verify “Email verified. You can now log in.”, password-change redirect, valid GET forms, invalid/expired-token 400, validation errors, registration and generic recovery-request behavior stay unchanged. A confirmed-success path still confirms success. |

An unavailable login/recovery path is a deployment dependency, not an excuse for
automatic resubmission or false outcome claims. GET/form-load failures must not
say a password was submitted: keep a separate neutral fixed read-only error
variant (“This page is unavailable. Try again later.”). Test GET versus POST.
A direct unknown/unresolved route handler500 keeps the existing generic contract;
no guessed account-flow copy from raw paths. Handled role-boundary/configuration
503 remains its truthful existing response. No new cookie/session behavior.

**Pending owner decisions:** approve W1–W3 exact text and GET/POST triggers;
approve W4's wording-only `student_web.views.server_error` target beyond R5's
initial accounts/template list, or provide a separately reviewed way to avoid its
false completion claim. This conflict cannot be hidden by reclassifying a non-DB
error or changing status. No implementation starts until the wording budget is
resolved. No approval of backend, transport, new reset-token semantics or broader
academic-page redesign. The generic issuance message is not delivery evidence;
provider/outbox semantics and any separate generic-email-copy correction belong
to B7/recovery work, not a silently broadened B1d.

## Exact matrix and observations

Every applicable cell records **O1** response-cookie actions, **O2** browser jar,
**O3** committed valid session rows on a clean connection, and **O4** prior keys.
Record status/body variant/no-store/Retry-After and final sanitized sink bytes.
Never print keys, tokens, raw usernames/IPs, hashes or paths in evidence artifacts.

| Invariant | Required assertion |
| --- | --- |
| CK1 | No non-empty issue/renew header on a pre-header handled failure; legitimate delete/expire headers retained, including required C2 deletion. |
| CK2 | After processing that response no authority from a new key outside prior K_prev; prior authority may remain. |
| CK3 | Prior-key user/validity/expiry follows the per-unit phase oracle, not status or assumed revocation. |
| CK4 | Enumerate valid undelivered/orphan rows separately. N/AN L5u and SX/DA L5i can leave them; SA L5u is renewal of a held key, not an orphan. |

CK5 boundary: after headers/no response, record what the client actually received;
do not promise no cookie or undo delivered authority. Post-header faults are
observation tests, not covered failures that B1 can retroactively repair.

| Flow | Complete cells and source-specific assertions |
| --- | --- |
| A1 success baseline | All N/AN/SA/SX/DA. N/AN cycle once; SA/SX/DA do not. Finalizer rows N/AN/SA 1, SX/DA 0. SA keeps K; others replace it. Response UPDATE N/AN/SA, INSERT SX/DA. Successful behavior unchanged. |
| A2 L0–L3 | All five states: real throttle failure + post-execute acknowledgement loss (S1/S3), Student lock L1; statement fault and pre-COMMIT L2; controlled termination around dispatched COMMIT and real-COMMIT-then-error L3. Track throttle/CAS S0/S1/S2/S3 separately from finalizer E0–E4. SA key/expiry unchanged before commit; DA rollback preserves A, creates no B row. |
| A2 L4u/L5u | N/AN/SA only: actual session UPDATE lock, 42703/42P01 defect, pre-save rollback and post-real-COMMIT acknowledgement loss. N/AN can have anonymous row before response UPDATE; committed authenticated row can be orphaned. SA keeps K, no orphan; L4u expiry unchanged, L5u renewal allowed/recorded. |
| A2 L4i/L5i | SX/DA only: exists SELECT and INSERT failures before commit; real INSERT commit then error. SX stale prior key was already invalid; DA prior A deletion committed. L4i has no replacement; L5i may leave one undelivered authenticated row. Never incorrectly test these through handler400. |
| A2 L6 | All five states, headers/transport loss: record delivered-key possibilities and successful session validity; CK5 explicitly limits guarantees. Inapplicable UPDATE/INSERT state pairs are marked N/A with lifecycle reason, not silently skipped. |
| A3 reset | N and SA: real 55P03/S1/E1, injected statement E1, controlled real termination and post-real-COMMIT error E3, confirmed commit/later error E4. Password+nominated-token atomic pair; compare distinct submitted/old secrets. Also same-plaintext reset: old plaintext may still verify, while encoded-hash/session validity must be observed separately. Other tokens are not claimed consumed by this unit. No new authority. |
| A4 verify | N: Student/token statement failures E1, email_verified_at update failure, uncertain E3 and confirmed-state follow-up. Verified iff nominated token consumed; verification never logs the user in. W2 cannot imply usable token after a completed verification. |
| A5 change | SA, C0 lock/validation; C1 flush DELETE; C2 after flush/pre-COMMIT; C3 real/injected uncertain COMMIT; C4 confirmed/later failure. C2 browser cookie deleted while server K and other old sessions can remain valid. C3 union: committed new hash + deleted K, or rollback state; C4 old-hash sessions invalid. W3 identical across possible outcomes. |
| A6 issuance | N, E1 and real-COMMIT-then-error E3: nominated new token/older-link revocation can commit without email callback. Count deliveries with synthetic backend; do not equate status, token creation or generic message with delivery. No automatic retry or trust from merely requesting recovery. |
| A7 registration | N, handled duplicate IntegrityError unchanged generic response. Registration cannot grant authenticated authority; no invented new account or email success on error. |

B1c owns its nominated A2/A5 status-changing cases; B1d must rerun them and fill
**all** remaining matrix cells. Build a coverage artifact naming flow, phase,
entry state, real/injected mechanism and assertion set. Existing functional and
race tests are retained, not renamed as complete matrix coverage without evidence.

## Execution, negative controls and acceptance

Real PostgreSQL 17, separate migrator/auth/runtime LOGINs and forced RLS. Real
blockers/SQLSTATEs and bounded schedules, fresh observers after transactions finish.
The migrator may create/restore disposable fault fixtures; never use it as a web
alias. A pre-COMMIT hook/statement exception proves rollback only, not uncertain
commit. Require the R5-T1 positive persisted control with real _commit then raise;
record whether real termination was controlled before/after COMMIT dispatch.
Do not claim deterministic server outcome from network loss alone.

Mutate false “rolled back”/“password unchanged” and false success wording; wrong
GET/POST variant, phase/status-based copy, stripped cookie deletion, unconditional
prior-key invalidation, SA orphan assumptions, DA finalizer INSERT assumptions,
new response-issued keys, missing token/password pair atomicity, fake post-COMMIT
fault and added write retries. Require exercised real production mutations with
passing baselines, assertion failures (not infrastructure errors) and cleanup.
Retain R5-T2, B1a 15/B1b 14 controls, Package A B/C negatives and all B1c additions.

Accept only with current 484 regression floor (plus genuine additions), all 27
browsers, additional website-root suites, PG17 restriction/isolation/MAINTAIN tests,
migration drift, dependency audit, B1b sentinels on every new failure route,
complete applicable matrix, exact-head CI and independent code review. Existing
historical assertions are not weakened; any deliberately approved presentation
assertion change must have explicit owner evidence. Documentation CI proves none
of these new behaviors. No skips hidden as matrix exclusions.

Future files: fixed failure_response text, minimal accounts view/template wording
where a current trigger actually needs it, the specifically approved W4 text
selection if accepted, tests/docs. No session engine/transaction refactor, account
policy, privilege/migration or academic formula change. If false wording cannot
be fixed within the approved targets, stop for a revised work order.

## Rollback and residuals

Revert wording/matrix additions and restart to the accepted B1c build; no database
rollback or compensating credentials. That reintroduces less precise copy, so it
is not launch-safe by itself. Uncertain commit/delivery, prior legitimate authority,
orphans, resource/fatal/post-header output, email availability and enumeration
remain. B1 completion still does not accept Stage C/D operations or account
restrictions. No trusted-device activation is part of B1d.

Independent review requested from a separate reviewer; Codex authored this proposal
and B1b and does not provide independent approval. After design/wording approval,
obtain a separate B1d implementation work order, then review/CI and exact-head owner
merge approval. No phase is activated by merging a documentation proposal.
