# PR #26 — dormant foundation / merged-PR29 integration rehearsal

Executed **12 November 2026 (Africa/Lagos)**. **Positive integration evidence; no new runtime correction required.** This is a **noncanonical evidence candidate**, not a replacement for canonical PR #26 or permission to merge/activate anything. Stop for independent Claude exact-head review and separate owner authorization.

## Exact source and environment manifest

| Item | Exact value |
| --- | --- |
| Fetched master | `5bd3c42f2748da8b6b082b853b005e63cc869b78`, containing canonical PR29 merge |
| Canonical PR26 head | `44c515f903cc35f1dfdd3d1c2b777a8d1a873222` |
| Original PR26 merge-base | `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5` |
| Isolated application candidate | `4593af40635833d9a7574333cbf7d656c9469136` |
| Candidate tree | `9c87c17b43b82824c612efa29e509133e29cbfaa` |
| Approved patch applied onto master | `git diff --binary 8295fbd 44c515f`, then `git apply --3way --index` in a fresh worktree |
| Candidate delta SHA256 | `git diff --binary 5bd3c42 4593af4` → `71729e1b192900e74453ff12c7bbb7c28f60383c006396c8bdf2c62b0a8462aa` |
| Prior independent device evidence | PR33 at `e2d6f811ffa64b6d6b4d7addc6febe566c233956`; reviews pinned e262442, carried forward to44c515f in PR35 at `e3da0bfa268b26e420f004d9eaabd06f69ccadc4` |
| Merged password fix | PR29 historical head `42910ed09ed1a20aee556e77666cf6e347c724cd`; candidate backends/views/password-race tests remain byte-identical to master5bd3c42 |
| Rehearsal branch | `test/pr26-current-master-rehearsal`; final head and hosted CI recorded in the draft PR |
| Local versions | Python3.12.14, Django5.2.19, psycopg3.3.8, Playwright1.65.0; existing hashed locks, no new dependency |
| PostgreSQL | **17.11 (Debian 17.11-1.pgdg13+2)**; no SQLite or PG16 substitution |
| Browser | Managed Chromium **158.0.8127.18**; all three browser suites |
| Local cluster | Disposable `ucc-pr26-rehearsal-postgres`, published only on `127.0.0.1:55450` |
| Image identity | ID `sha256:eb0fb2377534e65aad04f37838956b3dfb888e1a3dd3c1acf957bc6557eb6c7d`; digest `postgres@sha256:ff87138949ad9a46f32ff23bd6852b52ce024a13dffe9b4087be98292cdd3b4f` |

Git remote refs independently confirmed master5bd3c42 and PR26 head44c515f, including `refs/pull/26/head`. The GitHub `github_fetch` PR-details endpoint repeatedly returned internal errors; the dedicated `github_fetch_pr` succeeded for #26, confirming open/draft/unmerged and the exact head. Do not infer current readiness from its old PR body: that prose still describes an earlier schema/test count/CI state. Source, runtime evidence and final exact-head CI take precedence.

The patch's11 original paths applied without conflict. Its resulting tree equals `git merge-tree --write-tree 5bd3c42 44c515f`; no existing branch was merged, rebased or changed. All original PR26 implementation files retain canonical bytes. `docs/AUTHENTICATION.md` composes the new dormant note with the already-merged PR29 explanation. Neither PR29's behavior nor the premium UI was overwritten. The evidence commit adds this report,3 test-only modules and one extra CI step; it does not implement any correction in live code.

Reviewed context includes the actual merged PR29 backend/finalization implementation, PR33 findings/probes, PR35 carry-forward/migration/generation caveats, the candidate's S1/S0-02 reconciliation and merged B1 Revision5 plan §6.11–6.14. B1 remains design only and separately authorized; no B1 settings/classifier/logging behavior is added here.

## Database and migration evidence

Separate actual LOGINs `ucc_migrator`, `ucc_auth`, `ucc_runtime`: all NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE; only the disposable test migrator has CREATEDB. DBA bootstrap is offline and never serves application requests. Credentials/signing keys are random, private ignored0600 files, not printed or committed. Foundation tests use their separate disposable setup; auth/web/security runners migrate fixtures and use restricted real auth/runtime connections. No SET ROLE-from-superuser substitute, real student data or personal JSON.

