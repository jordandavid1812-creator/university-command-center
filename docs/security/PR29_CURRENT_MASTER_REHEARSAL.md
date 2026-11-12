# PR #29 — current-master integration rehearsal

Executed **12 November 2026 (Africa/Lagos)**. **No confirmed implementation correction required.** This is test evidence for the approved F04b fix, not a new authentication-policy/B1 implementation or permission to merge. Canonical PR #29 and PR #26 remain untouched and unmerged. The rehearsal draft is an evidence candidate, **not a replacement PR to merge instead of #29**.

## Exact sources and integration method

| Source | Exact identifier |
| --- | --- |
| Fetched master / candidate parent | `4e78b52d5a94856e31bfd15ef41d52a0f7f6c078` |
| Canonical PR #29 head | `42910ed09ed1a20aee556e77666cf6e347c724cd` (open draft, unmerged) |
| PR #29 merge-base | `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5` |
| Rehearsal protocol | PR #47, `3c93bb0804bb3259dc3b2c1684405b1bfd9c240d`, `docs/roadmap/OPEN_PR_RESOLUTION_REPORT.md` |
| Isolated application candidate | `b57adffeb11bc6a7da7cfd970d9ef6e19062530d` |
| Candidate tree | `5373eb3f2867aeb9925433527fd967e79f096451` |
| Independent nine-probe source | PR #32 publication `3949c8c3a29c8c9cba231f38de5f9324272c1d61`, `docs/security/PR_29_INDEPENDENT_PROBES.md`; Python block preserved as `tools/pr29_rehearsal_probes.py` |
| Branch | `test/pr29-current-master-rehearsal`; final head/hosted run recorded in its draft PR |

Created a fresh worktree/branch from fetched master, exported `git diff --binary 8295fbd 42910ed`, and applied it using `git apply --3way --index`. Four paths applied cleanly: `docs/AUTHENTICATION.md`, `server/accounts/backends.py`, `server/accounts/views.py`, `server/auth_tests/test_password_upgrade_race.py`. Committed that candidate without merging/rebasing any existing branch. Its tree exactly matches the non-mutating `git merge-tree --write-tree 4e78b52 42910ed` result.

`git diff --binary 4e78b52 b57adff | sha256sum` = `ea5237b8610203f38c48a28649fc6a93ad0e9366a9d77fb9018b2d928e214abd`. The candidate backend, views and nine regression tests are byte-identical to the canonical PR head. Backend blob in PR/candidate: `dd66960d19d436dfbc1f7ff43dd8aff2910a8d6d`; master backend blob: `d4cf174fa78948777ca1e93584a64364880b5aa6`.

The final evidence commit adds only this report, the preserved independent probe module, mutation-control module and one CI step. Production fix files remain exactly the approved PR29 implementation. Existing workflows/three browser commands, tests, academic calculations, templates, RLS, role grants and migrations are preserved. Hosted CI runs on this candidate, not an unrelated docs-only master tree.

## Environment and database separation

- Local Python **3.12.14**, Django **5.2.19**, psycopg **3.3.8**, Streamlit **1.67.0**, Playwright **1.65.0**; existing hashed locks/venv, no dependency changes.
- Disposable PostgreSQL **17.11 (Debian 17.11-1.pgdg13+2)**, local-only container `ucc-pr29-rehearsal-postgres`, published at `127.0.0.1:55449`; no SQLite, PG16, personal JSON or real student data.
- Image ID `sha256:eb0fb2377534e65aad04f37838956b3dfb888e1a3dd3c1acf957bc6557eb6c7d`; repository digest `postgres@sha256:ff87138949ad9a46f32ff23bd6852b52ce024a13dffe9b4087be98292cdd3b4f`.
- Actual distinct LOGINs: `ucc_migrator`, `ucc_auth`, `ucc_runtime`. All are NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE. The migrator has CREATEDB solely for disposable test databases; auth/runtime have NOCREATEDB. Offline DBA bootstrap is separate; web requests do not use it.
- Existing `SecurityTestRunner`/`AuthenticationTestRunner` migrate test databases and configure unchanged runtime/auth grants. Auth/web tests use real separate auth/runtime connections and signed context/forced RLS, not SET ROLE from a privileged web connection. Offline `default` is for fixtures/migrations only; migration-free request assertions remain in the test suites.
- Ephemeral random passwords/keys reside in ignored permission0600 env files. No values are printed or committed. Each suite gets a distinct test database. Browser fixtures are synthetic static real-template checks, not proof of live backend isolation.
- Managed Chromium **158.0.8127.18**, matching prior hosted-browser revision; actual hosted version is printed in job logs. No new screenshots are claimed because presentation is unchanged. Existing UI2 screenshot provenance remains Chromium156, not relabelled as158.

