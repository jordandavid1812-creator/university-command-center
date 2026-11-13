# Package C — trusted-device/account-security activation readiness

**THREAT MODEL AND STAGED PROPOSAL ONLY. No flag, account restriction, backend,
staging, deployment or user invitation is authorized. S0-02B/C are future work.**
Base `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6`; merged B1a/B1b. Master push
[43380783580](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43380783580)
passed all four jobs on PostgreSQL 17.12: 484 regressions, 27 browsers, additional
website-root 27/34 and mutation detections 15/14, no skipped/failing summaries.
Documentation CI is not activation evidence. B1c/B1d are not implemented.

Sources: current accounts/devices.py, models.py, views.py, tokens.py, throttling.py,
boundary.py, configure_auth_role and test_trusted_devices.py; [S1 A.19–A.21](S1_PROPOSALS.md),
[reconciliation §§4–5](S0_02_RECONCILIATION.md), [Stage B](STAGE_B_IMPLEMENTATION_PLAN.md)
and [B1b evidence](B1B_IMPLEMENTATION_EVIDENCE.md). Earlier “unmerged”, quota-refund,
trusted-grace and guaranteed-rollback statements in those histories are not current
source truth. The current primitive docstring/tests and strengthened A.20/A.21
control the starting point, subject to the explicit conflicts below.

## Exact implemented versus missing inventory

| Present in master | What it actually does / what it does not establish |
| --- | --- |
| Student, TrustedDevice, DeviceGeneration, LoginLimit; accounts.0003 | Auth-only foundation and role guards. Runtime has no device/account/key privileges. LoginLimit is **schema only**, not an admission service. |
| new_identifier(), identifier_digest() | 256-bit random identifier, purpose-separated SHA-256 digest stored; not a password or session credential. |
| cookie_value(), read_cookie() | Signed value with salt ucc.trusted-device.v1, global SECRET_KEY/FALLBACKS; 30-day signed max age, length <=256 and fixed identifier shape, reject junk before DB. No HTTP Set-Cookie writer. No independent device-signing key/ring exists. |
| generation(student_id) | Read current generation (default zero), does not authenticate or authorize the supplied UUID. |
| issue(student_id,username,credential_stamp,generation) | Student lock, active/exact username binding, credential stamp and pre-verification generation recheck; cap 10 with own-student LRU eviction; signed string result only. Caller must be trusted. |
| check(cookie,username) | Exact stored username equality after the form's NFKC policy, never casefold; joins immutable Student UUID. Returns trusted/grace/absent/mismatch/replayed; same-account superseded replay can delete its device. Check.selects_trusted_limits is true **only** for trusted, not grace. |
| rotate(cookie,student_id) | Locks device, compares authenticated UUID, CAS digest rotation. One winning response gets a string; grace loser gets no cookie. Current grace 60 seconds; rotation renews record expiry/signature to the 30-day contract. No HTTP wiring. |
| revoke(device_id) | Internal unscoped deletion by identifier, **not** an owner-authorized public endpoint. A future endpoint must first scope to the server-derived student's record, not expose this function directly. |
| revoke_all(student_id) | Student lock, increment DeviceGeneration, delete all own devices. Stale pre-verification generations cannot reissue trust. Does not change passwords/sessions or prevent a password holder logging in later. |
| cleanup_expired() / _delete_expired() | Bounded device/limit expiry cleanup; clear_auth_artifacts invokes it offline. Not request-time enforcement. |
| Existing AuthThrottle/rate_limit() | Active shared-source per-action throttling, normalized IP/IPv6 /64 and reviewed-proxy algorithm; login currently 10/900s by source, counting all attempts (including correct passwords), not only failures. No account-aware LoginLimit or trusted bypass. |

Internal helpers `_valid_username` (shape only), `_live` (active/expiry filter)
and `_classify` (owner-first status logic) also exist, with DeviceError and
Issued/Check/Rotation result types. None is a web authorization boundary. In
particular issue() itself checks active state, not email verification: a future
service must enforce verified eligibility after real credential/recovery proof.

**Absent:** T1 admission/failure reservations, conditional releases, T2 committed
success accounting, explicit-session B2 finalization, live device issuance/rotation/
revocation wiring, forget-all UI/service authorization, new source ceilings,
observe/enforce modes or their feature-flag implementation, independent/coalesced
recovery, event pseudonyms/dedup/alerts and operational activation controls.
Existing views/backend/middleware do not call device primitives; tokens.py resets
and password-change views do not automatically revoke devices. A reset changes
credential stamps, but that is not live device-row revocation. Existing recovery
issuance revokes older same-purpose links, and redemption shares source throttling.