1. Initialized the **master schema** with offline `auth_migration` in a baseline worktree whose migration/settings/provisioning inputs match master5bd3c42. No device schema was applied there initially. The baseline worktree contains only documentation changes on the older branch; schema/setup files are byte-identical to the stated master.
2. Candidate `migrate --plan` reported exactly `accounts.0003_trusted_device_foundation`, with CreateModel operations for **DeviceGeneration, LoginLimit and TrustedDevice**, depending on accounts0002.
3. Applied0003 and reran unchanged `configure_runtime` / canonical `configure_auth_role`; Django check passed and `makemigrations --check --dry-run` reported **No changes detected**.
4. Full auth suite executes `test_migration_reverses_and_reapplies_with_fail_closed_grants`: reverse to0002 removes all3 support tables, older-schema provisioning/login works, reapply0003 without provisioning must reject auth and return503, then provisioning restores expected operation. Academic forced RLS remains enabled/forced on all3 academic tables. Historical schema-reversal tests also pass.
5. Mutation of the support grant guard makes the unprovisioned reapply assertion fail, proving that the migration acceptance test detects missing gate behavior rather than merely checking table names. Partial support schema is separately rejected by supplied tests.

Reversal intentionally drops support rows. This is **synthetic disposable reversibility**, not a lossless production rollback or arbitrary persistent-db upgrade guarantee. An older already-recorded0003 does not receive rewritten SQL on fetch: inventory exact migration history before any persistent rollout and require a reviewed forward migration if needed. Never fake migrations or delete persistent data to reproduce this result. The migrate→provision window intentionally fails closed with503; coordinate offline maintenance, not an availability claim.

### Least privilege and RLS

Executed actual grant/column/grant-option/partial-schema checks, missing-grant HTTP503, excessive-grant rejection and raw runtime denial. Auth receives the exact column-limited support-table contract; runtime has no support-table access, no schema ownership or bypass authority. Academic direct-SQL missing/foreign-owner context and cross-owner relationships remain covered by the46 restricted-role tests and auth/web ownership tests.

`test_postgresql17_maintain_is_rejected_for_auth_and_runtime` executed **OK, not skipped** on PG17.11. Independent probes also grant forbidden MAINTAIN and revoke required UPDATE(rotated_at), check rejection and restore grants. This is tested scope, not a claim of exhaustive allowlisting for every legacy database object.

## Executed results and count reconciliation

| Suite | Actual result |
| --- | --- |
| Legacy academic/CLI/Streamlit | **113 passed** |
| Foundation/model/constraints/migrations | **33 passed** |
| Restricted-role isolation/RLS | **46 passed** |
| Authentication, password races and dormant foundation | **149 passed** = existing85 + canonical64 device tests |
| Website, academic/read/query-budget regressions | **91 passed** |
| **Main regression total** | **432 passed** = current-master368 +64; the earlier359 baseline and PR29's9 remain intact |
| Preserved independent PR33 device probes | **8 passed** |
| Preserved independent PR32/PR48 password/session probes | **9 passed** within the combined evidence command |
| New integration/dormancy check plus3 mutation controls | **4 passed** |
| Combined evidence command | **21 passed** (8+9+4); these rerun the same methods, not21 extra tests to double-count |
| UI1 browser | **10 passed** |
| Premium-auth browser | **5 passed** |
| UI2 browser | **12 passed**, including enlarged-layout/blocked-key/non-overflow checks |
| **Browser total** | **27 passed**, unchanged |
| Dependency check/audit | `pip check`: no broken requirements; strict hashed audit of all3 locks: **no known vulnerabilities** |

No skips were reported. Test fixtures and browser content are synthetic. Static browsers verify presentation/no-JS/keyboard behavior; actual ownership/roles/session behavior is separately verified on PG17. No new screenshots or real AT/mobile/actual-zoom certification are claimed for an unchanged UI.

The preserved8-probe source comes directly from PR33's `PR_26_FINAL_PROBES.md`; the9-probe source is byte-identical to `tools/pr29_rehearsal_probes.py` in independently approved PR48 (`f2a350b84c3c337586c1d1d8b976d8517df9c6b4`). They run as explicit test-only modules, not application imports. PR29 CAS reset/change races, real lock waits, simultaneous usable sessions and stale post-reset session payload rejection pass with PR26 installed. No successful-path session or authentication policy change is introduced by this rehearsal.

## Dormancy and negative controls

**No active HTTP device-cookie issuer or new login restriction.** Canonical views/backends remain master-identical. Supplied compatibility tests prove no device cookie/rows/limits are created by login; source isolation permits primitive imports only in offline artifact cleanup, not live views/middleware. Primitives can return a signed cookie string to an explicitly authorized internal caller; that is not HTTP delivery or authentication.

The additional live integration test populates all5 LoginLimit kinds at maximum positive-int attempts and supplies a valid pre-created device cookie. That cookie alone does not authenticate. Wrong credentials still give the normal generic form, and valid credentials still log in. Device primitives are patched to raise if any live login invokes them; none does. There is no response device cookie, the one pre-created device is unchanged and the saturated limits remain unchanged. Existing source-IP limits and CSRF remain covered by the original suites; the test does not disable or rewrite them.

