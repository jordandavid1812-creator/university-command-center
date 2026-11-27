# Remediation plan — proposed, awaiting review

Nothing here is authorized yet. Stage S0 made no application changes. Each item
names the smallest change, the tests that must keep passing, and the decision
the project owner needs to make. Work would be done on a separate security
branch from an agreed baseline. It would never be done on a Codex branch, and
nothing would be merged automatically.

## Release-gate status at baseline `fefd3ca`

| Gate | Status |
| --- | --- |
| No unresolved confirmed critical (P0) findings | Met in reviewed scope |
| Every confirmed P1 finding fixed or a documented blocker | Met (none confirmed) |
| Cross-student isolation, RLS, auth/session, CSRF tests pass | Met (local PG16; CI PG17) |
| Dependency audit passes | Met |
| CI passes on proposed commit | Met for baseline (run 43027238277) |
| Public deployment approved | **No.** S0-01, S0-02, S0-07, S0-08, S0-12 and the existing deployment items in `docs/AUTHENTICATION.md` block it. |

## Stage S1 — critical and high-risk

**S1 outcome (owner decisions, 2026-11-11):** S0-01 implemented (IPv6 /64 grouping; opt-in trusted proxies, disabled everywhere; IP limit otherwise unchanged). S0-02 paused because the approved hard limit creates a targeted lockout; proposal in `S1_PROPOSALS.md` section A. S0-03 design in section B, not implemented.

No P0 or P1 finding was confirmed, so **S1 has no mandatory work**. I recommend
pulling the two authentication-abuse P2s into S1, because they are the most
exploitable once any non-local exposure happens:

| Order | Finding | Change | Size | Owner decision needed |
| --- | --- | --- | --- | --- |
| 1 | S0-02 | Add an account-keyed throttle bucket (HMAC of normalized username) to the login view, alongside the IP bucket. Same generic 429. Unknown usernames counted identically. Soft limit with no permanent lockout. | ~20 lines + tests | Limit values (proposal: 10 failures per 15 min per account) |
| 2 | S0-01 | Add a `client_address(request)` helper. Default behaviour is unchanged (`REMOTE_ADDR`). Optional `UCC_TRUSTED_PROXIES` setting allows right-most untrusted `X-Forwarded-For` derivation. IPv6 grouped by /64. | ~30 lines + tests | Whether to add proxy support now or only the IPv6 grouping |

Tests that must stay green: all 113 legacy, 2A, 46 security, 63 auth and 52 web
tests, unchanged. New tests go in new files.

## Stage S2 — medium-risk and defence in depth

| Order | Finding | Change | Notes and risks |
| --- | --- | --- | --- |
| 3 | S0-03 | Per-owner create caps in `academics/services.py` (in the student transaction, race-safe), plus a write throttle for website POSTs | **Product policy decision:** cap values. Proposal: same as existing read limits (200 semesters, 1,000 courses), and an assignment cap to be agreed. Must not change any GPA calculation. |
| 4 | S0-06 | Legacy `course` POST rejects a missing `actual_grade` | Check that auth tests don't depend on the omission. Optionally disable legacy routes in website profiles only. |
| 5 | S0-07 | In-repo CSP middleware (strict, no `unsafe-inline`). HSTS and proxy-SSL header only in a future deployment profile. | Verify every page in a browser (S3-BR-01) before enforcing. Start report-only if unsure. |
| 6 | S0-12 | `LOGGING` to stderr with a redaction filter; security events for login failure, 429, token failure, role-boundary 503 | Must never log token URLs, session keys or SQL parameters |
| 7 | S0-08 | Secure profile refuses a non-loopback DB unless `sslmode=verify-full` | Settings-only |
| 8 | S0-13 | Move reset and verify secrets out of the URL after the first GET (session-stored, Django pattern) | Touches Milestone 3 flow. Keep existing token tests passing. |
| 9 | S0-09 | DB trigger or CHECK: auth-role inserts must have `email_verified_at IS NULL` | New migration, so needs migration security review per `DATABASE_SECURITY.md` |
| 10 | S0-11 | **Proposal only:** per-connection memo of role checks and request-scoped session re-validation | Architectural. Weakening risk. Needs a written design and explicit approval before code. |
| 11 | S0-14 | Separate capability key from DB context key; plan backup encryption and rotation | Needs env-var and runbook changes |
| 12 | S0-04 / S0-05 | Decide on the enumeration trade-off; queue email delivery before real SMTP | Product decision; S0-05 needs measurement once SMTP exists |
| 13 | S0-10 | Runbook: dedicated cluster, revoke PUBLIC CONNECT/TEMP on other databases | Docs and provisioning only |
| 14 | S0-15, S0-16 | Branch protection with required checks; "sign out other sessions" feature | Repository settings (owner action); feature needs a task |

## Stage S3 — adversarial verification

Run the planned rows in `SECURITY_TEST_MATRIX.md` section 4: browser CSP
check, real cross-origin POSTs, a proxy in front of the app, concurrent quota
races, a bounded load test, and a PostgreSQL 17 re-run.

## Stage S4 — pentest readiness

Finalize `PENTEST_HANDOFF.md`: add measured results, update the open-risk
register and attach the final verification evidence.

## Coordination with Codex

* Baseline for any S1 branch: `fefd3ca`, or whatever `master` is at that time. Rebase before review if `master` has moved.
* S0-01, S0-02 and S0-03 touch `accounts/views.py`, `accounts/throttling.py` and `academics/services.py`. Any concurrent Milestone 4B edits to those files must be coordinated.
