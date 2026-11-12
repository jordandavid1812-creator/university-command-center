# Independent S0-02 security architecture review

**Decision for ChatGPT review: neither proposal should be implemented unchanged.**
Agree the admission/issuance invariants, resolve the High findings below, and review
the dormant S0-02A schema against those decisions before authorizing code. This is
an architecture review, not a penetration-test result or implementation approval.

## 1. Scope, provenance and limits

Reviewed 11 November 2026. Application baseline/master:
`64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb` (PR #25).
Review branch: `docs/s0-02-independent-review`, in a separate worktree.

| Evidence label | Exact source |
| --- | --- |
| **C** | Claude's `docs/security/S1_PROPOSALS.md` at remote branch `claude/upbeat-clarke-prrzc0`, fetched HEAD `e161be87a2aacb6cb54eff43041c1fb3ea1f375d`; SHA-256 `4db96cac1675d4e5325c1ddd7c1b64042dbea86c0db086ffed79b45cb481e777` |
| **D** | Codex's uncommitted local proposal on `docs/s0-02-auth-design`, baseline above; SHA-256 `62eb0a4114744b5e22e39291ef8108285b01c1447b2c29952d2325d3ba787dc8`; original path `/workspace/university-command-center/docs/security/S1_PROPOSALS.md` |
| **B** | Actual application/configuration/test code at the pinned master commit; source links below |

D is **not** the S1 file checked into master or this review worktree. D citations
refer to that preserved local snapshot's numbered sections, with relevant text
quoted here. C links pin its commit so a later branch edit cannot alter evidence.
The remote C/master content difference is only S1_PROPOSALS.md; C contains no new
authentication implementation to execute. Neither proposal file was edited during
this review. Only this report is the proposed review-branch change.

Method: source/contract comparison, manual counter traces and race interleavings;
read the actual auth backend, views, tokens, role provisioning, boundary middleware,
router and existing tests. Inspected Django 5.2.19's installed supported password
verification behavior. **No new S0-02 application code, migrations, test code or
runtime exploit tests were written or run.** Findings about C/D are consequences
or gaps in their documented contracts, not claims that S0-02 bugs are deployed.

Severity is contextual: **High** means a plausible protection bypass, significant
login denial or contradictory security invariant to resolve before the relevant
implementation; **Medium** means a material risk/design gap requiring resolution
before enforcement. Preconditions and certainty are stated. No Critical finding
is claimed. An explicitly documented residual risk is still evaluated, but is not
misrepresented as something an author failed to acknowledge.

## 2. Protections both designs support

C §§A.0–A.4/A.8–A.10 and D §§A.1–A.4/A.7–A.9 agree on:

- Device evidence never authenticates by itself; password, active/verified eligibility
  and the existing session/principal checks remain required.
- Initial 30-day device lifetime, one remembered account per browser, HttpOnly/Secure
  HTTPS cookies, a SameSite policy and purpose-separated signatures. Both avoid raw
  username/password/session material in the device cookie.
- Stateful digest-backed devices, bounded device counts, expiry, own-account revoke-all,
  and revocation tied to credential replacement. Both admit copied cookies are portable.
- Trusted-device IP bypass is conditional, with per-device and cross-device account
  budgets plus infrastructure controls. Clearing cookies or changing IP must not create
  more trusted allowance for one account merely by changing browser presentation.
- Commit admission before password verification; do not hold quota locks throughout
  expensive login hashing. Correct passwords cannot bypass an enforced exhausted gate.
- Unknown/known identifiers need generic responses and privacy-preserving bucket keys.
- Reset requests/link GETs alone must not grant trust. Successful recovery needs
  one-use proof, expiry, purpose/credential binding and concurrency protection.
- Hard unfamiliar-account enforcement is gated on real recovery/email verification.
  Both acknowledge sustained targeted unfamiliar-browser lockout remains possible.
- Separate restricted auth/runtime database connections, no academic RLS weakening,
  no migration role in requests and actual PostgreSQL 17 verification before merge.
- Minimal secret-safe events and bounded retention, observation before enforcement,
  and deferral of the optional 100/day account cap.

These are important shared intentions; the findings identify where a detailed
algorithm contradicts or falls short of those intentions.

## 3. Important differences, without an author preference

| Topic | C | D | Assessment |
| --- | --- | --- | --- |
| Counting | Refund failure reservations after success; separate success/session quota | All admitted checks count, no refunds; no separate success quota | C can better accommodate successful traffic if corrected; D is simpler to reason about but spends capacity on legitimate checks too |
| Network ceiling | Failure-only ordinary source bucket, plus 60 all-attempts/15 min for every lane | Retains 10 submissions/15 min for unfamiliar sources; unspecified reviewed perimeter controls for all | Both can deny campus users; D's retained ordinary threshold is especially restrictive |
| Account identity | NFKC plus casefold, including device `username_key` | Authentication's bounded normalization, preserving case; explicit account binding | C's casefold is not merely conservative when used to validate device ownership (F02) |
| Trusted budgets | 5 device failures/15 min, 20 trusted-account failures/15 min, 20 account successes/hour | 5 device checks/15 min and 10 trusted-account checks/15 min per epoch | Values and meanings differ; neither should be assumed approved or operationally suitable |
| Device primitive | Opaque 256-bit ID, digest only, signed with Django secret + purpose salt | Selector + validator + opaque account reference + explicit key/audience/mode/expiry; independent device key | C has a smaller cookie/primitive. D has narrower key scope and richer revocation, but more protocol and privacy complexity |
| Rotation | Rotate on every successful login; previous-ID presentation deletes the record | Explicit fresh-password renewal; stable selector/validator; signed old copies retain old expiry | C detects some replay but confuses concurrency with theft; D tolerates concurrency but does not detect copied current evidence |
| State/revocation | Two tables, delete device rows | Three tables including persistent epoch and password stamp | D addresses stale issuance/restore explicitly; C needs an equivalent ordering barrier, not necessarily D's exact schema |
| Cap | Ten live devices; automatically evict LRU | Five; refuse extra remembering until explicit revocation | C is more convenient but may evict legitimate devices; D can strand a new browser at cap |
| Recovery | Reset flow plus mailbox step-up trust link with browser nonce | Changed resend semantics; reset completion plus optional short, one-check continuation | C is more incremental but inherits reset-denial issues; D explicitly changes more contracts and needs additional review |
| Cookie policy | SameSite=Strict, automatic remembered issuance | SameSite=Lax, explicit opt-in | Both policies can be valid with CSRF; cross-site email, browser privacy and shared-computer journeys need actual tests |
| Logging | 30-day stderr pipeline, per-window dedup claim, 48-bit references | 14 days/100 MiB, daily independent pseudonym keys, capped detection/queues | C is simpler to deploy but lacks global bounds; D caps exposure but can drop important observations |
| Delivery phasing | Explicit 02A/02B/02C split | Coherent modes; transport/backend details acknowledged unresolved | C's staging is useful, but its always-on success ceiling can introduce a hard account gate before recovery |

## 4. Findings ranked by severity

### F01 — High: failures spend C's successful-login allowance and bypass the recovery gate

**Evidence:** [C quotas][C-quota], [C reservation/release][C-reserve], and
[C activation][C-activation]. `account_success` is reserved **before** authentication
on both paths; failure keeps reservations; success releases only failure buckets.
C says “success and ceiling counts stay.” Therefore the proposed success counter
actually counts admitted failures too, contrary to its stated purpose.

Concrete trace with C's defaults and rotating sources:

1. Ten wrong unfamiliar attempts spend ten `account_fail` slots **and ten** hourly
   `account_success` slots.
2. Once the 15-minute account-failure window renews, ten more wrong attempts fill
   the hourly success bucket to twenty. No successful login has occurred.
3. A correct password from a valid trusted device is now refused by the shared
   success gate even though its device/trusted-failure budgets are unused. The
   denial can outlive the 15-minute failure restriction, until the hourly window ends.
4. With account-failure enforcement off/observe, the same twenty admissions can
   happen sooner. C makes these new source/success controls always on in 02B,
   before the verified-recovery gate in 02C.

This is a targeted availability attack and a layering error, not just conservative
accounting. Even after fixing failed reservations, a real hard 20-successes/hour
account gate needs the owner's recovery/production approval, not automatic exemption.

**Recommendation:** distinguish (a) committed password-evaluation admission,
(b) in-flight work, (c) final failed outcomes and (d) committed session issuance.
If a successful-session quota is kept, acquire it atomically **after verified
credentials**, at finalization, with explicit handling for transaction/session-save
failure; do not let wrong passwords consume it. Password-work budgets must still
exist before hashing. Specify any reservation/refund protocol instead of guessing
intent. D avoids this particular mislabeled-success bucket, but has F03's availability
trade-off. **Resolve before freezing 02A counter semantics or enabling 02B.**

### F02 — High: C's casefolded device binding can authorize the wrong account's throttle lane

**Evidence:** [C device validation][C-device], [C casefold keys][C-quota],
[B backend][B-backend], [B account identity][B-model]. Current authentication uses
`Student.objects...get(username=username)` with a case-sensitive username policy;
`Alpha` and `alpha` are distinct possible accounts. C says device ownership is checked
by `username_key = HMAC(NFKC(username).casefold())`, then leaves StudentBackend unchanged.

A cookie issued to attacker-owned `Alpha` has the same username key as victim
`alpha`. Submitted with `alpha`, it passes C's documented username-key comparison
and selects the trusted path for a different actual account. The correct victim
password is still necessary: this is **not passwordless account takeover**. It does,
however, defeat the intended account binding and can bypass the victim's unfamiliar/
ordinary-IP gate while sharing/mis-spending case-collapsed budgets. Own-account cookie
issuance and the device cap do not fix a collision created deliberately by casefolding.

**Recommendation:** preserve actual authentication identifier semantics and compare
the device's stored Student FK with the **exact authenticated target identity** (or
an exact canonical-name check before hashing plus a definitive identity check on
success). A broad attack-correlation bucket may be a separate deliberate control;
it must never serve as proof of account equality. D explicitly preserves case and
account binding. Require a positive/negative `Alpha`/`alpha` test **before 02A's
`username_key` contract is accepted**.

