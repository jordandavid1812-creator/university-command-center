# Security test matrix — Stage S0

Commit: `fefd3cae4efeac5539bc3f02e9ffdc53bfb88766`. All data is synthetic
(`alpha`, `bravo`, `*@example.invalid`). Result values: **PASS** (secure
behaviour observed), **FAIL** (finding), **N/T** (not tested), **BLOCKED**
(environment).

## 1. Suites executed (2026-11-11, local)

Environment: Python 3.12, hashed `requirements-lock.txt` plus
`requirements-django-lock.txt`, and a disposable loopback **PostgreSQL 16.15**
cluster (PG17 is unavailable in this sandbox; see the audit's section 2). Each
suite ran in a separate test database with real separate LOGIN roles, as in CI.

| Suite | Command (settings) | Result |
| --- | --- | --- |
| Repository safety | `python tools/check_repository_safety.py` | passed |
| Legacy CLI/Streamlit | `python -m unittest discover` | 113 tests OK |
| Django checks | `manage.py check`; `makemigrations --check --dry-run` | no issues; no changes |
| 2A foundation | `test accounts academics --settings=config.settings.test` | OK |
| 2B security (RLS, roles, signing) | `test security_tests --settings=config.settings.security_test` | 46 tests OK |
| Milestone 3 auth | `test auth_tests --settings=config.settings.auth_test` | 63 tests OK |
| 4A website | `test web_tests --settings=config.settings.web_test` | 52 tests OK |
| S0 probes | `test s0_probes --settings=config.settings.web_test` | 10 probes ran (observations below) |
| Deploy check | `check --deploy --settings=config.settings.web_secure` | W004 (HSTS), W008 (SSL redirect) |
| pip-audit 2.10.1 | `--strict --require-hashes` on both locks | No known vulnerabilities |
| Bandit 1.9.4 | `-r server *.py tools` | 0 findings in application code (test fixtures and the git subprocess only) |
| Secret scan | detect-secrets (tree) + `git grep` patterns across all 46 commits | No credentials (1 false positive, see audit) |
| Semgrep | p/django, p/python, p/secrets | **BLOCKED** (semgrep.dev denied) |
| PostgreSQL 17 | GitHub CI run 43027238277 on this commit | success (not re-run locally) |

## 2. Matrix

| Test ID | Area | Threat scenario | Preconditions / synthetic data | Expected secure behaviour | Observed | Result | Sev. if failed | Files | Regression reference |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AZ-01 | IDOR | A edits or deletes B's semester, course or assignment via website | A, B seeded | 404 for foreign; same detail as missing | 404/404; identical detail | PASS | P0 | `student_web/views.py:123,161` | `web_tests/test_security.py::test_cross_account_edit_and_delete_have_same_not_found_message` |
| AZ-02 | IDOR | A uses legacy JSON GET/POST/delete on B's records | A, B seeded | 404; B's grade unchanged | 404/404/404; B grade A | PASS | P0 | `accounts/views.py:185,203` | P05 (`docs/security/s0_probes`) |
| AZ-03 | IDOR | A links a course to B's semester or an assignment to B's course | seeded | 400; nothing stored | 400 | PASS | P0 | `services.py:_validate_changes` | `test_parent_choices_and_filters_cannot_select_another_owner` |
| AZ-04 | IDOR | A filters list or dashboard by B's semester UUID | seeded | 400 | 400 | PASS | P0 | `forms.py:SemesterFilter` | same as AZ-03 |
| AZ-05 | Mass assignment | POST `owner_id`, `id`, `record_version`, `updated_at` | seeded | 400 | 400 | PASS | P1 | `forms.py:StrictForm` | `test_client_owner_ids_and_server_fields_are_rejected` |
| AZ-06 | Pages | Unauthenticated access to every student page and POST | none | Redirect to login | 302 | PASS | P1 | `accounts/views.py:student_required` | `test_all_student_pages_reject_unauthenticated_sessions` |
| CS-01 | CSRF | Cross-site POST to CRUD, status, predictor, planner | session cookie only | 403 | 403; version unchanged | PASS | P2 | settings `MIDDLEWARE` | `test_post_csrf_protection_covers_crud_status_and_planning` |
| XS-01 | XSS | Stored `<script>`/`<img onerror>` in label, name, title | A records with marker | Escaped on all pages | 0 raw occurrences on 7 pages + predictor POST | PASS | P2 | templates | P07 |
| XS-02 | XSS | Reflected extra query parameter | — | Rejected or escaped | 400, not reflected | PASS | P2 | `StrictForm` | P07 |
| RD-01 | Redirect | `?next=https://evil.example/` at login | valid creds | Ignore `next` | Location `/` | PASS | P2 | `accounts/views.py:50` | P08 |
| HH-01 | Host header | `Host: evil.example` | — | 400 | 400 | PASS | P2 | `ALLOWED_HOSTS` | P08 |
| HD-01 | Headers | Clickjacking, sniffing, referrer, cache | — | DENY, nosniff, same-origin, no-store | All present | PASS | P3 | settings | P06 |
| HD-02 | Headers | CSP present | — | Strict CSP | **absent** | FAIL | P3 | settings | S0-07 (to write) |
| HD-03 | Transport | HSTS / SSL redirect in secure profile | `web_secure` | Configured | W004, W008 | FAIL | P3 | `web_secure.py` | S0-07 (to write) |
| SE-01 | Session | Cookie flags | logged in (test profile) | HttpOnly, SameSite=Lax (+Secure in secure profiles) | HttpOnly, Lax; Secure off in test profile by design | PASS | P2 | `auth_common.py:38-41` | P06; existing auth tests |
| SE-02 | Session | Old sessions after password change or reset; fixation | — | Invalidated; key rotated | Existing tests pass | PASS | P1 | `principals.py` | `auth_tests/test_accounts.py` |
| BF-01 | Brute force | 10 failures then legit user from same IP (proxy or NAT) | `REMOTE_ADDR=192.0.2.10` | Legit user unaffected | **429** for bravo | FAIL | P2 | `throttling.py:14` | S0-01 (to write) |
| BF-02 | Brute force | 40 guesses on one account from 40 IPs | distinct `REMOTE_ADDR` | Throttled per account | All 200; correct pw then 302 | FAIL | P2 | `views.py:41`, `backends.py:8` | S0-02 (to write) |
| EN-01 | Enumeration | Register a taken username with own email | `alpha` exists | No observable difference | 0 vs 1 emails (bodies identical) | FAIL | P3 | `tokens.py:44-53` | S0-04 |
| EN-02 | Enumeration | Timing of reset/resend for known vs unknown email | real SMTP | Constant time | Not measurable (no SMTP) | N/T | P3 | `tokens.py:41,56` | S0-05 |
| AB-01 | Abuse | 60 rapid record creations | A logged in | Quota or throttle | 60/60 stored, all 302 | FAIL | P2 | `services.py:97` | S0-03 (to write) |
| AB-02 | Abuse | Oversized body, too many fields | 70 KB; 700 fields | 400 | 400, 400 | PASS | P3 | `web_common.py:16-17` | C03 |
| AB-03 | Cost | Queries per request | seeded | Bounded and modest | anon 3; dashboard 48; course list 47 | FAIL (hardening) | P3 | `middleware.py:17`, `ownership.py:70,141` | S0-11 (budget test to write) |
| IN-01 | Integrity | Legacy POST omitting `actual_grade` | own course grade B | 400, grade kept | 200, grade cleared | FAIL | P3 | `accounts/views.py:193` | S0-06 (to write) |
| DB-01 | RLS | RLS enabled + forced; policies | migrated | 3 tables, 1 policy each, USING + WITH CHECK | as expected | PASS | P0 | `0004_student_rls.py` | P09; `security_tests/test_rls.py` |
| DB-02 | Context | Unsigned `set_config('ucc.student_id')` as runtime | seeded | 0 rows | 0 | PASS | P1 | verifier | P09; existing replay tests |
| DB-03 | Roles | Runtime reads accounts, sessions, key, `ucc_crypto` | runtime login | Denied | InsufficientPrivilege ×4 | PASS | P0 | `configure_runtime.py` | P09 |
| DB-04 | Roles | Runtime updates `owner_id`; DDL; TEMP; `SET ROLE` migrator | runtime login | Denied | Denied ×4 | PASS | P1 | same | P09 |
| DB-05 | Roles | Auth reads academic tables; updates `is_active`/`email`; executes verifier | auth login | Denied | Denied ×4 | PASS | P0 | `configure_auth_role.py` | P09 |
| DB-06 | Roles | Auth INSERT of `is_active`/`email_verified_at` | auth login | Not insertable or constrained | Allowed | FAIL (hardening) | P3 | `configure_auth_role.py:45` | S0-09 |
| DB-07 | Roles | Runtime large objects; CONNECT/TEMP on `postgres` DB | runtime login | Denied | Allowed / (True, True) | FAIL (hardening) | P3 | cluster defaults | S0-10 |
| DB-08 | Roles | SECURITY DEFINER hygiene | — | `search_path` pinned; no PUBLIC EXECUTE | pinned; ACL migrator + runtime | PASS | P1 | `0004` | P09 |
| DB-09 | Roles | Web traffic on migration connection | seeded | 0 queries | 0 | PASS | P1 | settings | C01/C02; existing test |
| SC-01 | Secrets | Credentials in tree or history | 46 commits | None | None (1 FP) | PASS | P0 | — | `git grep` patterns below |
| SC-02 | Supply chain | Known CVEs in locks | — | None | None | PASS | P2 | locks | CI `dependency-audit` |
| SC-03 | Supply chain | Branch protection | GitHub | Required checks | `protected: false` | FAIL (process) | P3 | repo settings | S0-15 |

## 3. Reproducing the S0 probes

The probe sources are in `docs/security/s0_probes/`. They are deliberately
outside the discovered suites and use the existing `web_tests.base.WebsiteCase`
harness. On a **disposable** cluster prepared as described in
`docs/DATABASE_SECURITY.md` (test roles from `tools/prepare_security_test_roles.py`):

```bash
export PGUSER="$UCC_MIGRATION_ROLE" PGPASSWORD="$UCC_MIGRATION_PASSWORD" PGDATABASE="$UCC_SECURITY_SCRATCH_DATABASE" PGTESTDATABASE=test_ucc_s0 PYTHONPATH=docs/security
```

```bash
python server/manage.py test s0_probes --settings=config.settings.web_test -v 1
```

Each probe prints `PROBE <id> ...` lines. They are observations, not
assertions, so a FAIL row above does not make the probe run fail. `test_probes.py`
hard-codes the CI test migrator role name `ucc_migrator_ci` for the `SET ROLE`
probe. Change it if your role names differ.

Secret patterns searched across `git rev-list --all` (file names only, values
never printed): private-key headers, `SECRET_KEY = '<literal>'`,
`postgres://user:pass@`, `PGPASSWORD=<literal>`, `*_KEY=`/`PASSWORD=` long
literals, AWS `AKIA`, GitHub `gh?_`, Slack `xox?-`, `sk-` keys.

## 4. Planned for later stages (not executed)

| ID | Stage | Description |
| --- | --- | --- |
| S3-BR-01 | S3 | Playwright: render every page with a CSP in report-only mode and collect violations |
| S3-CO-01 | S3 | Real cross-origin form POST from a second origin in a browser |
| S3-CC-01 | S3 | Concurrent creates against a per-owner cap (after S0-03 fix) |
| S3-PX-01 | S3 | nginx reverse proxy in front of the app: CSRF Origin checks, `is_secure`, throttle IP derivation |
| S3-PG-01 | S3 | Re-run all suites on PostgreSQL 17 in an environment that allows it |
| S3-LD-01 | S3 | Bounded load test (for example 20 concurrent sessions, 2 minutes) to find connection-exhaustion thresholds with `CONN_MAX_AGE=0` |
