# S0-02 reconciliation: Codex independent review vs. Claude design and S0-02A code

| Item | Value |
| --- | --- |
| Codex report reviewed | `docs/security/S0_02_INDEPENDENT_REVIEW.md` at `5890c5932e54ef1ef1db40128277bab7afa483b3` (remote branch `docs/s0-02-independent-review`, PR #27). All 497 lines were read. |
| Design Codex reviewed ("C") | `S1_PROPOSALS.md` at `e161be8` (design only; **predates** the S0-02A code) |
| S0-02A code reconciled | PR #26 branch `security/s0-02a-trusted-device-foundation`, previous head `0e9e478`, plus the identity correction in this commit |
| Baseline | `master` `64fe874` |
| Scope rule | Only the owner-authorized identity-binding correction (F02) is implemented here. Every other correction below is **proposed** and awaits approval. S0-02B and S0-02C are not started. PR #26 stays unmerged. |

Correction to my earlier report: the design-only merge commit on
`claude/upbeat-clarke-prrzc0` is **`e161be8`**. I previously cited it as `ff0ed96`, which was wrong.

## 1. Summary

| ID | Codex finding | Verdict | Severity (mine) | Stage | Status |
| --- | --- | --- | --- | --- | --- |
| F02 | Casefolded device binding selects another account's lane | **Agree, reproduced** | High | 02A | **Fixed in this commit** |
| F04 | Stale issuance after reset or forget-all | Agree | High | 02A schema, 02B wiring | Reset/change fixed in `0e9e478`. **Forget-all generation barrier implemented** (owner-approved; S1_PROPOSALS A.19 F). |
| F04b | Stale hash-upgrade setter can undo a password reset (baseline code) | **Agree, reproduced** | High (conditional) | Separate baseline fix | **Fixed in separate PR #29** (draft) |
| F01 | Failures consume the success quota | Agree | High | 02B design; no 02A schema change | **Proposed** (§4) |
| F06 | Contradictory DB-failure outcomes | Agree | High | 02B | Partly corrected in A.19 D; full stage table §5 |
| F05 | Concurrent rotation treated as theft | Partly agree | Medium (after `0e9e478`) | 02A, done; 02B | Grace plus no-cookie implemented; residual documented (§2) |
| F03 | Shared-IP ceilings deny campus logins | Agree | High (availability) | 02B policy | **Proposed**; needs owner policy and measurements |
| F07 | Recovery not independent of attack path | Agree | High (enforcement gate) | 02C | Proposed; blocks `enforce` |
| F08 | Cross-account deletion; LRU eviction | Agree | Medium | 02A/02B | Cross-account deletion was never implemented; design corrected. Cap UX needs a decision. |
| F09 | Signing key, 31-day CHECK, restore | Partly agree | Medium | 02A schema | **30-day CHECK implemented** and boundary-tested. Signing kept by owner decision. Restore runbook still to do. |
| F10 | Log deduplication and bounds | Agree | Medium | 02B | Proposed |
| F11 | Response similarity isn't an enumeration proof | Agree | Medium | 02B/02C | My design wording corrected; tests to use distributions |
| F12 | Codex's own design ("D") continuation | n/a (D-specific) | — | — | Noted; one compatibility point applies to C (§2) |

## 2. Finding-by-finding

### F02 — Casefolded identity binding (High). Agree; reproduced; fixed.

* **Facts verified in code:**
  * `Student.username` is `unique=True` and case-sensitive, so `Jordan` and `jordan` can both exist.
  * `StudentBackend.authenticate` uses exact `get(username=...)`.
  * Django's `AuthenticationForm` NFKC-normalizes the submitted value, and `create_user`/`full_clean` stores NFKC. Rows written without `clean()` keep their raw form.
  * S0-02A `0e9e478` bound devices with `username_key = HMAC(NFKC(u).casefold())` and matched with `_username_matches`.
  * `issue()` already required the exact username, but `check()` did not.
* **Reproduction (before the fix, PostgreSQL 16 local, real auth role):** `DeviceIdentityBindingTests` against the `0e9e478` code gave **13 failures**:
  * `Jordan`'s device was `trusted` for `jordan` and `JORDAN`;
  * `alpha`'s device was trusted for `Alpha`, `ALPHA` and fullwidth `ａｌｐｈａ`;
  * a stored-ligature account's device was trusted for the NFKC account, and vice versa.

  The backend authenticates none of these strings as the device owner.
* **Correction (implemented):**
  * Removed `username_key` (column, CHECK, grant guard). The binding is the immutable `student` UUID foreign key.
  * `check(cookie, username)`, before authentication, joins the device's student and requires `stored username == submitted username` exactly: the same semantics as `StudentBackend` on the form-cleaned value. There is no normalization or casefold inside the device code.
  * `rotate(cookie, student_id)`, after authentication, requires the authenticated student's **UUID**.
  * Django's username policy is unchanged.
* **Regression tests (8):**
  * `test_case_distinct_accounts_exist_and_backend_distinguishes_them`
  * `test_device_for_one_case_variant_never_selects_another_accounts_lane`
  * `test_device_check_agrees_exactly_with_backend_identity`: for each candidate string, trusted **iff** `StudentBackend` authenticates it as the owner.
  * `test_stored_non_nfkc_and_nfkc_accounts_are_never_interchangeable`
  * `test_issue_requires_the_exact_stored_username`
  * `test_rotation_requires_the_authenticated_student_uuid`
  * `test_forged_or_foreign_identifiers_never_select_the_trusted_lane`
  * `test_binding_is_the_student_foreign_key_not_a_username_hash`
* **Mutation evidence:**
  * Reintroducing casefold in `check()` gives 10 failures. That mutation used casefold only; the fullwidth case is covered by the pre-fix baseline run, which used NFKC plus casefold.
  * Dropping the UUID comparison in `rotate()` gives 3 failures.
* **Design follow-up:** the 02B `account_fail` bucket subject is also changed to the exact form-cleaned username (no casefold), so failures against `Jordan` can't restrict `jordan`.

### F04 — Stale issuance after revocation (High). Agree; partly fixed; epoch proposed.

* **Already in S0-02A (`0e9e478`, which Codex didn't review):**
  * `issue()` locks Student, requires the exact username, and requires the password-derived `credential_stamp` captured at verification.
  * `revoke_all()` locks Student first.
  * Tests: `test_issue_waiting_on_a_password_reset_cannot_recreate_trust` and `test_revoke_all_waits_for_inflight_issuance_and_removes_it`, using real row locks observed through `pg_locks`, and mutation-checked.
* **Remaining gap (Codex is right):** an explicit **forget-all without a password change** leaves the stamp unchanged. A login verified before forget-all and finishing after it could still insert a device. Row deletion can't delete a future insert.
* **Proposed 02A correction (not implemented, needs approval):** a monotonic per-student device generation in a new auth-only table:
  * Schema: `accounts_devicegeneration(student_id PK FK, generation bigint NOT NULL DEFAULT 0)`, no runtime grant.
  * `revoke_all` increments it under the Student lock.
  * `issue(..., generation=g)` must present the generation read **before** the password check, and is refused if it changed.
  * This avoids altering `accounts_student` or its grants.
  * Test: `test_issue_after_forget_all_with_unchanged_password_is_refused`, with barrier and row locks.

### F04b — Hash-upgrade setter can revert a password reset (baseline Milestone 3 code). Agree; reproduced.

* **Code:** `accounts/backends.py` `StudentBackend.authenticate` calls `student.check_password(password)`. Django's `AbstractBaseUser.check_password` passes a setter that saves an upgraded hash (`update_fields=['password']`) on a **stale model instance**.
* **Reproduction:** a scratch probe, not committed; real auth role; `PBKDF2PasswordHasher` with a 1,000-iteration stored hash that needs an upgrade:
  1. The login row is loaded.
  2. A reset commits, and the new password works.
  3. The stale instance verifies the old password.
  4. Result: **old password valid = True, new password valid = False.** The completed reset is silently undone.
* **Preconditions:** a stored hash that needs an upgrade (typically after a Django release raises PBKDF2 iterations), and a login with the old password racing the reset. That is the attacker's natural move against a victim recovering a compromised account.
* **Correction (proposed, separate authorization; changes authentication internals, not S0-02A):** verify with `django.contrib.auth.hashers.check_password(raw, encoded, setter=None)` against the loaded hash. Then upgrade only with a compare-and-swap, `UPDATE accounts_student SET password=%s WHERE id=%s AND password=%s` (the old encoded value), under the existing auth grants.
* **Test:** `test_stale_hash_upgrade_cannot_overwrite_reset` (deterministic interleaving, as in the probe).

### F01 — Success quota counted failures (High). Agree.

* **Affected:** design only (A.6.1–A.6.3, A.19 A). No S0-02A code uses `LoginLimit` yet.
* **Correction:** see §4. `account_success` is **acquired at finalization after verified credentials**, never reserved before the password check. No refunds are involved, so a wrong password can never consume it, even if a later step fails. As a hard gate it stays `observe`-only until the 02C recovery gate is met.
* **Stage:** 02B. The 02A `LoginLimit` schema needs no change.

### F06 — Contradictory DB-failure outcomes (High). Agree.

* The earlier "log and still complete login" text was already withdrawn in A.19 D.
* Codex also correctly notes that `DatabaseRoleBoundaryMiddleware` (`accounts/middleware.py`) only wraps the role checks, not the view or session save. 02B therefore needs explicit stage handling (§5) and fault injection at session save and response time.

### F05 — Rotation concurrency (Medium after `0e9e478`). Partly agree.

* **Implemented:** the row lock serializes rotations. Within 60 s, the loser gets `grace` with **no** Set-Cookie, so whatever order the responses arrive in, only one response ever sets a cookie. A lost conditional UPDATE never returns an unstored cookie. `grace` never selects trusted limits (`selects_trusted_limits` is false).
* **Residual (Codex is right):**
  * If the winning response is lost in transit, the browser keeps the old cookie. After 60 s its next use is treated as `replayed`, and the device is revoked: a legitimate loss of trust, falling back to the unfamiliar path.
  * A thief holding a previous identifier can deliberately trigger that revocation.
  * Owner decision: accept, or adopt explicit renewal (D-style) instead of per-login rotation.
* **Destructive action before the binding check:** replay revocation only ever deletes the record the presented identifier belongs to. It never touches another account's record. Keeping replay-first is intentional.

### F03 — Shared-IP ceilings (High availability). Agree.

* My A.12 claim that returning browsers "can't" suffer NAT denial was wrong while a shared `ip_ceiling` existed. A.19 B separates the trusted and unfamiliar ceilings.
* Codex is right that no universal number is safe, and that a proxy can't split a genuinely shared public NAT.
* Required: an owner-approved campus policy from measured bursts, and tests with all source-wide controls saturated. Stage 02B; no enforcement before approval.

### F07 — Recovery independence (High, gates enforcement). Agree.

* **Baseline facts:**
  * `reset_confirm` applies the `reset-confirm` source limit **before** checking the token (`accounts/views.py`).
  * A new reset request revokes earlier links (`tokens._issue_locked`), and a historical test asserts this.
* So recovery shares the attack path. The 02C design must provide coalesced issuance and an independently bounded redemption route, and must not let an unauthenticated request invalidate a victim's live link without a reviewed compatibility decision.
* The provider-outage runbook switching to `observe` is a manual risk decision, not recovery.

### F08 — Cross-account deletion and cap (Medium). Agree.

* S0-02A never implemented cross-account deletion; the design text is now corrected.
* LRU eviction at 10 versus refusal is an owner UX decision. Eviction only ever removes the student's **own** oldest device.

### F09 — Signing, CHECK and restore (Medium). Partly agree.

* `read_cookie` already enforces a 30-day signed max age; the implementation has it, unlike the design text Codex reviewed.
* **Proposed 02A changes:**
  * Tighten the CHECK to `expires_at <= last_used_at + interval '30 days'`.
  * Optionally add an independent `UCC_DEVICE_COOKIE_KEY` with a bounded retirement list instead of the generic `SECRET_KEY_FALLBACKS`.
  * Document that restoring device rows from a backup must be followed by a forget-all generation bump or a key retirement.
* The ORM uses CASCADE while the DB constraint is NO ACTION. Deletion is ORM-driven, and no account-deletion feature exists.

### F10 / F11 — Logging and enumeration (Medium). Agree.

* My phrase "reveals nothing beyond a device" overstated it: a stolen valid cookie can probe candidate usernames.
* 02B needs durable or bounded deduplication, priority for protection-failure events, independently keyed pseudonyms, and enumeration tests that compare bounded timing distributions rather than asserting equal times.

### F12 — D-specific

Not applicable to C. One point does apply: preserving all historical tests holds
only for feature-off profiles. Any enabled profile that changes reset-link
semantics needs explicit approval.

### Codex §5 point: dormant rollout outage

`require_auth_role` intentionally returns 503 site-wide when `accounts.0003`
exists without grants. That is fail-closed by design and documented in
`AUTHENTICATION.md`, but it is an operational outage risk. Rollout order must be
migrate, then provision, then deploy code, in one maintenance step, and the
rollback must be tested. The owner may prefer failing only at first use; that is
a decision, not a defect.

## 3. Priority 3 — Revocation and rotation

| Event | S0-02A today | Proposed |
| --- | --- | --- |
| Password reset or change | Stamp refuses stale `issue`. `revoke_all` (Student lock) deletes all devices, including rows mid-rotation. | 02B wires `revoke_all` into the same auth transaction as the password update |
| Explicit forget-all | Deletes all existing rows | **Generation table** (F04) so in-flight logins can't re-insert |
| Deactivation | Lookups ignore inactive students; `issue` refuses | — |
| Replay or grace | Replay after 60 s revokes. Grace gets no cookie, no renewal, and **no trusted limits**, so it can't multiply guessing allowance. | — |

## 4. Priority 2 — Quota accounting (02B design, proposed)

**Taxonomy:**

| Counter | Counts |
| --- | --- |
| Admission (`ip_ceiling_*`) | Every admitted password evaluation |
| Failure buckets | Failed evaluations |
| `account_success` | Committed sessions |

**Protocol:**

1. **Admit** (auth transaction T1, committed **before** hashing). Upsert the admission and failure buckets in sorted order. If any is over its limit: roll back T1 and return 429 with no hash. Otherwise commit, so the failure buckets now hold a provisional unit.
2. **Verify** the password outside any transaction, without the auto-upgrade setter (F04b).
3. **Finalize** (auth transaction T2):
   * Lock Student.
   * Recheck active status, the credential stamp and the device generation.
   * Upsert `account_success` (+1). If that would exceed the limit, roll back T2: in `observe` mode log only; in `enforce` mode return 429 with no session.
   * Release the provisional failure units (`-1 WHERE expires_at = reserved window`).
   * Rotate or issue the device.
   * Create the session.
   * Commit.
4. **On a failed password:** nothing more is needed. The provisional unit becomes the failure, and `account_success` is never touched.

**Invariants**, all in one database, using only atomic upserts and conditional updates:

* `account_success` changes only in a T2 that also commits a session, so wrong passwords, rollbacks and crashes can never consume it.
* Failure units can be over-counted (by a crash between T1 and T2, or a T2 rollback) but never under-counted, so the count stays conservative.
* Releases never touch a newer window.

**Tests (02B):**

* `test_failures_never_touch_success_quota`: 20 failures across windows, then a trusted correct login is admitted.
* `test_success_quota_only_counts_committed_sessions`: T2 fault injection.
* `test_concurrent_finalizations_never_exceed_success_limit`: N+1 threads.
* `test_t1_rollback_consumes_nothing`
* `test_crash_between_t1_and_t2_counts_as_failure_only`

## 5. Priority 4 — Exact commit points (02B design, proposed)

| Stage | Commits | On DB error |
| --- | --- | --- |
| 0. Role check (middleware) | — | 503, nothing evaluated |
| 1. Device classification (`check`) | Replay revocation only | 503, no hash |
| 2. Admission T1 | Admission and failure reservations | 503, no hash, nothing committed |
| 3. Password verification | Nothing (no setter) | — |
| 4. Finalization T2 | Success unit, failure release, device rotate/issue, **session row** | Rollback: 503, **no session, no cookie**, old device identifier still valid. Reservations stay counted. |
| 5. Response | Set-Cookie for the session and device, only after T2 commits | Cookie not sent: the user retries, with nothing trusted created |
| 6. Logging | After commit, never while holding locks | Dropped events are counted, never block auth |

Django's `SessionMiddleware` normally saves the session at response time.
02B must create the session row **inside T2** (an explicit save in finalization)
so that a session can't be created after a failed T2, and a session-save failure
can't leave a committed device without a session.

## 6. Owner decisions recorded

* Identity (UUID) correction: accepted.
* F04b: fixed separately in PR #29.
* Generation table and 30-day contract: implemented in PR #26.
* Signing, LRU cap and dormant rotation: kept.
* §§4–5: accepted as the S0-02B starting point, strengthened in S1_PROPOSALS A.20.
* Account enforcement: blocked by A.21.

## 6a. Decisions originally requested

1. Approve the F04 device-generation table (02A schema).
2. Approve the F09 30-day CHECK and decide on an independent device key (02A).
3. Authorize a separate fix for F04b in baseline `StudentBackend`.
4. Accept or replace per-login rotation (F05 residual).
5. Choose LRU eviction or refusal at the cap (F08).
6. Approve the §4 quota protocol and §5 commit points as the 02B baseline.
7. Set the campus availability policy (F03) and the recovery-independence requirements (F07).