### F03 — High availability risk in both: shared-IP ceilings still deny legitimate campus logins

**Evidence:** [C quotas/NAT][C-quota], [C NAT claims][C-reserve], [C critical answers][C-answers];
D §A.1 explicitly retains “Existing 10 submissions / 15 minutes” for unfamiliar sources.
[B settings][B-settings] confirm that baseline limit.

- **D's flaw:** eleven different legitimate first-time students on one source,
  each using a correct password, exhaust the retained ten-submission bucket before
  student eleven. This needs no attacker or per-account failure. D acknowledges NAT
  interference but has not made its campus availability policy acceptable merely by
  preserving an existing limit.
- **C's flaw:** sixty legitimate source admissions can exhaust `ip_ceiling`; the
  sixty-first valid remembered student is denied too. C's A.12 answer that returning
  browsers “can't” suffer shared-NAT denial once bypass is on contradicts its ceiling.
  Three controlled accounts with twenty correct logins each could also spend sixty
  source slots within fifteen minutes; the ordinary failure counter need not grow.
- A reviewed proxy can recover a source address hidden by **that proxy**. It cannot
  split users who genuinely share one upstream public NAT address; forwarded headers
  must not be invented/trusted to make this sizing problem disappear.

**Recommendation:** retain broad abuse controls, but separate account/device guessing
budgets from measured infrastructure capacity/concurrency policy. Benchmark campus
arrival bursts (not just C's proposed thirty-student test) and approve a fair policy
for unfamiliar users; no universal safe ceiling is inferred. Classify rejected cases
accurately and test trusted users after all source-wide controls saturate. Do not
simply remove all perimeter limits. **Both authors need to revise numeric/policy
claims before a production restriction is approved.**

### F04 — High: C does not specify a barrier against stale device issuance after revocation/reset

**Evidence:** [C issue/revoke algorithm][C-device], [C finalization][C-reserve],
[B reset/change][B-views], [B backend][B-backend]. D §§A.4–A.5 explicitly require an
epoch/password stamp and post-hash revalidation.

Race: login verifies a snapshot of the old password → reset or forget-all locks the
account and deletes devices, then commits → original login later locks the account
and inserts/rotates a new device using its earlier authentication result. Merely
locking Student **after** the password check does not prove the old result is still
valid. No generation or current-password comparison is specified in C's device
schema/finalization. Deleting existing rows cannot delete a stale future insertion.
A resulting old-password session would ordinarily fail the existing live auth-hash
check on its next use ([B principals][B-principals]); nevertheless a newly inserted
device without a credential stamp could survive and recover a trusted guessing lane.

A related **conditional baseline hazard**, not a runtime exploit result here:
`StudentBackend` calls `student.check_password`. Installed Django 5.2.19's
`AbstractBaseUser.check_password` (dependency source `django/contrib/auth/base_user.py`,
lines 100–112, inspected locally) can automatically save an upgraded hash by account
ID. If a hash upgrade is needed, its stale setter can race a reset unless protected
by an application finalization/CAS protocol. C's “unchanged StudentBackend” does not
address that; D §A.5 correctly calls for verifying a captured hash without an
uncontrolled save, then upgrading under finalization locks. Confirm this hazard in
an authorized PG17 test rather than claiming it was reproduced in this review.

**Recommendation:** define the success/revocation ordering point and bind admission
to current credential/generation state. Lock/recheck eligibility and captured password
version before issuance/session finalization; authorize upgrades with compare-and-swap.
Use a monotonic epoch or equivalent proven barrier for forget-all. D's proposed
mechanism is useful, but not implemented/proven. **02A schema must support the chosen
barrier; finalization races are not postponed until after a schema freeze.**

### F05 — High conditional availability risk: C treats concurrent rotation as malicious replay

**Evidence:** [C rotation][C-device]. C explicitly concedes a two-tab race but deletes
the record on `previous_digest` before even checking submitted-account matching.

Two genuine tabs submit the same current cookie. Both can validate before either
finishes. First login rotates the row; the second then sees stale evidence, or rotates
again if there is no expected-version check. Responses can arrive out of order,
leaving an already-rotated cookie in the browser. Its next use deletes the record.
Serializing row writes does **not** serialize network delivery of Set-Cookie responses.
A thief with the previous cookie can deliberately trigger this loss of trust; under
an ongoing unfamiliar-account attack, “simply re-earn trust” may itself be blocked.

**Recommendation:** decide a complete concurrent-renewal protocol before implementing
rotation/reuse primitives in 02A. Options include explicit renewal with fixed original
expiry (D's approach), or carefully versioned rotation with a short, bounded grace
policy. Grace increases replay exposure and needs a threat decision; do not silently
add unlimited previous-token acceptance. Recheck expected row state under the lock,
validate target-account binding before destructive action, and test reverse response
order. D avoids this automatic replay-trigger deletion but accepts undetectable replay
of a current copy until signed expiry/revocation; that is a trade-off, not proof D wins.

### F06 — High specification conflict: C has contradictory database-failure outcomes

**Evidence:** [C reservation][C-reserve] says any DB error during reservation/lookup/
release gives 503, no evaluation/session, **then** says failed release after success
still completes login. The diagram promises “DB error at any step” → no evaluation.
Actual [B boundary middleware][B-boundary] catches errors in initial role checks;
its try block does not cover exceptions later in the wrapped view/session middleware.
It is not an all-stage fail-closed handler.

It is impossible to undo a hash already evaluated when a later release fails. A
refund failure that leaves counters over-counted is mathematically conservative,
but permitting authentication after it is a distinct policy needing review, not the
same all-stage 503 guarantee. Issuance/revocation/credential-state errors are not
interchangeable with optional logging errors. Catching a PostgreSQL error inside a
broken atomic block and continuing would not safely commit the promised state.

**Recommendation:** publish stage-specific outcomes: pre-admission error means no hash;
post-admission security-state/finalization error means no **new** session/evidence and
503 after rollback; already-performed work remains spent; post-commit log loss uses a
bounded safe reporting policy. Choose explicitly whether a noncritical refund can be
best effort. Do not automatically retry a committed admission by hashing again.
D's no-refund rule removes one stage but still needs a concrete integration with
Django's response-time session saving. Both need fault injection through that late
boundary, not only a mocked first cursor failure.

### F07 — High enforcement dependency: recovery is not independent of the attack path yet

**Evidence:** [C recovery][C-recovery] says the existing reset flow is unchanged and a
new request revokes the earlier step-up token. [B reset view][B-views] applies the
ordinary `reset-confirm` source gate **before** checking the secret, on GET and POST.
[B token issuance][B-tokens] consumes all older same-purpose links on a new request.
The [existing regression][B-tests] explicitly expects that invalidation.

- Attackers sharing a source can spend reset-request/confirmation allowance and deny
  recovery as well as login. A trust link must also be shown to work after **all**
  relevant ordinary source/account gates saturate; C gives no equivalent complete
  independent redemption-lane contract to D §A.6.
- A repeated requester can invalidate a victim's usable reset/trust link without
  reading it. Per-email throttling slows this; it does not make replacement safe.
  Step-up's pending-browser nonce does not stop a different browser issuing a newer
  request for the same account and invalidating the first token. The surviving
  link can be bound to the attacker's pending nonce, so the mailbox owner cannot
  necessarily redeem it in their own browser. Email possession and a sender-side
  nonce need a non-disruptive multi-request protocol, not just a request cap.
- The same-browser step-up link is a distinct mailbox-proof flow without changing
  the password; D instead uses completed reset. Its authorization, cookie attributes,
  use on another device/mail client and consent need an explicit decision.
- D addresses live-link preservation but its three-token cap plus an unresolved
  delivery/outbox contract can leave all slots occupied by undelivered messages.
  “Use any of the emails” only works if they arrive. D correctly makes transport and
  support blocking dependencies; that is not a completed escape hatch.
- C's provider-outage runbook switches to observe, reopening guessing. A manual,
  audited risk decision can be legitimate, but it is not recovery while retaining
  enforcement. A simultaneous attack does not stop at the end of one window.

**Recommendation:** specify bounded/coalesced issuance without unauthenticated link
invalidation, durable secret-safe retry/resend behavior, an independently bounded
valid-proof redemption route, and a usable outage/support procedure. Avoid triggering
email automatically on every denied login. No hard account gate, including a
session-success ceiling, gets a production exemption from the owner's recovery gate.

### F08 — Medium: C's cross-account deletion and cap behavior have unnecessary side effects

**Evidence:** [C issuance][C-device] step 5 deletes the browser's different-student
record while completing the newly authenticated student's login. Its reuse branch
also deletes before account matching. Auth tables have no per-student RLS; the auth
role can delete rows globally ([C grants][C-grants], [B provisioning][B-grants]).

Logging in as B does not authorize B as A. Replacing the browser's cookie can enforce
one remembered slot without deleting A's server record. C's extra deletion expands
availability effects for a copied/shared cookie and introduces a second account into
its claimed Student-first lock order. Reciprocal A/B browser replacements need a
global two-account ordering or, preferably, no cross-account mutation. This is a
trust-availability concern, not evidence of academic cross-student data access.

C's automatic ten-device LRU eviction can also remove a legitimate escape route;
D's refusal at five can inconvenience a legitimate sixth browser. Neither cap is
empirically justified. Recommend replacing/clearing only the local cookie on account
switch, own-account explicit revocation and an independently reviewed cap UX.

### F09 — Medium: signing, schema and restore contracts need decisions before 02A

**Evidence:** [C format/schema][C-device], [C rotation lifecycle][C-device]; D §§A.3–A.4/A.7.
C's salted use of Django's secret provides a purpose domain and its random DB-backed
ID remains unforgeable from a leaked signing key alone. Do not falsely call this an
unsigned cookie or automatic takeover. However, an independent device key and an
explicit bounded key-retirement policy narrow operational coupling; C's generic
`SECRET_KEY_FALLBACKS` has no device-specific retirement deadline. Purpose-separated
salt is not an independently rotatable key.

C's 31-day SQL CHECK does not enforce a strict 30-day ceiling, and no maximum signed
age is specified for `loads`; current DB expiry still helps, so this is not proof
of indefinitely valid live cookies. Previous-token replay consequences and restoring
old device rows/keys must be covered. C's risk register treats restored throttle state
as only one extra guessing window; restoring **devices/old credentials** can resurrect
revoked trust unless the restore runbook rotates keys/advances state (explicit in D).
C's deferrable SQL FK without ON DELETE CASCADE also differs from its ORM CASCADE
statement; no public account-delete policy should be inferred or academic PROTECT
constraints weakened to accommodate it.

D's weakness is protocol cost: selector, validator, account-reference HMAC, stamp,
key ID, epoch, two cookie modes and multiple keys are substantially more to audit.
The opaque account tag is not needed merely to bind a DB-backed opaque token to a
Student FK; it adds a linkable per-account value across browser copies. Consider
C's compact random-token primitive with exact owner/generation checks and an
independent key, instead of copying D's whole envelope. Do not drop signed-age,
revocation or parser limits in the name of simplicity.

### F10 — Medium: both event designs need a durable/bounded deduplication contract

**Evidence:** [C rollback][C-reserve], [C logging][C-logging]; D §A.8.
C rolls back the increment above the limit, so the stored count stays at the limit,
not `limit+1`. Each later denial can observe that same transient transition again.
Its “log once per window on transition to limit+1” claim needs a durable marker or
an external bounded deduplicator. Also, one event per arbitrary identifier/window
is not a global event-volume bound. Thirty-day retention alone does not bound disk
usage, and a separate salt is not a separate key. Forty-eight-bit references should
not be treated as collision-free attribution at large cardinalities.

D proposes global size/rate/cardinality caps and daily keys, but its caps can cause
important failure events to be dropped while an attacker fills the low-value event
queue/detection subject set. Priorities/reserved health capacity and the selected
cross-worker collector are still unspecified. Bounded detection overflow must never
evict active auth budgets or cause an implicit permission change.

Recommend independently keyed pseudonyms, allowlisted route names/reason enums,
explicit retention across backups, source/token/query-string redaction at every
logging layer, durable or correctly bounded deduplication, priority for protection
failures, loss metrics and no synchronous logging while holding auth locks.

### F11 — Medium: response similarity is not an enumeration or privacy proof

**Evidence:** [C recovery/logging][C-recovery], [C tests][C-tests]; D §§A.2–A.3/A.8.
[B backend][B-backend] does dummy hashing for unknown users, but generic responses
alone do not prove timing or state equivalence. Async mail removes synchronous
provider delay, not every lookup/queue/rate-history difference. A mocked delayed
sender cannot prove “constant response time.” Existing registration email behavior
remains a separate S0-04 issue; this review does not claim S0-02 repairs it.

Valid stolen device evidence can be probed against candidate usernames to observe
lane behavior; C's phrase that a single-account cookie “reveals nothing beyond a
device” is too strong. D acknowledges such correlation but carries an extra opaque
account tag (F09). Neither should emit account existence in 429 reasons, token errors,
cookie issuance on failed login, logs or account-prefill UI. Test bounded distributions,
not an unrealistic identical-time assertion, and distinguish proof-of-mailbox behavior
from unauthenticated enumeration.

### F12 — Medium, D-specific: the recovery continuation and compatibility claims need narrowing

**Evidence:** D §§A.6/A.9/A.10 propose “one admitted password check” after recovery,
consume it on a wrong password or worker crash, preserve three live reset links,
retain all 337 historical tests, and acknowledge unresolved finalization/transport.
[B tests][B-tests] currently requires a new reset request to invalidate the earlier one.

D's privacy opt-out is useful, but one typo, duplicate submission or post-reservation
crash can exhaust the only continuation and send a restricted legitimate student back
to email. That increases dependency on the very recovery channel being protected.
Choose and test an accessible bounded retry policy; one check is not automatically
better security/UX than a few checks under the shared trusted aggregate. Do not
silently make long-term remembering a prerequisite for account access.

Preserving all old tests is compatible with feature-OFF/default profiles, but the
opposite reset-link semantics cannot both apply in the **same** enabled profile.
D must specify that compatibility matrix or obtain explicit approval for changed
contracts rather than claim every old assertion applies in every mode. Its existing
lock-order/hash-outside-transaction aspiration also requires restructuring reset/new-
password hashing: current reset/change views call `set_password` inside Student
transactions. D's extra state, locking and HMAC/session rereads need measured query/
contention costs; its transport, collector and finalization choices are admitted
open dependencies, not an implementation-ready design.

## 5. Before S0-02A: required invariants and staged PostgreSQL tests

Agree the following expected results **before implementing** the primitives. Tests
can only verify a future implementation after explicit authorization; no claim is
made that any proposed S0-02 test has passed now. Dormant 02A tests must not enable
new login behavior just to obtain a green check.

| Stage / test | Required assertion |
| --- | --- |
| Design gate: budget taxonomy | State separately what counts submissions, password evaluations, pending work, failures and committed sessions; explain expiry/refunds and both lanes' combined bound |
| 02A: exact identity binding | Distinct `Alpha`/`alpha` accounts; cookie for one never selects trusted protection or mutates devices for the other; NFKC matches the actual backend contract |
| 02A: state/generation primitive | Password replacement/revoke-all preceding issuance commit prevents stale evidence from becoming usable; row deletion alone is not accepted as proof |
| 02A: rotation/version contract | Two simultaneous uses, explicit lock barriers and reverse response delivery; no benign race automatically destroys trust unless that loss is an explicitly accepted policy |
| 02A: expiry/key/restore | Exactly 30-day maximum, old signed expiry after renewal, bounded previous-key acceptance, emergency retirement and restore cannot resurrect revoked devices |
| 02A: real grants and schema | Fresh PG17 migrator provisions separate auth/runtime LOGINs; auth has necessary columns only; runtime/PUBLIC lack SELECT and all mutations on support tables; FKs/CHECKs and ORM vs raw-SQL delete behavior verified |
| 02A: activation/rollback | Migrate and provision before code requires new grants; old OFF profile and reversal tested. C's global middleware SELECT requirement must not create an unexplained site-wide outage in a supposedly dormant rollout |
| 02A: cap and cleanup | Parallel issuance at cap minus one, lazy state creation, expired vs live cleanup, no active-budget eviction and no unsafe state-epoch restart |
| 02B: success/failure isolation | Twenty failures over independent source/account windows do not spend a separately named successful-session quota; a trusted correct login remains eligible under its actual independent budgets |
| 02B: campus tests | 11 unfamiliar successful students (D), 61 mixed/trusted successful students (C), larger measured bursts, attacker-owned accounts and an actually saturated public NAT; record intended refusals honestly |
| 02B: multi-bucket admission | N+1 workers, separate PG17 connections/barriers, existing and missing rows, mixed devices/sources; count backend evaluations and durable reservations, not only responses |
| 02B: window/refund/retry | Old-window release cannot change a new window; rollback/denial dedup and worker crash tested; no whole-request retry repeats an already admitted/evaluated password |
| 02B: stale credentials/hash upgrade | Pause between verify and issuance; reset/change/forget-all in another connection; also use a real hash requiring upgrade and ensure no stale setter overwrites the new password |
| 02B: database failure stages | Faults during role check, lookup, reserve, after commit, release, device write, session save and response middleware; no unadmitted hash or new auth/evidence on failed security finalization; expected 503/rollback specified per stage |
| 02B: observe/OFF safety | Unknown/known targets and actual session ceilings tested with every flag combination; no hidden pre-recovery hard account restriction; no bypass with missing independent budgets |
| 02B: replay and privacy | Cross-browser copy, old cookie, wrong account, forging, parsing/size bounds, secure/local key isolation, consent/logout/forget and no raw secrets in any captured log |
| 02C: recovery under attack | Saturated login source/account and reset/step-up source budgets do not prevent the independently authorized valid-proof redemption path; malformed requests cannot consume a victim's grant |
| 02C: resends and outages | New requests cannot indefinitely invalidate the student's usable link; three-token/one-token caps, pending mail, ambiguous send, delayed delivery and provider outage/support exercised |
| 02C: concurrent proof use | Same and different outstanding tokens, sibling invalidation, credential change, GET scanners, browser-nonce mismatch, purpose swap and DB rollback yield at most one authorized recovery result |
| 02C: accessibility/continuation | Actual email navigation on supported browsers, Strict vs Lax behavior, keyboard/screen-reader journey, opt-out, typo, retry, duplicate POST, cookie blocking and post-admission crash |
| All: regressions and logging | Existing 337 tests on their supported default profiles; explicit enabled-profile changes approved; redaction sentinel tests, global/subject log flooding, loss/retention and no new runtime/migration query privileges |

Use `TransactionTestCase`, independent connections, `threading.Barrier`/events and
bounded timeouts; assert all threads finish and no hidden DB errors/deadlocks are
swallowed. PostgreSQL READ COMMITTED plus an upsert is not by itself a proof of the
whole multi-row protocol. Define one global lock order across issuance, revocation,
cleanup, recovery and counters; sorted quota inserts alone do not prove absence of
all deadlocks. Only retry known rolled-back, pre-hash units with an explicit bound.
Test on the actual auth login, not privileged SET ROLE or the migration connection.

Current middleware/configuration/provisioning evidence: [B boundary][B-boundary],
[B router][B-router], [B grants][B-grants]. Extend both positive and negative privilege
checks, not only presence of SELECT on the new tables. Academic RLS remains on the
runtime connection. The migrator creates/reverses schema but never serves requests.
Historical destructive migration tests must stay in their separate disposable DB.

Neither author's prior local suite results establish a new S0-02 implementation.
C explicitly reports local PG16 and unverified hosted PG17; D's prior 4B report records
PG17 local work on the existing application. Those are different environments and
scopes, not reasons to declare either proposed algorithm race-safe. Hosted CI status
was not re-certified by this documentation-only review. A future PG17 job must pass
for the actual implementation commit before a merge is considered.

## 6. Recommended improvements, in order

1. **High / before 02A schema approval:** resolve F01's quota taxonomy, F02's exact
   identity binding and F04's generation/credential ordering. These affect stored
   keys/state and cannot safely be left to later form integration.
2. **High / before 02A rotation primitives:** settle F05's concurrent cookie protocol
   and F06's stage-specific failure/finalization rules. Use C's small opaque token
   where adequate and D's explicit revocation ordering where needed, without adding
   redundant account metadata or assuming either entire design is superior.
3. **High / before enabling any new hard gate:** approve a realistic campus policy
   (F03) and recovery independence/outage behavior (F07). Apply the recovery gate to
   success/session restrictions too, or obtain an explicit separate owner decision.
4. **Medium / before integration:** remove cross-account device deletion (F08),
   finalize independent key/expiry/restore policy (F09), and choose bounded safe
   logging/deduplication and privacy verification (F10–F11).
5. **Medium / before recovery implementation:** simplify D's continuation/protocol
   where possible and specify feature-profile compatibility, queue/collector grants,
   consent, retries and actual transaction costs (F12). Validate accessible recovery
   with real delivery; no automatic provider-outage downgrade.
6. Keep 02A **dormant** with explicit, independently authorized migration/grant tests;
   implement nothing from this review by implication. Keep the 100/day account cap,
   site-wide adaptive restriction, S0-03 quotas, public deployment and merge outside
   this authorization. No proposal text was rewritten to silently decide these issues.

Evidence links embedded above pin source commits rather than mutable branch content.

[C-device]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L84-L201
[C-quota]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L203-L246
[C-reserve]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L248-L282
[C-recovery]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L284-L321
[C-grants]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L323-L334
[C-logging]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L336-L353
[C-activation]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L355-L368
[C-answers]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L391-L404
[C-tests]: https://github.com/jordandavid1812-creator/university-command-center/blob/e161be87a2aacb6cb54eff43041c1fb3ea1f375d/docs/security/S1_PROPOSALS.md#L450-L513
[B-backend]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/backends.py#L7-L30
[B-model]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/models.py#L19-L39
[B-views]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/views.py#L90-L147
[B-tokens]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/tokens.py#L18-L89
[B-tests]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/auth_tests/test_limits_and_tokens.py#L18-L90
[B-settings]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/config/settings/auth_common.py#L36-L54
[B-principals]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/principals.py#L21-L46
[B-boundary]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/middleware.py#L9-L21
[B-router]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/routing.py#L1-L19
[B-grants]: https://github.com/jordandavid1812-creator/university-command-center/blob/64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb/server/accounts/management/commands/configure_auth_role.py#L43-L54