Proposed UCC_TRUSTED_DEVICES/UCC_ACCOUNT_LOGIN_MODE/UCC_DEVICE_IP_BYPASS switches
are **not implemented activation controls today**. UCC_TRUSTED_PROXIES=() is real
and remains empty. No document text or manually set nonexistent flag activates code.

## Threats, invariants and compatibility

| Threat/scenario | Required future protection / residual |
| --- | --- |
| Copied current cookie | Can be replayed in another browser; it is a bearer throttle hint, not browser-bound hardware. Password still required, with per-device and aggregate-account limits plus infrastructure controls. Never unlimited guessing. |
| Wrong-account/case/normalization replay | Preserve exact form/backend identity and post-auth UUID binding; foreign account presentation never revokes the owner's device or selects its trusted lane. Test known/forged UUIDs and stored non-NFKC variants. |
| Two tabs/rotation response reordering | First rotation gets one new identifier; grace loser sends no Set-Cookie and uses unfamiliar limits. Lost winner response may leave the old identifier, then lose trust after grace. A thief may cause replay revocation; do not claim lossless renewal. |
| Targeted unfamiliar restriction | An attacker can repeatedly spend a victim's failure allowance. Correct password must not bypass an activated pre-hash restriction. This is a real denial-of-service risk, not solved by cookie branding; independent recovery and owner acceptance gate enforcement. |
| Cookie accumulation | Successful verified enrollment only, cap 10 and aggregate account_trusted_fail across devices; account_success cannot be spent by failures. Enrollment/LRU/forget-all UX and ownership require review. |
| Reset/change/forget-all race | Read generation before verification; serialize Student then device state, recheck password/hash/generation. Commit revocation with credential change in future wiring. Old cookie after reset must not remain trusted. No trust for merely requesting a reset. |
| Compromised auth role / restore | Current auth SQL can lower generation (nonnegative CHECK is not a monotonic privilege boundary). A restored snapshot can resurrect rows/generations. Resolve with separately reviewed hardening or explicit documented risk acceptance and tested global trust invalidation before activation; never claim complete revocation security today. |
| Shared-campus NAT / distributed guessing | Trusted and unfamiliar source lanes remain independently capped. Even a trusted ceiling can deny legitimate students. Campus measurements and a tested capacity policy are mandatory; trust a proxy only for an actual reviewed proxy, never because an IP belongs to campus NAT. |
| DB/counter uncertainty | No password evaluation before required T1 admission; no authority from failed finalization. Committed/uncertain states remain possible. Do not retry writes, silently fail open or claim rollback from a 503. Observe mode threshold behavior is distinct from DB failure. |
| Enumeration | Constant text is insufficient. Compare known/unknown usernames with absent/valid/stolen/grace cookies by status, timing distribution and side effects; a stolen cookie can probe account associations. |
| Provider/recovery outage | Logging/alerting and owner-approved rollback may reduce restrictions; neither sends recovery mail nor repairs revoked links. No automatic downgrade to an unsafe login bypass. |

No new schema, endpoint, request behavior or risk acceptance is implemented by
this proposal. Password/CSRF/session/RLS/math tests stay mandatory. A cookie alone
never authenticates. Proposed same-browser multi-account UX starts with **one
account-bound cookie slot**, replaced on account switch; no list of accounts in
the cookie and no growing per-account cookie map. Other devices' records expire
or are revoked; a displaced browser cannot reconstruct their identifiers.
Measure total headers/cookies (including session/CSRF) below browser/proxy limits;
MAX_COOKIE_LENGTH on the reader is not proof of HTTP header compatibility.

Future HTTP writer: 30-day bound, HttpOnly, Secure for HTTPS, SameSite=Lax unless
separately approved otherwise, host-only/path policy and renewal/expiry/deletion
semantics tested. A secure __Host- name is a proposal for review, not a configured
cookie; local HTTP fixtures cannot silently weaken production cookie attributes.
Global signing-key rotation/fallbacks affect device verification and may affect
sessions. Dedicated key separation/retirement remains a separate design choice;
retire keys/revoke trust after compromise/restore, never fake migrations.

## Protocol conflicts that block S0-02B implementation

1. **Quota accounting:** older A.19 reserves a success unit then refunds it. A.20
   and reconciliation §4 supersede that: T1 reserves volume/provisional failures
   before hashing; wrong passwords never touch account_success. T2 alone acquires
   success alongside a committed session; conditional releases use the same window.
   Crash after T1 can conservatively overcount failures; do not hide that DoS cost.
2. **Lock order:** devices.py/R5 state Student → affected device rows → optional
   AccountToken → sorted counter rows. A.20 lists success/release counter updates
   before rotate/issue. A unified SQL lock schedule (including pre-locking affected
   device rows if needed) must be reviewed and PG17-deadlock-tested **before code**.
   Merely wrapping the conflicting orders in atomic is not a resolution.
