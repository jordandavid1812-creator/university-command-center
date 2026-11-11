# Security audit — Stage S0 (read-only baseline)

| Item | Value |
| --- | --- |
| Commit audited | `fefd3cae4efeac5539bc3f02e9ffdc53bfb88766` (master, PR #23 merge) |
| Auditor role | Independent security review (Claude Code). Separate from the feature agent. |
| Branch | `claude/upbeat-clarke-prrzc0` (documentation only; no application code changed) |
| Codex work in progress | None found. No open feature PR or 4B branch. Dependabot PRs #18 and #19 are open. |
| Data used | Synthetic identities (`alpha`, `bravo`, `*@example.invalid`) in disposable databases only |

## 1. Executive summary

**No P0 or P1 finding was confirmed in the reviewed scope.** These were tested
and held:

* cross-student access (IDOR) on every page and legacy endpoint
* forged owner and parent fields
* forged PostgreSQL context
* runtime and auth role separation
* CSRF
* stored and reflected XSS
* open redirect
* Host-header poisoning

The weaknesses found are in **abuse resistance and deployment readiness**, not
in data isolation. The three P2 findings are all confirmed by probes:

1. **S0-01** Login throttling uses only the socket IP. Behind any reverse proxy or NAT, one attacker can lock every user out of login.
2. **S0-02** There is no per-account login limit. One account can be password-guessed from many IP addresses without limit.
3. **S0-03** There is no per-student record quota and no write rate limit. One verified account can grow the shared database without bound.

None of these leaks another student's data. S0-01 and S0-02 matter most once
the site is reachable by anyone other than the local user, and the site is not
approved for that.

This audit does not show that the application is secure or ready for a
penetration test. It records what was tested, what was observed, and what was
not tested (section 6).

### Five highest-priority risks

| Rank | ID | Title | Priority | State |
| --- | --- | --- | --- | --- |
| 1 | S0-02 | No per-account brute-force limit | P2 | Confirmed vulnerability |
| 2 | S0-01 | IP-only throttle: shared-IP lockout and proxy/IPv6 bypass | P2 | Confirmed (proxy impact depends on deployment) |
| 3 | S0-03 | No per-student record quota or academic write rate limit | P2 | Confirmed |
| 4 | S0-07 | No CSP or HSTS, and HTTPS/proxy settings missing from the secure profile | P3 | Control not implemented |
| 5 | S0-11 / S0-12 | Per-request query amplification, no security logging | P3 | Confirmed (measured) / Control not implemented |

## 2. Methodology and environment

* Read AGENTS.md, ARCHITECTURE, DATABASE_FOUNDATION, DATABASE_SECURITY, AUTHENTICATION, STUDENT_WEBSITE and the milestone reviews, then every file under `server/` that is not a test.
* Re-ran every existing suite with hashed locks on Python 3.12.
* Wrote 10 bounded probe tests. They were run from the scratchpad through the project's own `web_test` harness, using real separate runtime, auth and migrator LOGIN roles. They are not committed. The probe source is reproduced in `SECURITY_TEST_MATRIX.md` so the results can be repeated.
* Tools: pip-audit 2.10.1, Bandit 1.9.4, detect-secrets 1.5.0, `git grep` across all 46 commits, and `manage.py check --deploy`.
* **Environment deviation:** the session network blocks the PGDG repository, so local verification used **PostgreSQL 16.15**, not 17. The same suites ran on **PostgreSQL 17 in GitHub CI** for this exact commit and passed (run 43027238277). PG16 results are supporting evidence, not a substitute for the project's PG17 requirement.
* Semgrep could not run because its rule registry (semgrep.dev) is blocked. It is recorded as **Unable to test**.

## 3. Findings

Severity follows the program's P0–P3 scale. CWE IDs are given where one clearly
fits. OWASP WSTG v4.2 test IDs are given where I am confident of them. ASVS 5.0
is cited by chapter name only, because exact requirement IDs should be mapped
by the human tester rather than guessed here.

---

### S0-01 — Throttle keyed solely on REMOTE_ADDR (shared-IP lockout; proxy and IPv6 weaknesses)

* **State:** Confirmed vulnerability. Impact depends on deployment topology.
* **Priority:** P2. CWE-307 and CWE-770. WSTG-ATHN-03. ASVS Authentication chapter (anti-automation).
* **Component / boundary:** `server/accounts/throttling.py:14`, TB2 (browser to session).
* **Scenario:** The site sits behind a TLS-terminating reverse proxy, or many students share a campus NAT. In both cases `REMOTE_ADDR` is the same for everyone. An attacker sends 10 failed logins in 15 minutes, and every user then gets HTTP 429 at login. The same applies to registration and reset (5 per hour). In the other direction, an IPv6 attacker gets a fresh bucket for every /128 address.
* **Affected:** availability of login, registration and recovery for all students.
* **Demonstration (P02):** 10 failed logins from `192.0.2.10` for `alpha`. A legitimate login for `bravo` from the same address returned **429**.
* **Root cause:** No trusted-proxy client-IP derivation and no IPv6 prefix grouping. The project's docs acknowledge this ("IPv6/proxy policy needs production review").
* **Fix (minimal):** Add an explicit, settings-driven way to get the client address. Default stays `REMOTE_ADDR`. Optionally, use `X-Forwarded-For` only from a configured list of trusted proxy addresses, counting hops from the right. Group IPv6 addresses by /64. Do not trust headers by default. Pair this with S0-02 so the IP limit is not the only control.
* **Regression test:** With a trusted proxy configured, two different forwarded client addresses get separate buckets. Without it, spoofed `X-Forwarded-For` is ignored. Two IPv6 addresses in the same /64 share a bucket.

### S0-02 — No per-account login attempt limit

* **State:** Confirmed vulnerability.
* **Priority:** P2. CWE-307. WSTG-ATHN-03. ASVS Authentication chapter.
* **Component:** `server/accounts/views.py:41-51`, `server/accounts/backends.py:8`.
* **Scenario:** A botnet or rotating proxy pool sends guesses for one known username, each from a new address. No counter is keyed on the target account.
* **Affected:** account takeover, which exposes that student's grades and records. The password policy (12+ characters, common-password list) reduces but does not remove this risk, especially for credential stuffing with reused passwords.
* **Demonstration (P03):** 40 wrong passwords for `alpha` from 40 different addresses all returned **200** (none throttled). The correct password then succeeded (**302**).
* **Root cause:** By design, only per-IP buckets exist. The docs say account-target controls are future work.
* **Fix:** Add a second bucket keyed on `salted_hmac(action|normalized username)`, with a soft limit such as 10 failures per 15 minutes and progressive delay. Return a generic 429 so the response does not show whether the account exists. Avoid permanent lockout, which would let attackers deny service to a victim. Count unknown usernames the same way to avoid an enumeration difference. Policy values need owner approval.
* **Regression test:** N failures for one username from N distinct addresses lead to 429 for that username only. Another account is unaffected. An unknown username behaves the same as a known one.

### S0-03 — No per-student record quota or academic write rate limit

* **State:** Confirmed vulnerability.
* **Priority:** P2 (availability affecting all tenants; needs a verified account). CWE-770. WSTG-BUSL-05.
* **Component:** `server/academics/services.py:97-107` (create), all `student_web` POST views.
* **Scenario:** A verified student scripts the creation forms with their own session and CSRF token. They can create millions of semesters, courses or assignments. Their own analysis pages fail closed once past 1,000 courses or 200 semesters (`WorkspaceLimit`). Creation itself is never limited, so database storage and backup size grow for everyone. Registration is limited to 5 per hour per IP, so an attacker can also run several accounts.
* **Demonstration (P04):** 60 rapid creations all returned **302**, and 60 rows were stored. Nothing was throttled.
* **Root cause:** Read-side limits exist (`academics/queries.py:14-16`), but there is no matching write-side cap or rate limit.
* **Fix:** Enforce per-owner caps at creation in the service layer, in the same student transaction, aligned with the existing read limits (the exact numbers are a product decision). Add a per-session or per-account write throttle that reuses the existing atomic throttle table. Note that a SELECT-count-then-insert cap can be raced. Use a lock on the owner's parent row or a DB-side check, and test it with concurrent requests.
* **Regression test:** Creating record cap+1 fails with a friendly 4xx and stores nothing. Concurrent creates cannot exceed the cap. Burst writes beyond the throttle get 429.

### S0-04 — Username enumeration through registration email behaviour

* **State:** Confirmed vulnerability (low impact).
* **Priority:** P3. CWE-204. WSTG-IDNT-04.
* **Component:** `server/accounts/tokens.py:44-53`.
* **Scenario:** The attacker registers `target_username` with an email address they control. If the username is taken, an `IntegrityError` occurs and no email is sent. If it is free, a verification email arrives. The HTTP responses are byte-identical, but the attacker's inbox tells them the answer. Usernames are login identifiers, so this feeds S0-02.
* **Demonstration (P01):** Existing username gave 0 emails. New username gave 1 email. Responses were identical.
* **Fix options (needs owner decision):** (a) Accept and document it as an inherent trade-off of unique usernames, and rely on S0-02 limits. (b) When the email address already exists, send that address an "account already exists" notice so email existence is not inferable. This does not fix the username case. (c) Make login use email instead of username. That is a product change and is not recommended in S1.
* **Regression test:** Depends on the option chosen.

### S0-05 — Email-existence timing difference (synchronous delivery)

* **State:** Likely vulnerability requiring verification.
* **Priority:** P3. CWE-208. WSTG-IDNT-04.
* **Component:** `server/accounts/tokens.py:41` (`on_commit` delivery inside the request), `:56` (`request_email`), `:44` (register).
* **Scenario:** With a real SMTP backend (`EMAIL_TIMEOUT=10`), the "account exists and is eligible" path of reset or resend performs a network send before responding. The unknown-account path returns immediately. The response time therefore reveals whether an email address is registered.
* **Evidence:** Code path difference only. **Not measured**, because only console and locmem backends exist. The project's docs already note "Generic email responses do not promise constant timing".
* **Fix:** Send email through a queue or background worker so the request path is constant-work, before any real email provider is configured.
* **Regression test:** Patch the delivery function to sleep, then confirm the response time is the same for known and unknown addresses.

### S0-06 — Legacy JSON academic endpoints still routed; missing field clears a grade

* **State:** Confirmed (integrity hardening and attack-surface reduction).
* **Priority:** P3. Own records only, CSRF-protected.
* **Component:** `server/config/web_urls.py:5` includes `config.auth_urls`. `server/accounts/views.py:192-193` passes `request.POST.get('actual_grade')`, which is `None` when the field is absent.
* **Scenario:** A student or a buggy client POSTs `version` without `actual_grade` to `/accounts/academic/courses/<own uuid>/`. The saved grade is silently set to ungraded. This is a second write path with different validation from the website's `StrictForm`.
* **Demonstration (P05):** Foreign GET, POST and delete returned **404/404/404**, and B's grade was unchanged. Own POST without the field returned **200** and the grade became **None**.
* **Fix:** Require the `actual_grade` key to be present (reject when absent). Separately, consider disabling the legacy demonstration routes when `STUDENT_WEBSITE_ENABLED` is true. Existing auth tests rely on them in `auth_test`, so they must be kept there.
* **Regression test:** A POST missing `actual_grade` returns 400 and the grade is unchanged. All 63 existing auth tests still pass.

### S0-07 — No Content-Security-Policy; HSTS, SSL redirect and proxy-SSL settings absent

* **State:** Security control not implemented. Partly Future (deployment).
* **Priority:** P3. CWE-693. WSTG-CONF-07 and WSTG-CONF-12.
* **Component:** `server/config/settings/auth_common.py`, `web_common.py`, `web_secure.py`.
* **Evidence (P06 and `check --deploy`):** No `Content-Security-Policy` header. `security.W004` (HSTS) and `security.W008` (SSL redirect) are raised for `web_secure`. `SECURE_PROXY_SSL_HEADER` is unset, so behind a TLS-terminating proxy `request.is_secure()` is false. That breaks Django's HTTPS Origin/Referer CSRF checks and pushes operators towards unsafe workarounds.
* **Verified present:** `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, `Cache-Control: no-store, private`.
* **Fix:** Templates contain **no inline script or style** and no third-party assets. A strict policy is therefore feasible without `unsafe-inline`: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'`. Django 5.2 has no built-in CSP, so a tiny in-repo middleware would be needed (no new dependency). Add HSTS and the proxy-SSL header only in a reviewed deployment profile, not in local profiles.
* **Regression test:** Every page sends the CSP header. A browser-rendering check (Playwright, in a later stage) shows no CSP violations on any page.

### S0-08 — Database TLS defaults to `sslmode=prefer`

* **State:** Security hardening opportunity (deployment).
* **Priority:** P3. CWE-319.
* **Component:** `server/config/settings/base.py:37`.
* **Scenario:** If the database is ever off-host, `prefer` falls back silently to plaintext and does not verify the server certificate. An attacker on the network could then capture runtime or auth credentials, session data and grades, or impersonate the database.
* **Fix:** The secure profile should require `verify-full` whenever the database host is not loopback, and fail to start otherwise.
* **Regression test:** A settings test shows that `web_secure` with a non-loopback host and `prefer` raises `ImproperlyConfigured`.

### S0-09 — Auth role can INSERT any `accounts_student` column

* **State:** Security hardening opportunity (defence in depth; needs auth-role compromise or a code bug).
* **Priority:** P3. CWE-269.
* **Component:** `server/accounts/management/commands/configure_auth_role.py:45`.
* **Evidence (P09):** `has_column_privilege(auth, accounts_student, is_active / email_verified_at, INSERT)` is **true / true**. UPDATE is correctly limited, so `is_active` and `email` updates are denied.
* **Impact:** Anyone with the auth connection (for example through a future injection bug) can create pre-verified active accounts, skipping email verification. That role can already read sessions and hashes, so the extra impact is limited.
* **Fix:** Django inserts every column, so a column-limited INSERT grant would break the ORM. Use a DB `BEFORE INSERT` trigger or CHECK instead, so the auth role can only insert `email_verified_at IS NULL`. Get migration review first.
* **Regression test:** A direct SQL insert by the auth role with `email_verified_at` set fails. Registration still works.

### S0-10 — Cluster-level PUBLIC defaults: other databases, TEMP, large objects

* **State:** Security hardening opportunity.
* **Priority:** P3.
* **Component:** `configure_runtime.py` and `configure_auth_role.py` only revoke privileges inside the application database.
* **Evidence (P09):** The runtime role has `CONNECT` and `TEMP` on the `postgres` database (cluster default), and `lo_from_bytea` **succeeded** (large objects need no table privilege). `require_runtime_role` checks `pg_class` ownership only, so it does not notice runtime-owned large objects. Verified denied: TEMP or CREATE in the app DB, `SET ROLE` to the migrator, the key table, `ucc_crypto`, and account tables.
* **Impact:** Only matters if runtime credentials are compromised. It allows storage abuse and a foothold outside the app DB. No path to student data was found.
* **Fix:** Document a dedicated cluster as a requirement, and `REVOKE CONNECT, TEMP ON DATABASE postgres, template1 FROM PUBLIC` in provisioning runbooks. Optionally have `require_runtime_role` also check `pg_largeobject_metadata`.
* **Regression test:** Role-check tests that assert runtime cannot connect to other databases (in a disposable cluster).

### S0-11 — Per-request database amplification and connection churn

* **State:** Confirmed (measured).
* **Priority:** P3. CWE-770.
* **Component:** `server/accounts/middleware.py:17-18` (two catalog privilege queries on **every** request, including anonymous ones), `server/academics/ownership.py:70-75,141` (session and role re-validation for every service call), `config/settings/base.py:36` (`CONN_MAX_AGE=0`: two new DB connections per request).
* **Evidence (C01/C02, PG16 local, single user):** Anonymous `GET /accounts/login/` used 3 queries. Dashboard used **48 queries** (20 runtime + 28 auth), course list 47, overview 31, all at about 30–54 ms. The migrator connection had 0 queries.
* **Impact:** A large cost multiplier for unauthenticated floods and for connection limits. This is not a confidentiality issue. The repeated re-validation is a deliberate safety property and **must not be removed casually**.
* **Fix (architectural; proposal only):** Cache `require_*_role` results per connection for the life of that connection, and re-validate the session once per request with a request-scoped memo still bound to the session key and auth hash. Any change needs the full suites plus a new test that logout or password change mid-request still invalidates later requests.
* **Regression test:** `assertNumQueries` budgets per page, plus all existing session-invalidation tests.

### S0-12 — No logging configuration or security event log

* **State:** Security control not implemented.
* **Priority:** P3. CWE-778. ASVS Security Logging and Error Handling chapter.
* **Evidence:** No `LOGGING` or `ADMINS` in any settings file. With `DEBUG=False`, Django's default sends `django.request` errors to `mail_admins`, which has no recipients. Unhandled-exception tracebacks are therefore lost for operators. Failed logins, 429s, token failures and role-boundary 503s are not recorded. Users correctly see only generic error pages (verified in existing tests).
* **Fix:** Add structured logging to stderr with redaction (never log token URLs, session keys, passwords or SQL parameters), and specific security events. No new dependency is needed.

### S0-13 — Recovery and verification secrets in URL path

* **State:** Security hardening opportunity. Documented by the project as a pre-production item.
* **Priority:** P3. Closest CWE: CWE-598.
* **Component:** `server/config/auth_urls.py:9,11`. The form posts back to the secret-bearing URL.
* **Mitigations present:** One-use, 1-hour (reset) and 24-hour (verify) lifetimes; digest-only storage; `Referrer-Policy: same-origin`; no third-party resources; consumption invalidated by password change.
* **Fix:** Follow Django's `PasswordResetConfirmView` pattern: on GET, validate the token, store it in the session, and redirect to a token-free URL. Redact paths in access logs.

### S0-14 — Single signing key for capabilities and DB context; key copy inside the database

* **State:** Security hardening opportunity.
* **Priority:** P3.
* **Component:** `academics/ownership.py:25-36`, `migrations/0004_student_rls.py` (`context_key`, plus a non-constant-time `<>` comparison at line 32).
* **Analysis:** Payload domains are separated (`identity|`, `identity-session|`, `verified-session|`, `transaction|`), so cross-use was not found. However, the key copy in `ucc_security.context_key` is readable by the migrator and would be present in any DB backup. With that key, runtime credentials could forge any owner context, and the key also signs in-process web capabilities. The PL/pgSQL `<>` comparison is not constant-time. Exploiting that would need runtime SQL access plus fine timing, and the signature is bound to the xid and PID, so this is informational.
* **Fix:** Use a separate capability key that never leaves the web process. Make backup encryption and key rotation mandatory before any backups exist.

### S0-15 — `master` branch not protected

* **State:** Security hardening opportunity (process / supply chain).
* **Priority:** P3.
* **Evidence:** The GitHub API reports `protected: false` for `master`. CI is not a required check, and direct pushes are possible. Two Dependabot PRs for GitHub Actions major versions (#18, #19) are open.
* **Fix:** Enable branch protection with required CI jobs (`tests`, `dependency-audit`, `database-tests`) and require a PR review. Review and merge the Actions bumps after checking compatibility.

### S0-16 — Unlimited concurrent sessions; no "sign out other sessions"

* **State:** Security hardening opportunity.
* **Priority:** P3.
* **Notes:** Verified good: 30-minute absolute server expiry, browser-session cookie, rotation at login, password change or reset invalidating all sessions. Missing: a way to revoke other sessions without changing the password, and any visibility of active sessions.

## 4. Existing protections verified

| Area | Evidence |
| --- | --- |
| Cross-student read/edit/delete on all 3 record kinds, pages and legacy JSON routes; same 404 for foreign and missing | Existing `web_tests`/`auth_tests` (run); P05 |
| Parent forging (course to foreign semester, assignment to foreign course) | Existing `test_parent_choices_and_filters_cannot_select_another_owner` |
| Client-supplied `owner`, `id`, `record_version`, `updated_at` rejected | Existing `test_client_owner_ids_and_server_fields_are_rejected` |
| Optimistic concurrency (stale version gives 409; simultaneous edits) | Existing security and web suites |
| CSRF on every academic POST, predictor and planner | Existing test (run) |
| Stored XSS markers in label, name and title across 8 pages plus predictor POST; reflected query parameter | P07: 0 unescaped occurrences |
| Login ignores `next`; foreign Host returns 400 | P08 |
| Security headers and no-store | P06 |
| Request body over 64 KB and over 600 fields return 400 | C03 |
| RLS enabled and **forced** on all 3 tables; exactly one `FOR ALL` policy each with USING and WITH CHECK; no extra permissive policies | P09 (live catalog) |
| Verifier: `SECURITY DEFINER`, `search_path=pg_catalog`, EXECUTE only for migrator and runtime | P09 |
| Runtime denied: account and session tables, key table, `ucc_crypto`, `owner_id` update, TEMP/CREATE in app DB, `SET ROLE` | P09 |
| Forged unsigned `ucc.student_id` sees 0 rows | P09; existing replay tests |
| Auth role denied: academic tables, verifier, `is_active`/`email` update | P09 |
| No PUBLIC table grants in `public` or `ucc_security` | P09 |
| Web requests issue 0 queries on the migration connection | C01/C02; existing test |
| Dependency advisories | pip-audit: "No known vulnerabilities found" on both hashed locks |
| Static analysis | Bandit: 0 findings in non-test application code |
| Secrets | No credentials found in the working tree or any of the 46 commits (patterns listed in the matrix). One hit in the CI workflow is a runtime `secrets.token_urlsafe` generator (false positive). |
| Personal data in history | `courses.json`/`assignments.json` were added in `fe511c9` and removed in `d51ed5f`. Already recorded in `docs/FOUNDATION_REVIEW.md`. **Contents were not opened.** Provenance remains an open owner decision. |

## 5. Not applicable

File upload, download and storage risks (no upload feature). Admin-site risks
(not installed). Third-party OAuth and social login (not implemented). JWT and
API tokens (none).

## 6. Not tested, or blocked

| Item | Reason |
| --- | --- |
| PostgreSQL 17 locally | PGDG repository blocked by network policy. PG16 used locally; PG17 covered by CI run 43027238277. |
| Semgrep rulesets | semgrep.dev blocked by network policy |
| Real SMTP timing (S0-05) | No email provider configured, by design |
| Browser-level CSP and CORS behaviour, real cross-origin requests from a browser | Deferred to S3 (Playwright available but out of S0 time box) |
| Reverse-proxy behaviour (S0-01, S0-07) | No proxy deployed; analysed from code |
| External connection pooler (PgBouncer) | Not deployed |
| Load and DoS testing beyond 60-request bursts | Excluded by rules of engagement for S0 |
| GitHub secret scanning and code scanning status | Not queried in S0 |
| Historical JSON contents | Deliberately not inspected (AGENTS.md: never print student records) |