## Executed positive results

| Suite | Executed count / result |
| --- | --- |
| Legacy CLI/Streamlit/academic unit and interaction tests | **113 passed** |
| Foundation accounts/academics models, constraints and migration tests | **33 passed** |
| Restricted-role security / forced-RLS isolation | **46 passed** |
| Authentication, session, CSRF, ownership, token and rate-limit regression suite | **85 passed**: baseline76 + PR29's9 race regressions |
| Website/academic/query-budget/UI2 integration | **91 passed** |
| **Integrated regression total** | **368 passed** = unchanged359 baseline +9 authorized PR29 tests |
| Independent PR32 lock/CAS/session/failure probes | **9 passed** separately; all nine source methods retained |
| Race mutation controls | **2 passed**: each requires its inner known-bad regression assertion to fail, with zero infrastructure errors |
| UI1 browser | **10 passed** |
| Premium-auth browser | **5 passed** |
| UI2 browser, including both mutations and non-overflow | **12 passed** |
| **Browser total** | **27 passed**, unchanged baseline |
| Combined independent+negative command used by new CI step | **11 passed**; rerun of the same9+2, not11 additional unique tests |

No skips were reported by these runs. The two expected inner mutation failures are not failures of the integrated product or extra baseline tests. Do not count re-executions twice. All published counts refer to actual runner results, not the earlier estimated368.

### What the race evidence proves

The approved nine regressions interleave real reset/change endpoints before and after verification, test current-hash stale verification (no upgrade), five simultaneous same-secret logins, six logins racing reset, normal hash upgrade, wrong-password non-write and zero migrator reads during a request.

Independent probes additionally:

1. Hold a real Student row lock, observe the waiting auth backend using `pg_blocking_pids`, commit a reset, and confirm the CAS rechecks its exact old-hash predicate and returns false. Only the new secret verifies afterwards.
2. Observe a login waiting on the finalization Student lock; commit a new password and confirm generic login rejection with no authenticated session.
3. Reset after login's atomic block but before `SessionMiddleware.process_response` saves. An obsolete auth payload really can be persisted afterwards, but its hash is stale: `session_student` denies it and the next authenticated request clears it. **A saved row/cookie is not by itself usable authority.** This is not a claim that HTTP/session persistence is atomic with reset.
4. Inject finalizer lock failure and post-login-signal failure; confirm existing500/no-auth outcomes, rollback of session/last_login in the latter case, and no new authority. Existing behavior remains unchanged; B1 safe failure classification is not implemented.
5. Run four simultaneous weak-hash logins and then verify every returned session is usable; test algorithm migration, account disablement after verification, and a real PostgreSQL100ms lock timeout with no session delivery.

These tests verify the scoped race fix and current session binding, not comprehensive production timing/side-channel or infrastructure reliability.

## Negative controls and failures investigated

`tools/pr29_negative_controls.py` applies runtime-only patches inside test cases. No application source is edited, and both controls restore their patches automatically:

- Replace CAS upgrade with a stale `set_password`/`save(password)` helper: `test_reset_committed_before_verification_is_not_overwritten` must fail **“new password must remain valid”**. This demonstrates detection of the original reset-overwrite defect.
- Force the finalization hash comparison true (remove credential revalidation): `test_stale_verification_without_upgrade_creates_no_session` must fail **302 !=200**, demonstrating detection of stale-secret session issuance. This mutant changes no production policy or persistent source.

Both controls require exactly one assertion failure and **no errors**, then report only the test name/outcome. Their positive counterparts pass in the normal85-test authentication suite. Test-class setup/teardown and Django's `__call__` lifecycle are preserved.

| Failure | Attribution / correction | Final result |
| --- | --- | --- |
| Initial pip-audit cache creation at `/home/agent/.cache/pip-audit` failed read-only | Environment default cache, not dependency vulnerability or PR29. Re-ran with `--cache-dir "$PWD/work/audit-cache"`, preserving strict hashes and vulnerability checks | No known vulnerabilities across all three hashed locks |
| First custom mutation harness called `TestCase.run()` directly, bypassing Django fixture/client setup; next inner test saw leftover fixtures and teardown had an open connection | Rehearsal test infrastructure, not PR29/master. Corrected harness to class setup/teardown plus Django `case(result)` and explicit connection close; used a fresh disposable test DB. Did not weaken underlying regression assertions | Both intended mutants rejected for the exact expected assertion; corrected combined11-test run passed |