3. **Session semantics:** current Django saves N/AN/SA UPDATE or SX/DA INSERT during
   response. B2/A.20's explicit T2 session save is separate future behavior, not
   already delivered by B1. Preserve the verified-hash recheck and same-secret CAS
   compatibility; test all five entry states before owner accepts that change.
   Saving inside T2 alone is insufficient: specify how response middleware avoids
   a second write while delivering the cookie only after commit. Simply clearing
   session.modified also suppresses its cookie path; do not assume that solves B2.
4. **Schema taxonomy:** LoginLimit.kind currently accepts account_fail,
   account_trusted_fail, account_success, device_fail, ip_ceiling only. Logical
   ip_ceiling_trusted/unfamiliar lanes cannot simply be inserted as new kind values.
   Prefer reviewed domain-separated lane keys with existing ip_ceiling kind, or
   explicitly authorize a forward migration. Do not edit/fake applied 0003 history.
5. **Outcome claims:** reconciliation's old “rollback/no session/no cookie” and
   “lost cookie means nothing trusted created” statements cannot cover dispatched
   COMMIT or response loss. Use B1's S0–S3/E0–E4 and CK1–CK5 instead. Grouping writes
   reduces units but cannot make COMMIT atomic with HTTP delivery.

These are documented integration blockers/proposed resolutions, not code fixes or
blanket approval of a new protocol. Keep separate from Package A's D-B1-6.

## Staged future work — no stage is authorized here

| Gate | Future package / required evidence before advancing |
| --- | --- |
| 0 current | Dormant primitives only; all existing regressions pass. No device cookies or LoginLimit restrictions; current shared-IP throttle still has campus availability limits. |
| 1 B1 completion | Independently reviewed/authorized B1c then B1d, complete failure/cookie/logging matrices. No intermediate B1 staging acceptance. |
| 2 B2/B3 | Separately authorized explicit-session T2 and structured security events; resolve lock/order/provenance/rollback and logging key/retention schema. Flags off. |
| 3 B4 observe | Implement atomic admission/account counters in synthetic observe mode. Threshold crossing logs would_restrict but does not hard-restrict accounts. Counter/DB errors are security-state failures, not permission to silently allow auth; owner approves availability trade-off. New source ceilings also remain non-enforcing until explicitly approved. Existing ordinary throttle remains. |
| 4 B5 device wiring | Enrollment/revocation/UI behind default-off device flag; reset/change/forget-all transaction tests, cookie attributes, ownership and independent device/aggregate caps. Synthetic enrollment activation needs its own explicit scope; no automatic real-user enrollment. |
| 5 B6 source bypass | Separate default-False trusted-IP bypass, only current trusted status. Grace/absent/mismatch/replayed never bypass. Test independent device/account limits and both source ceilings under campus saturation before owner authorizes any bypass. |
| 6 B7 / S0-02C recovery | Coalesced issuance (unauthenticated requests cannot invalidate a working link), independently bounded redemption, single-use/expiry/replay/concurrency, credential/generation revocation and reliable accessible support. Successful verified redemption may enroll trust only under a separately reviewed policy. |
| 7 controlled enforcement | Only after every A.21 and operational gate below has independent evidence and explicit owner authorization for that exact deployment/profile/cohort/threshold set/rollback. No implementation completion implies activation. |

Proposed defaults for future code: devices=off, account mode=off (observe only by
explicit synthetic work order), IP bypass=False, trusted proxies/high-volume
source exceptions empty. Validate combinations; reject bypass without devices or
enforcement without readiness attestations. Deployment-controlled settings and
worker restart/consistent rollout are proposed; no unimplemented “instant switch”
is promised. Do not add a paid flag service or claim runtime consistency without
multi-worker tests. Rollback propagation time itself must be measured.

## Enforcement prerequisites and owner decisions — PENDING

- Approve one unified T1/T2 lock/accounting/session protocol after B1 and separate
  B2/B4 review. Failure units and success units have independent limits; abandoned
  attempts cannot consume committed-success allowance. Counter keys domain-separated,
  atomically saturated/bounded; releases never refund a newer window.
- Approve campus-specific thresholds and both trusted/unfamiliar ceiling capacity
  from aggregate synthetic traffic and later authorized private-stage measurements.
  Historical 10/15m, 20/15m, 60/600 ceiling examples are **not universal approval**.
  Optional daily 100-attempt restriction remains deferred, not part of this plan.
- Approve cookie name/host/path, single-slot multi-account UX, cap/LRU messaging,
  rotation loss/replay trade-off, key/retirement/restore protocol and generation
  privilege hardening/risk disposition. Bind every management endpoint to a live
  trusted student identity and CSRF POST; no client owner ID trust.
- Independently verify a separately approved **real email backend** (E105 is empty
  today), TLS/credentials, SPF/DKIM/DMARC, delivery/bounce/outbox and bounded backlog.
  Backend class approval is not delivery acceptance. No provider is approved here.
