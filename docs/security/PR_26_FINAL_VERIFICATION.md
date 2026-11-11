# PR #26 final independent verification

**Verdict: APPROVE WITH CONDITIONS for dormant S0-02A foundation only.** The previously reproduced case-binding, PG17 privilege-drift, NULL rotation constraint, wrong-account replay deletion and stale forget-all issuance findings are addressed at the reviewed head. No confirmed new student-facing bypass was reproduced. This is not approval of active account/device throttling, recovery enforcement or deployment.

Reviewed head: **`e2624428e52aa867e6c33721438f33da91546454`** ([PR #26](https://github.com/jordandavid1812-creator/university-command-center/pull/26)), 12 November 2026 (Africa/Lagos). Actual PR base: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`; fetched master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5` includes PR #30. Claude's branch was not modified. This report supersedes only the explicitly retested dispositions in [the earlier PR #27 report](https://github.com/jordandavid1812-creator/university-command-center/blob/docs/s0-02-independent-review/docs/security/PR_26_S0_02A_IMPLEMENTATION_REVIEW.md).

## Conditions and scope

1. Before merge acceptance, integrate current master/PR #30 through the implementation owner's workflow and obtain green CI on the resulting exact head. Current pinned-head CI is red solely on the reproduced pre-existing calendar-dependent website test; the local test-only overlay passes. Recheck changed code after integration; this review does not authorize a merge.
2. Keep device primitives dormant. Do not enable trusted-device IP bypass, counters or hard account restrictions on the strength of 02A tests. Future callers must derive the authenticated Student UUID, read device generation **before password verification**, retain credential-stamp/transaction checks, and handle HTTP/session/cookie failure boundaries in separately reviewed S0-02B/C.
3. Before any accepted staging authentication release, integrate and reverify PR #29 (independently approved at `bec0a44`, still unmerged). PR #26 leaves the baseline hash-upgrade/reset race unchanged. That separate known defect is not fixed merely by adding device generation.

## Retested findings

| Finding / severity before fix | Evidence at e262442 | Disposition |
| --- | --- | --- |
| P26-01 / High latent cross-account lane binding | `devices.py:109–114,147–175,190–203,245–257`: exact stored username for pre-auth classification/issuance; authenticated immutable UUID for rotation; no casefold. Existing exact-case/NFKC tests and independent distinct `alpha`/`ALPHA` accounts return mismatch without changing trust | **Addressed** for primitives. Future form normalization/caller identity must match backend |
| P26-02 / Medium privilege drift | `accounts/boundary.py:7–76,79–109` checks required table privileges, exact effective UPDATE-column set, forbidden privileges/grant options and partial schema. `academics/ownership.py:91` onward uses support/MAINTAIN checks. Independent PG17 grants of MAINTAIN to each real auth/runtime LOGIN are rejected; revoked UPDATE(rotated_at) is rejected; restoring grants passes | **Addressed** for new support-table contract and tested PG17 MAINTAIN scope. Not a claim that every legacy privilege on every unrelated object is exactly allowlisted |
| P26-03 / Medium NULL constraint | `models.py:95–105`, migration `0003` explicit previous_digest IS NOT NULL in rotated branch; previous/null timestamp half-pairs rejected by real INSERT/UPDATE tests/raw SQL; exact 30-day expiry replaces 31-day bound | **Addressed** on fresh/reapplied reviewed schema |
| P26-04 / Medium stale forget-all issuance | `devices.py:140–175,283–291`: generation captured by caller, Student row lock, credential-stamp equality and generation equality; revoke_all creates/increments barrier with F expression under same lock before deletion. Independent unchanged-password stale-generation issue fails; fresh generation issue succeeds; failed revocation transaction restores trust and generation | **Addressed** at service boundary, subject to before-password-check caller contract |
| P26-05 / Medium cross-account replay deletion | `_classify` checks account identity before stale-cookie replay; check() conditional delete and rotate() locked delete follow classification. Independent previous-cookie-after-grace calls to both check(A-cookie, B-name) and rotate(A-cookie, B-UUID) return mismatch and preserve A's current row; same-account replay still revokes | **Addressed** |

Exact reviewed source: [devices.py](https://github.com/jordandavid1812-creator/university-command-center/blob/e2624428e52aa867e6c33721438f33da91546454/server/accounts/devices.py), [role guard](https://github.com/jordandavid1812-creator/university-command-center/blob/e2624428e52aa867e6c33721438f33da91546454/server/accounts/boundary.py), [models](https://github.com/jordandavid1812-creator/university-command-center/blob/e2624428e52aa867e6c33721438f33da91546454/server/accounts/models.py), [tests](https://github.com/jordandavid1812-creator/university-command-center/blob/e2624428e52aa867e6c33721438f33da91546454/server/auth_tests/test_trusted_devices.py).

## Transactions, rotation and remaining trust boundaries

Issuance/forget-all lock Student first; rotation locks its device row only. A revocation that waits for issuance sees/deletes its committed device. Issuance waiting behind forget-all fails the generation equality check, even if the password was not changed. F-expression increment is atomic; ten simultaneous revocations and mixed issue/rotate/revoke tests pass. Rollback restores both deletion and barrier. No service in this PR accepts a client-supplied identity as authentication; these are internal primitives, not public request handlers.

Rotation's locked conditional update gives one winner/new cookie and a concurrent previous-cookie request `grace` with no new cookie. `Check.selects_trusted_limits` is true only for current `trusted`, not grace. Grace avoids false immediate revocation; it does not grant the trusted throttle lane. A copied current cookie remains replayable as device evidence; a stolen previous cookie can revoke the owning device after grace. A lost winning response or out-of-order browser responses can lose trust and fall back to the unfamiliar path. Two-generations-old identifiers are absent, not a retained replay history. These documented availability limitations remain; a cookie never authenticates by itself. No HTTP cookie issuance/rotation, reset-time automatic primitive wiring, throttle admission or recovery-finalization behavior is being approved here.

### Low: generation monotonicity is enforced by trusted service code, not SQL permissions

Affected: `accounts/models.py:113–123`, `configure_auth_role.py:55–74`, `auth_tests/test_trusted_devices.py:719`.

Confirmed independent probe: revoke once (generation 1), then UPDATE generation=0 through the actual auth LOGIN succeeds, and require_auth_role still passes. The role has permitted column-level UPDATE(generation); no database trigger rejects decreases. Denying DELETE/TRUNCATE does not make value rollback impossible. The test named `test_auth_role_cannot_delete_or_reset_the_generation` denies deletion/truncation/identity-column UPDATE, but does not try resetting the generation value.

This is **not a demonstrated student-controlled bypass**. The auth role already has password/session mutation privileges, and arbitrary trusted-code/credential compromise is outside this project's student-isolation boundary. Normal revoke_all uses an atomic increment and issue checks it correctly. Recommendation: qualify “rows are never ... reset” in the model documentation and rename/extend the test to state its actual boundary. Add a database monotonicity mechanism only if the threat model explicitly requires protection from otherwise-authorized auth SQL; do not imply the current grants already provide it.

### Operational migration caveat: rewritten unmerged 0003 is not an upgrade for an already-applied old 0003

The generation table, rotation CHECK and expiry bound were revised inside the unmerged `0003_trusted_device_foundation`. Fresh databases and reverse/reapply tests pass, but an existing database that recorded an older 0003 as applied will not receive new SQL merely by fetching this commit; makemigrations --check checks model state, not that physical history. Support-table partial-schema checks provide a denial boundary, not an automatic upgrade.

Before using any persistent shared/staging database, inventory its applied migration revision. If an older 0003 is already applied there, require a reviewed forward migration/provisioning plan; do not fake migrations or destroy data. Recreating a disposable synthetic local test database is different from upgrading persistent data. This is a deployment dependency, not evidence that the reviewed fresh-schema constraint remains vulnerable.

## Independent execution and CI

Python 3.12.14, Django 5.2.19, PostgreSQL **17.11 (Debian 17.11-1.pgdg13+2)**, actual separate non-superuser migrator/runtime/auth LOGINs, disposable loopback-only cluster, synthetic accounts. No SQLite and no superuser web requests. Legacy/foundation/security/auth/web runs used separate disposable test databases. Foundation migration tests used the documented isolated privileged setup; app request suites used restricted roles.

| Pristine pinned-head suite | Result |
| --- | --- |
| Legacy with Streamlit | 113 passed |
| Foundation | 33 passed |
| Restricted-role security / forced RLS | 46 passed |
| Authentication / dormant-device foundation | 140 passed, no skipped PG17 MAINTAIN case |
| Website | 68 passed, 1 known date-dependent failure |
| Additional independent probes | 8 passed |

Supplied total: **400 passed / 1 failed of 401**, plus **8 independent passes**. The website failure is the same `test_existing_workspace_does_not_repeat_first_time_onboarding` assumption independently reproduced on base master during PR #29's review, now fixed in merged PR #30. A separate detached checkout of e262442 with **only** master/PR #30's test-file change applied passed **69/69 website tests**. This yields 401 supplied passes with that explicit test overlay; it is not a claim that pristine e262442 CI is green.

Schema drift check: `makemigrations --check --dry-run` → No changes detected. Both hashed lockfiles: `pip-audit --strict --require-hashes --disable-pip` → No known vulnerabilities found. These do not certify production settings or provider compatibility.

[Exact-head CI run 43119679366](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43119679366): **failure**. Legacy and dependency-audit jobs pass. Database job 130856644076 logs confirm foundation 33, security 46 and auth 140 **OK**, website 69 with the single date failure. CI workflow service is PostgreSQL 17; local execution independently used 17.11. Re-run CI on the integrated head before accepting a merge.

Independent probe source/reproduction: [PR_26_FINAL_PROBES.md](PR_26_FINAL_PROBES.md). Eight probes cover exact-case target/UUID rotation; wrong-account previous-cookie preservation for check + rotate; both NULL half-pairs; actual PG17 MAINTAIN for both roles; missing rotated_at UPDATE; stale generation after unchanged-password revocation; rollback; and the documented direct-SQL generation limitation. Supplied tests additionally exercise per-column grants/grant options, concurrent generation/rotation/cap behavior, migration reversal/reapply, expiry and dormant live-code boundaries.

## All 12 original design findings: what this closes

| Design finding | Current disposition |
| --- | --- |
| F01 failed authentication spending successful-login quotas | **Unverified S0-02B**: dormant LoginLimit schema is not implemented admission/release logic |
| F02 account identity | Primitive exact-case/UUID defect addressed; retain integrated form/caller tests |
| F03 shared-campus ceilings | **Policy/load/integration pending**; schema kind ip_ceiling alone does not prove separate trusted/unfamiliar ceilings |
| F04 stale trust issuance/revocation | Generation + password-stamp primitives addressed; future capture timing/reset wiring/finalization need tests. F04b baseline race remains separate unmerged PR #29 |
| F05 concurrent rotation | Primitive lock/CAS/no-cookie grace verified; browser response loss/reordering and lane reservation require B integration evidence |
| F06 database failure outcome | No new live login behavior in 02A; stage-by-stage B failure/commit/session-save tests remain required |
| F07 independent recovery | **Deferred**, real email/accessibility/quota/outage proof required before hard account enforcement |
| F08 account ownership/LRU | Per-student cap/deletion and binding tests pass; eventual HTTP revoke endpoints must authorize ownership, not trust device IDs |
| F09 keys/schema/restore | NULL/30-day constraints addressed; purpose signing with main key/fallback remains deliberate choice, not independent device key. Restore invalidation/key retirement still operational work |
| F10 bounded security logging | **Deferred** to B/operations; no production-retention/sentinel proof from schema |
| F11 enumeration | No new public cookie/throttle handler is enabled; response/timing distributions and failure similarity must be tested in B/C |
| F12 alternative design continuation | Comparison/design observation, not an 02A implementation defect; no blanket approval of either entire proposal |

Before S0-02B: retain direct PG17 drift/NULL/replay/generation regressions, test generation captured before password check under real concurrency, ensure wrong-account cookies never mutate another student's evidence, and add failure/crash/response-order tests for session + device + quota transactions. Before hard restrictions: independent accessible recovery under saturated campus/account limits and real email outages. Before staging acceptance: provider qualification, exact-role restore, key/auth artifact invalidation, private HTTPS and privacy/monitoring evidence.

No authentication implementation, merge, purchase or deployment was performed. The new staging plans organize the remaining work; they do not close these deferred security dependencies.