No confirmed product defect or implementation correction was found. The initial harness failure is retained here rather than described as a security regression or hidden by a retry.

## Migration compatibility and quality checks

Executed master-schema initialization using `config.settings.auth_migration` in a baseline worktree at `3c93bb0804bb3259dc3b2c1684405b1bfd9c240d` whose **entire `server/` tree is identical to master4e78b52** (only the inventory report differs). Then used the candidate on that same disposable scratch DB:

- `migrate --plan`: **No planned migration operations**.
- `migrate --noinput`: **No migrations to apply**.
- `makemigrations --check --dry-run`: **No changes detected**.
- `configure_runtime`, `configure_auth_role`, `showmigrations`, `check`: passed; current accounts0001–0002, academics0001–0004 and Django sessions migrations applied. No accounts0003/trusted-device schema appears.
- Foundation33 tests additionally exercise migration/constraint compatibility. Candidate changes no migration file, model, role command or ownership code.
- `pip check`: no broken requirements; strict three-lock dependency audit passed with the local-cache correction above. Syntax/YAML, scope, repository safety and whitespace checks passed before evidence publication.

This is compatibility from the current known master schema on synthetic PostgreSQL17, not an inventory/upgrade guarantee for arbitrary persistent databases. No live DB, backup, provider, TLS deployment or production migration was touched.

## Reproduction and hosted evidence

Use the separated disposable environments in [AUTHENTICATION.md](../AUTHENTICATION.md) and [DATABASE_SECURITY.md](../DATABASE_SECURITY.md); never run destructive test databases on student/application data. Record image/version/digest and generate private temporary credentials outside Git. Apply the exact canonical patch onto the stated master as above, or check out this evidence branch. Use hashed locks and the existing role preparation commands.

```sh
python -m unittest discover -v
python server/manage.py test accounts academics --settings=config.settings.test -v 2
python server/manage.py test security_tests --settings=config.settings.security_test -v 2
python server/manage.py test auth_tests --settings=config.settings.auth_test -v 2
python server/manage.py test web_tests --settings=config.settings.web_test -v 2
PYTHONPATH=tools python server/manage.py test pr29_rehearsal_probes pr29_negative_controls --settings=config.settings.auth_test -v 2
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py -v
python -m pip check
python -m pip_audit --cache-dir "$PWD/work/audit-cache" --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt -r requirements-browser-test-lock.txt
python tools/check_repository_safety.py
```

Use distinct `PGTESTDATABASE` values for the DB suites and the existing non-superuser migrator/auth/runtime configuration. Local probe runs used `test_pr29_auth`, `test_pr29_web`, `test_pr29_isolation`, `test_pr29_independent`, `test_pr29_negative_fixed` and a combined-evidence database; foundation used its separate DBA bootstrap environment. The hosted workflow retains existing test separation and adds just one dedicated `test_ucc_pr29_independent` step for the preserved9 probes and2 controls under the auth runner. All three existing browser commands and read-only CI permissions remain intact. Final exact-head CI/run is recorded in the draft PR, not predeclared here.

## Independent review and remaining risks

**Engineering conclusion:** current-master integration of the exact approved fix is supported by the executed positive/negative evidence. This does not merge PR29 or replace independent Claude verification. Verify the final evidence head, original-fix byte identity, mutation failure reasons, real lock observations, role separation, schema invariance and hosted results. Canonical PR29 remains the source PR for any separately authorized owner integration.

Remaining risks: response/session persistence is not atomic with credential changes; obsolete persisted payloads must continue failing hash binding. Same-secret hash upgrades remain supported, not a password-reuse/credential-epoch policy. Existing500/lock/error logging and COMMIT/HTTP uncertainty are unchanged B1/Stage C dependencies. No new outage classification, hard throttle, device trust, logging policy or proxy deadline is introduced. No PR26 foundation/activation, B1, staging, email delivery, backup/restore acceptance, public deployment or real-data migration is covered. Browser fixtures do not provide real-device/screen-reader/actual-zoom certification.

Next gate: independent Claude exact-head verification and an owner decision on canonical PR29 integration. Any new fix or source change invalidates an automatic carry-forward of this evidence; re-pin and rerun. No merge, closure, deployment, production data or unrelated security-branch change occurred.