- Implement and verify independent recovery issuance/redemption protections before
  any hard account_fail/account_success restriction. Current reset-request link
  invalidation/shared source redemption fails that readiness gate.
- Approve accessible recovery/support procedures with identity verification and
  incident escalation; never ask support to transmit passwords or raw reset tokens.
- Approve B3 event schema, independent pseudonym key, bounded dedup/drop accounting,
  priority for protection failures, collector access/export and retention. A.20's
  proposed 30-day retention is not an operationally accepted collector. Current
  B1b FAILURE/UNCLASSIFIED-only sink is not the completed B3 monitoring system.
- Approve concrete flag/rollout/rollback ownership, alerts and operator decision
  paths during DB/email failure. No automatic fail-open login or mode downgrade.
- Before real users: secure preflight E101–E105, external Gunicorn/proxy/raw-output
  privacy, tested TLS/worker/DB budgets, encrypted backup/restore, monitoring,
  incident response, privacy policy/student consent/support and accessibility.
  Staging destination and private beta require separate explicit authorizations.

## Acceptance, negative tests and monitoring

Use disposable PostgreSQL 17 with separated LOGINs/forced RLS, real lock observers
and clean-state readers. Keep the current 484 regressions, 27 browsers, 27/34
additional suites, 15/14 controls, audits/migration drift; add genuine tests per
separately authorized package and report actual counts and skips.

Test enrollment/reset/forget-all interleavings, generation decrement/restore risk,
wrong account/case/NFKC/forged IDs, stale hash recheck, one rotation winner/grace
loser, reordered/lost cookie responses, replay before/after 60s, 30-day boundaries,
key retirement, cap evictions and total cookie/header size. Mutation-drop owner/
UUID/generation/stamp checks and no-cookie-on-grace rule; must fail real assertions.

Quota tests: N+1 concurrent finalizations; 20 wrong passwords then permitted correct
login without exhausted success quota; success does not spend failure allowance;
T1 rollback/crash, every T2 statement failure/COMMIT uncertainty and conditional
release across rollover. Mutate success reservation before hashing, double refund,
unsigned/unscoped buckets, wrong-window release, overflow and partial session save.
Never rely on SQLite or mocked first cursor as proof of PG atomicity.

Campus tests: 11/61 distinct correct unfamiliar students sharing one address,
attacker flooding unfamiliar lanes while trusted students return, attackers with
own accounts/cookies spending trusted volume, mixed IPv4/mapped IPv6/shared /64,
spoofed forwarded headers and **all** source ceilings saturated. Record legitimate
refusals, hasher calls and latency distributions; source exceptions are finite
and never proxy trust or unlimited bypass. Distributed guessing and long-running
targeted lockout tests must show both security gain and residual student DoS.

Recovery tests: no trust on reset request; forged/expired/replayed/single-use tokens,
concurrent redemptions, post-reset stolen cookies, outage/recovery/backlog and
support escalation without raw secrets. Test valid recovery while login/account/
source attack buckets are saturated; the escape hatch must actually be independent.

Monitoring requires synthetic end-to-end exercises of protection-failure, dropped
and would_restrict events, replay, email backlog/outage, lockout/refusal fairness,
source saturation and recovery success. Only bounded aggregates/keyed pseudonyms,
never usernames/IPs/tokens/URLs/session keys. Alerts must have an on-call/runbook
owner, observed delivery and a tested response; configured dashboards alone fail.
Account enumeration is measured by distributions/side effects, not one equal time.

## Rollback, restore and independent gate

Rehearse enforce→observe→off and IP-bypass/device-off through the approved multi-
worker configuration mechanism. Existing password/session authentication remains
mandatory; disabling new restrictions does not disable baseline role guards,
CSRF/RLS/throttle. No request-time automatic downgrade, retries or compensation.
Report committed devices/counters/orphan sessions after failures; flag rollback
does not undo their writes or revoke all trust. If compromise/restore requires
invalidation, execute the separately approved generation/key revocation plan with
maintenance controls and prove no stale in-flight issuance survives. Never fake
migrations or reverse persistent security schema without a recovery plan.

Residuals: bearer replay, targeted unfamiliar lockout, campus/trusted-pool DoS,
response-loss trust eviction, generation SQL privilege, restore resurrection,
global signing-key coupling, email/support social engineering, diagnostic loss,
raw external output, runtime flag/graph mutability and uncertain COMMIT/delivery.
No activation is ready today. A separate reviewer must review this threat model;
Codex authored this proposal and B1b. Every S0-02B/C implementation, flag activation,
backend, destination environment and launch cohort needs its own owner work order,
independent evidence and exact-head/activation authorization. Stop at this proposal.