Three runtime-only mutations in `tools/pr26_integration_controls.py` must be rejected by existing assertions, without editing application files:

| Mutation | Required rejection |
| --- | --- |
| Replace support-grant violation SQL with false | All **5** missing-auth-grant subcases must fail the expected `ImproperlyConfigured` assertion; zero infrastructure errors |
| Same bypass during reverse/reapply test | Unprovisioned0003 reapply must fail its expected guard assertion; restoring guards/provisioning returns normal behavior |
| Add test-only synthetic device Set-Cookie to a login redirect | Existing dormant-cookie assertion must fail; no production issuer or persistent cookie wiring is added |

The first harness version expected1 failure from the missing-grant method, but it deliberately contains5 subtests. It rejected all5 correctly; the harness expectation was corrected to require **exactly5**, each with the expected assertion message and no errors. Other mutants require exactly1 assertion failure. This is test-harness accounting, not a product defect or weakened regression. The corrected4-test module and combined21-test run passed. All patches and connections are restored by fixture cleanup.

## Findings and residual limitations

No new confirmed runtime integration defect was found. Important limitations remain explicit:

- **Generation trust boundary:** `revoke_all` increments atomically under the Student lock and stale-generation issue is refused, but permitted auth SQL can lower the generation value. The independent probe reproduces that pre-existing trusted-auth-role limitation. It is not a demonstrated student-controlled bypass or a SQL monotonicity guarantee.
- **Dormant reset/revocation wiring:** existing devices can remain `trusted` at primitive level after password reset/change because automatic flow revocation is deliberately not wired in02A. The cookie does not authenticate and no lane uses it. Future02B/C must read generation before verification and separately review reset/compromise/issuance/recovery/cookie/response handling before activation.
- **Replay/rotation availability:** copied current evidence is replayable; prior-cookie replay after grace can revoke trust, lost/out-of-order responses may lose trust, and grace never selects trusted limits. No production recovery or browser-cookie lifecycle is accepted here.
- **Migration/operations:** rewritten historical0003, provisioning outage window, backup restoration/key custody and persistent rollout remain external acceptance work; no provider/TLS/restore/public availability evidence is supplied by this local test.
- **Documentation drift:** canonical PR26's old PR body and some operator prose describe earlier table/count/CI states. In particular the AUTHENTICATION note names2 support tables while0003 actually creates3, including DeviceGeneration. Provisioning/tests handle all3. This report records the actual schema; recommend reconciling canonical operator documentation through the owner's reviewed workflow rather than treating old prose as an exact manifest. The canonical patch also contains one inherited whitespace-only documentation line; no implementation was silently reformatted.
- **B1 and launch:** safe failure classification/log privacy/request/COMMIT/response uncertainties remain separate B1/Stage C work. No counters/enforcement/recovery restriction, B1 implementation, service purchase, deployment or production data is included.

## Reproduction and publication

Use [AUTHENTICATION.md](../AUTHENTICATION.md), [DATABASE_SECURITY.md](../DATABASE_SECURITY.md) and the current restricted-role CI setup with **separate disposable databases/provisioning environments**. Never point the test runner at student/application data or serve requests with a DBA/migrator. Record exact source/image versions and keep all temporary secrets outside Git.

```sh
python -m unittest discover -v
python server/manage.py test accounts academics --settings=config.settings.test -v 2
python server/manage.py test security_tests --settings=config.settings.security_test -v 2
python server/manage.py test auth_tests --settings=config.settings.auth_test -v 2
python server/manage.py test web_tests --settings=config.settings.web_test -v 2
PYTHONPATH=tools python server/manage.py test pr26_rehearsal_probes pr29_rehearsal_probes pr26_integration_controls --settings=config.settings.auth_test -v 2
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py -v
python -m pip check
python -m pip_audit --cache-dir "$PWD/work/audit-cache" --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt -r requirements-browser-test-lock.txt
python tools/check_repository_safety.py
```

The three browser commands, read-only workflow permissions and existing regression commands are unchanged; hosted CI adds only one separately named auth-runner database for the21 evidence methods. Final exact-head hosted results belong in the draft PR; do not substitute unrelated master/docs CI. Metadata-read connector errors are not a PostgreSQL/app failure. If publication/CI tools remain unavailable, report that limitation instead of inventing hosted results.

**Handoff:** independent Claude review of the exact candidate/evidence head, canonical-byte identity, migration/role/dormancy controls and current hosted results. Then the owner separately decides canonical PR26 integration; **do not merge the noncanonical evidence PR as a substitute**. No activation, B1, merge, unrelated-branch change or deployment is authorized or performed.
