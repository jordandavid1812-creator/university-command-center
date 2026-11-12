# University Command Center — open PR resolution and private-MVP critical path

Snapshot: **12 November 2026 (Africa/Lagos)**. This is the first authorized **documentation and integration-test preparation** slice, not a security implementation or merge instruction. **NOT LAUNCH READY.**

## Current baseline and method

Current fetched master: **`4e78b52d5a94856e31bfd15ef41d52a0f7f6c078`**. It contains UI2 merge785253ddd796554dfc509361d69f18a7140affb2 and roadmap merge4e78b52d5a94856e31bfd15ef41d52a0f7f6c078. [Master CI43232194518](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43232194518) passed all four jobs; previously inspected logs establish PostgreSQL17.11,359 regression tests and27 browser methods. These are baseline observations, not combined #29/#26 results.

Queried GitHub open PRs (per_page100;15 returned), individual PR details, complete changed-file lists (each below100 files), reviews, issue comments, exact-head workflow runs and every latest-run job. Recorded base means the **base SHA reported by the PR API**, not an assertion that a stale branch is based on today's master. Every PR targets `master`; actual merge-base is listed separately. All heads were fetched locally. Independent approval may exist outside GitHub's formal review API: the source and limits are stated explicitly below.

Static checks on all15 candidates: `git merge-base --is-ancestor`, changed-path blob comparisons and `git merge-tree --write-tree <master> <head>`. **All15 have clean textual merges**; none of their heads is an ancestor of master, and none has every changed path already byte-identical in master. GitHub initially returned unknown mergeability for #27/#32/#33; local tree checks resolve textual-conflict uncertainty only. No branches were merged or rebased. This does **not** establish runtime compatibility.

A sequential #29→#26 conflict rehearsal used an unreferenced commit object made from #29's clean synthetic merge tree, then `merge-tree` with #26. It was also clean; no branch/ref, working implementation or application database was changed, and no request/tests were run on that candidate. Shared documentation overlap is `docs/AUTHENTICATION.md`; manually preserve both security descriptions. #18/#19 overlap `.github/workflows/quality.yml`. Their clean merged trees retain **all three browser-suite commands**, even though directly comparing their old head files to master shows missing newer commands. Never confuse that direct comparison with a merge-result regression.

All15 latest exact-head workflows are green. Only #46/#18/#19 have the current four-job shape; the other12 have **three jobs and no frontend-browser job**. The #18/#19 browser jobs execute only UI1 on their old heads; they are not evidence that all three current suites passed with those action versions. #46 has all three. Old green CI is historical, not current integrated-release evidence. All15 have **zero submitted GitHub reviews** and zero issue comments at inspection; the owner's explicit approval report for #46 and independent reports for security work are separate evidence. Do not equate an empty API review list with proof that an external review never happened.

## Classification and resolution queue

A = ready for owner merge decision; B = needs independent review; C = needs corrections or integration testing; D = superseded/redundant, recommend closure; E = blocked by dependency/owner decision. These classifications authorize no merge, closure, draft promotion or security activation.

| PR | Title | Class | Exact next resolution action |
| --- | --- | --- | --- |
| [#46](https://github.com/jordandavid1812-creator/university-command-center/pull/46) | docs: reconcile roadmap after UI2 and status merges | **A** | Owner reports independent approval; exact approved head unchanged. All four current jobs green. Ready for owner exact-head merge decision; do not alter this branch. |
| [#42](https://github.com/jordandavid1812-creator/university-command-center/pull/42) | docs: publish independent B1 Revision 5 conditional approval | **B** | Latest independent B1 design report conditionally approves revision5, not implementation. No GitHub review of this documentation PR is recorded. Recommended first B1 evidence publication for independent acceptance. |
| [#40](https://github.com/jordandavid1812-creator/university-command-center/pull/40) | docs: publish independent B1 Revision 4 security review | **B** | Historical revision4 REQUEST CHANGES report and probes are unique evidence, not current-plan defects. No GitHub review of this documentation publication is recorded. |
| [#38](https://github.com/jordandavid1812-creator/university-command-center/pull/38) | docs: independent B1 Revision 3 review and PostgreSQL 17 probe evidence | **B** | Historical revision3 REQUEST CHANGES report and probes are unique evidence. No GitHub review of this documentation publication is recorded. |
| [#35](https://github.com/jordandavid1812-creator/university-command-center/pull/35) | docs: Stage A integration readiness and Stage C local staging architecture | **C** | Useful Stage A/C plan, but its master8295fbd, open-PR status and337/410 discovery expectations are historical. Refresh release ledger and test counts; retain architecture rather than duplicate it. |
| [#34](https://github.com/jordandavid1812-creator/university-command-center/pull/34) | docs: Milestone 5A backlog, PG17 provider tests and readiness gates | **C** | Detailed backlog/provider/acceptance plans exist but retain older base/counts and conditional security references. Update integration dependencies before adopting as executable release backlog. |
| [#33](https://github.com/jordandavid1812-creator/university-command-center/pull/33) | docs: final independent verification of PR #26 at e262442 | **B** | Independent #26 report is pinned to e262442 and conditional; later #35 records carry-forward to44c515f. No GitHub documentation review is recorded. |
| [#32](https://github.com/jordandavid1812-creator/university-command-center/pull/32) | docs: independent security audit of PR #29 at bec0a44 | **B** | Independent #29 APPROVE report is pinned to bec0a44; later #35 carries it forward to42910ed. No GitHub documentation review is recorded. |
| [#31](https://github.com/jordandavid1812-creator/university-command-center/pull/31) | Make onboarding polish test independent of the current date | **D** | Clean textual merge, but **unsafe to merge into current master**: the reviewer reproduced an existing UI2 test failure when its frozen zero-overdue response is expected to contain `?status=overdue`. Recommend closing without merging, subject to separate owner authorization. The date issue is only partially hardened; see the dedicated entry. |
| [#29](https://github.com/jordandavid1812-creator/university-command-center/pull/29) | F04b: stop stale password-hash upgrades from undoing resets and changes | **C** | Independent security approval is preserved in #32 and the later #35 reconciliation, but the branch CI predates current master and has only three jobs. No new code defect is confirmed. Refresh integration evidence before treating it as ready. |
| [#28](https://github.com/jordandavid1812-creator/university-command-center/pull/28) | Plan Milestone 5A private staging, costs and readiness gates | **C** | Roadmap/cost research is planning, not qualified infrastructure. Refresh current project dependencies and label price estimates/quote requirements before an owner adoption decision. |
| [#27](https://github.com/jordandavid1812-creator/university-command-center/pull/27) | Document independent S0-02 design and PR 26 implementation reviews | **B** | Original S0-02 design/implementation findings are unique historical evidence, not a statement that current44c515f still has every old defect. No GitHub documentation review is recorded. |
| [#26](https://github.com/jordandavid1812-creator/university-command-center/pull/26) | S0-02A: dormant trusted-device foundation (schema, grants, primitives) | **E** | Dormant-only independent approval and prior corrections are recorded in #33/#35. Remains blocked behind #29 and current combined migration/privilege verification; clean textual merge is insufficient. |
| [#19](https://github.com/jordandavid1812-creator/university-command-center/pull/19) | Bump actions/checkout from 6.1.0 to 7.0.1 | **C** | Pinned checkout major update has four green jobs on its old branch. Current three-way tree preserves all three browser commands; no current-master action runtime/integration proof is claimed. |
| [#18](https://github.com/jordandavid1812-creator/university-command-center/pull/18) | Bump actions/setup-python from 6.3.0 to 7.1.0 | **C** | Pinned setup-python major update has four green jobs on its old branch. Current three-way tree preserves all three browser commands, but current-master runtime/action compatibility and combined workflow evidence remain unexecuted. |

**Ready now: #46 only.** The owner explicitly reports independent approval and its exact head is unchanged. **Next security priority: #29**, requiring current integration evidence, not an unreviewed rewrite. **Closure recommendation: #31 only, without merging, subject to separate owner authorization. Its clean textual merge fails an existing UI2 test in the reviewer's integration experiment; do not merge it as a date fix.** Historical review documents #27/#32/#33/#38/#40 are not duplicates merely because their reviewed implementation has since changed; preserve useful evidence and disposition context.

## Complete exact-head inventory and changed files

Each CI link below is the latest run returned for the specified head, and every listed job was completed/success. All branches are open/unmerged at this snapshot. The inclusion/conflict findings above apply to each row. No PR is marked merged just because its purpose overlaps other work.

### PR #46 — docs: reconcile roadmap after UI2 and status merges

- Class: **A**; draft. Target: `master`.
- Exact head: `8fa83a39e89476a48ecd913dce7e9ea6e8c795bf`.
- API-recorded base: `4e78b52d5a94856e31bfd15ef41d52a0f7f6c078`. Actual merge-base with current master: `4e78b52d5a94856e31bfd15ef41d52a0f7f6c078`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43233498507](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43233498507), exact head match, **success**. Jobs: database-tests=success, frontend-browser=success, dependency-audit=success, tests=success.
- Independent review: owner reports approval of this unchanged exact head; no formal GitHub review object.
- Dependency / acceptance: No prerequisite beyond owner decision; this report does not merge it.
- Complete changed-file list:

  - `docs/roadmap/PROJECT_COMPLETION_STATUS.md`

### PR #42 — docs: publish independent B1 Revision 5 conditional approval

- Class: **B**; open, non-draft. Target: `master`.
- Exact head: `642df7909afc882e5ed61a62f232113c560a5e08`.
- API-recorded base: `0983f6f144cfd39a744b915e89d648740d1187d2`. Actual merge-base with current master: `0983f6f144cfd39a744b915e89d648740d1187d2`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43174278727](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43174278727), exact head match, **success**. Jobs: tests=success, dependency-audit=success, database-tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Preserve R5-T1 real-COMMIT fault placement and R5-T2 unsafe-logging fixture placement as implementation-test conditions; obtain owner B1 decisions separately.
- Complete changed-file list:

  - `docs/security/B1_REVISION_5_INDEPENDENT_REVIEW.md`
  - `docs/security/B1_REVISION_5_REVIEW_PROBES.md`

### PR #40 — docs: publish independent B1 Revision 4 security review

- Class: **B**; open, non-draft. Target: `master`.
- Exact head: `e713a1e0f83ee06ea931f34326afbf3c09ddbb3b`.
- API-recorded base: `0983f6f144cfd39a744b915e89d648740d1187d2`. Actual merge-base with current master: `c19c1a335c6817e9eb2b359e5944a63eea3f3189`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43148243615](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43148243615), exact head match, **success**. Jobs: database-tests=success, tests=success, dependency-audit=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Accept/archive as historical evidence with #42 disposition context; do not apply its verdict to merged revision5.
- Complete changed-file list:

  - `docs/security/B1_REVISION_4_INDEPENDENT_REVIEW.md`
  - `docs/security/B1_REVISION_4_REVIEW_PROBES.md`

### PR #38 — docs: independent B1 Revision 3 review and PostgreSQL 17 probe evidence

- Class: **B**; open, non-draft. Target: `master`.
- Exact head: `a908e12cd43c9e7574818091dcd48f027bb9502c`.
- API-recorded base: `c19c1a335c6817e9eb2b359e5944a63eea3f3189`. Actual merge-base with current master: `c19c1a335c6817e9eb2b359e5944a63eea3f3189`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43141315989](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43141315989), exact head match, **success**. Jobs: dependency-audit=success, tests=success, database-tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Review as historical record; point readers to revision5/#42 before treating old findings as outstanding.
- Complete changed-file list:

  - `docs/security/B1_REVISION_3_INDEPENDENT_REVIEW.md`
  - `docs/security/B1_REVISION_3_REVIEW_PROBES.md`

### PR #35 — docs: Stage A integration readiness and Stage C local staging architecture

- Class: **C**; open, non-draft. Target: `master`.
- Exact head: `e3da0bfa268b26e420f004d9eaabd06f69ccadc4`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43133095308](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43133095308), exact head match, **success**. Jobs: dependency-audit=success, database-tests=success, tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Reconcile with merged B1rev5 and UI2; retain no intermediate B1 staging, explicit tool approvals and #29→#26 sequence. Independent review after documentation corrections.
- Complete changed-file list:

  - `docs/LOCAL_STAGING_ARCHITECTURE.md`
  - `docs/REMAINING_ENGINEERING_LAUNCH_PLAN.md`
  - `docs/SECURITY_INTEGRATION_READINESS.md`

### PR #34 — docs: Milestone 5A backlog, PG17 provider tests and readiness gates

- Class: **C**; open, non-draft. Target: `master`.
- Exact head: `9de431c271b85585c2b5972bcf0b0f6533e5b10e`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43122737311](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43122737311), exact head match, **success**. Jobs: database-tests=success, tests=success, dependency-audit=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Use #35/current B1rev5/#42 and current UI2 counts; provider compatibility and owner decisions are unverified/unimplemented. Review corrected docs.
- Complete changed-file list:

  - `docs/LAUNCH_READINESS_GATES.md`
  - `docs/MILESTONE_5A_IMPLEMENTATION_BACKLOG.md`
  - `docs/PG17_PROVIDER_COMPATIBILITY_PLAN.md`

### PR #33 — docs: final independent verification of PR #26 at e262442

- Class: **B**; open, non-draft. Target: `master`.
- Exact head: `e2d6f811ffa64b6d6b4d7addc6febe566c233956`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43122659048](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43122659048), exact head match, **success**. Jobs: database-tests=success, dependency-audit=success, tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Publish as historical audit evidence with explicit later-head disposition; no device activation or owner risk acceptance inferred.
- Complete changed-file list:

  - `docs/security/PR_26_FINAL_PROBES.md`
  - `docs/security/PR_26_FINAL_VERIFICATION.md`

### PR #32 — docs: independent security audit of PR #29 at bec0a44

- Class: **B**; open, non-draft. Target: `master`.
- Exact head: `3949c8c3a29c8c9cba231f38de5f9324272c1d61`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43121636404](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43121636404), exact head match, **success**. Jobs: tests=success, dependency-audit=success, database-tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Review the documentation as a preserved audit; current integration tests remain required for #29.
- Complete changed-file list:

  - `docs/security/PR_29_INDEPENDENT_PROBES.md`
  - `docs/security/PR_29_INDEPENDENT_SECURITY_REVIEW.md`

### PR #31 — Make onboarding polish test independent of the current date

- Class: **D — unsafe integration; recommend closure without merging**; open, non-draft. Target: `master`.
- Exact head: `9f09c0c72d11d7d4f20a993f8db1f697c31453f4`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43121276490](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43121276490), exact head match, **success**. Jobs: dependency-audit=success, database-tests=success, tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Runtime integration evidence: Claude's independent review, as supplied by the owner, used **disposable PostgreSQL 16**. Current-master `web_tests.test_polish` passed **17/17**; the synthetic master + PR31 candidate failed `test_existing_workspace_does_not_repeat_first_time_onboarding`. PR31 freezes its first dashboard request before the seeded deadline, then expects `?status=overdue`, while UI2 correctly hides that link when the overdue count is zero. This is **reported PG16 evidence**, not a new local reproduction or PostgreSQL 17 verification by this documentation correction.
- Safety disposition: **PR31 is unsafe to merge into current master despite its clean textual merge. Recommend closing PR31 without merging, subject to separate owner authorization.** No closure, merge or test change is performed here.
- Date-independence correction: PR30 and UI2 made the relevant overdue-boundary assertions deterministic, but **the first dashboard request remains unfrozen** in current master. Its overdue-link assertion currently succeeds only when the actual local date is **after November 11, 2026**. Thus the entire test is not fully date-independent. Further hardening belongs in a **separate narrowly scoped test correction**, preserving the owner-approved U2 expectations; merging PR31 is not that correction.
- Complete changed-file list:

  - `server/web_tests/test_polish.py`

### PR #29 — F04b: stop stale password-hash upgrades from undoing resets and changes

- Class: **C**; draft. Target: `master`.
- Exact head: `42910ed09ed1a20aee556e77666cf6e347c724cd`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43129590527](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43129590527), exact head match, **success**. Jobs: database-tests=success, dependency-audit=success, tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: First security implementation to resolve; current-master PG17 race/auth/isolation/website and all three browser suites, then exact-candidate independent verification and owner decision.
- Complete changed-file list:

  - `docs/AUTHENTICATION.md`
  - `server/accounts/backends.py`
  - `server/accounts/views.py`
  - `server/auth_tests/test_password_upgrade_race.py`

### PR #28 — Plan Milestone 5A private staging, costs and readiness gates

- Class: **C**; open, non-draft. Target: `master`.
- Exact head: `48d96ca5cc344da13fe12d441fdf017178950fbe`.
- API-recorded base: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`. Actual merge-base with current master: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43105418737](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43105418737), exact head match, **success**. Jobs: tests=success, database-tests=success, dependency-audit=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: No services selected or purchased. Coordinate with #34/#35 instead of parallel competing staging implementations.
- Complete changed-file list:

  - `docs/MILESTONE_5A_ROADMAP.md`
  - `docs/STAGING_COST_RESEARCH.md`

### PR #27 — Document independent S0-02 design and PR 26 implementation reviews

- Class: **B**; open, non-draft. Target: `master`.
- Exact head: `058220391e74ae9b3e23619fe0aaabfd78957dc4`.
- API-recorded base: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`. Actual merge-base with current master: `64fe8743fa1d3b1c2b1f9e833dca9e5e4fd982bb`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43105416209](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43105416209), exact head match, **success**. Jobs: tests=success, dependency-audit=success, database-tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Independent historical-publication review with #33/#35 correction context; keep design findings and implementation status distinct.
- Complete changed-file list:

  - `docs/security/PR_26_S0_02A_IMPLEMENTATION_REVIEW.md`
  - `docs/security/S0_02_INDEPENDENT_REVIEW.md`

### PR #26 — S0-02A: dormant trusted-device foundation (schema, grants, primitives)

- Class: **E**; draft. Target: `master`.
- Exact head: `44c515f903cc35f1dfdd3d1c2b777a8d1a873222`.
- API-recorded base: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`. Actual merge-base with current master: `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43129781953](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43129781953), exact head match, **success**. Jobs: tests=success, dependency-audit=success, database-tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: After owner-authorized #29 integration, verify accounts.0003 history, actual restricted LOGIN grants, device tests/generation limitations and dormant imports. No device activation.
- Complete changed-file list:

  - `docs/AUTHENTICATION.md`
  - `docs/security/S0_02_RECONCILIATION.md`
  - `docs/security/S1_PROPOSALS.md`
  - `server/academics/ownership.py`
  - `server/accounts/boundary.py`
  - `server/accounts/devices.py`
  - `server/accounts/management/commands/clear_auth_artifacts.py`
  - `server/accounts/management/commands/configure_auth_role.py`
  - `server/accounts/migrations/0003_trusted_device_foundation.py`
  - `server/accounts/models.py`
  - `server/auth_tests/test_trusted_devices.py`

### PR #19 — Bump actions/checkout from 6.1.0 to 7.0.1

- Class: **C**; open, non-draft. Target: `master`.
- Exact head: `8759c8cb7cb2f29332e682dd93b38ddb2ee4459f`.
- API-recorded base: `13c8cc10aa8c4a7b2a2e08c16778f5a9697364ef`. Actual merge-base with current master: `13c8cc10aa8c4a7b2a2e08c16778f5a9697364ef`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43176454130](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43176454130), exact head match, **success**. Jobs: frontend-browser=success, database-tests=success, tests=success, dependency-audit=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Same workflow file as #18: resolve sequentially, preserve pinned SHAs/permissions/credential handling and all current tests; no blind source-file replacement.
- Complete changed-file list:

  - `.github/workflows/quality.yml`

### PR #18 — Bump actions/setup-python from 6.3.0 to 7.1.0

- Class: **C**; open, non-draft. Target: `master`.
- Exact head: `d83d58797410970351d6cdcf4ad7e49c8f4aca34`.
- API-recorded base: `13c8cc10aa8c4a7b2a2e08c16778f5a9697364ef`. Actual merge-base with current master: `13c8cc10aa8c4a7b2a2e08c16778f5a9697364ef`.
- Textual merge conflict: **none** (local tree check); head included in master: **no**. Changed files byte-identical to master: **none**.
- CI: [run43176445957](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43176445957), exact head match, **success**. Jobs: tests=success, dependency-audit=success, frontend-browser=success, database-tests=success.
- Independent review: no formal GitHub review object; see evidence/disposition in the classification table.
- Dependency / acceptance: Review upstream major-version/runner requirements, keep read-only permissions and persist-credentials:false; integrate/test separately from #19 and recheck the second candidate.
- Complete changed-file list:

  - `.github/workflows/quality.yml`

## First prepared engineering slice — current-master PR #29 integration rehearsal

**Purpose:** replace stale three-job branch evidence with a reproducible current-master test candidate, without changing Claude's branch or implementing a new authentication feature. Preparation is complete in this runbook; **candidate database/browser execution has not been performed in this documentation slice**. A clean tree is not evidence that the password race is fixed in master.

1. Re-fetch master and #29. Require the exact head above or stop and assess the delta. Preserve the independent audit in PR #32 and the carry-forward comparison in #35. Do not reuse a stale approval for changed authentication code.
2. Materialize an isolated candidate from current master plus the exact #29 patch in a disposable checkout/test workspace. Record both parents, resultant tree/source manifest and environment versions. Do not push to #29, merge a PR, rebase its owner branch, promote a draft or call this an accepted release. Owner decides any subsequent PR integration workflow.
3. Verify only the four expected #29 paths apply, preserve newer master templates/workflow/queries, and inspect `docs/AUTHENTICATION.md` integration. Keep the current three browser commands and all historical tests. No blind overwrite from an old branch file. Any implementation correction is a separate scoped patch with independent review.
4. Use the repository's hashed runtime/Django/browser locks, Python3.12 and an actual patched PostgreSQL17 disposable cluster. Generate ephemeral synthetic keys/passwords outside tracked files. Use the existing separate non-superuser migrator, auth and runtime LOGINs and forced-RLS runners. No production/student database, JSON migration, web request on the migrator or credential output.
5. Run the complete baseline tests and #29's race tests. Reproduce independent CAS waiting/recheck and row-lock-login observations from #32 on that exact candidate. A post-COMMIT/lost-response probe must distinguish committed state from pre-COMMIT rollback; an HTTP error alone does not prove rollback. Keep same-secret simultaneous logins, stale old-password reset/change, role/CSRF/session boundaries and generic responses covered. Preserve reproducible probes and clean-connection state checks.
6. Run **UI1, premium-auth and UI2 browser suites**, auth and website suites, foundation/isolation/legacy tests, migration drift, role/grant safety and dependency audits. Record actual discovery/skips rather than passing on a predicted count. Source-history expectation is master359 + #29's9 auth tests ≈368 regression tests and27 browser methods; this is **unexecuted reconciliation guidance**, not a result.
7. Publish a test-evidence-only draft PR or a reviewable report on the approved candidate; record exact source tree/parents, commands, versions, counts, failures and hosted CI against that candidate. A docs-only CI run on unchanged master does not test #29. If hosted integrated-candidate CI requires owner-branch integration, prepare the candidate for that owner's action instead of silently changing their branch.
8. Stop for independent exact-candidate verification and owner merge authorization. #46 may be resolved by its separate owner decision without waiting for security tests; no code dependency on the report exists.

Reproduction uses the existing private/disposable setup in [DATABASE_SECURITY.md](../DATABASE_SECURITY.md), [AUTHENTICATION.md](../AUTHENTICATION.md) and [STUDENT_WEBSITE.md](../STUDENT_WEBSITE.md):

```sh
python -m unittest discover -v
python server/manage.py test accounts academics --settings=config.settings.test -v 2
python server/manage.py test security_tests --settings=config.settings.security_test -v 2
python server/manage.py test auth_tests --settings=config.settings.auth_test -v 2
python server/manage.py test web_tests --settings=config.settings.web_test -v 2
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py -v
python -m pip check
python -m pip_audit --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt -r requirements-browser-test-lock.txt
python tools/check_repository_safety.py
```

The database commands require their **different disposable test profiles/environments**, not one shared application database. Offline `auth_migration` handles schema/setup; web profiles must never inherit its login. Capture migration `--plan`, applied inventory and drift on the candidate using that offline process before role-restricted tests.

### Subsequent #26 rehearsal

Only after the approved #29 baseline is selected: repeat on that base with the exact dormant #26 head. Inventory whether `accounts.0003` was ever applied in any persistent environment: revised unmerged migrations are not forward upgrades. No fake migration or destructive reset of persistent data. Verify actual PG17 grants, PUBLIC/membership/MAINTAIN drift, cross-account cookie replay rejection, rotation/issuance concurrency, generation revocation and no active imports/issuance/limits in login paths. Auth role generation-counter monotonicity remains a trust limitation, not an owner-isolation claim. Use #33 probes with current-head disposition from #35. Expected combined discovery ≈432 regression tests (359+9+64) and27 browser methods is **not executed evidence**. Independently review every difference and require exact combined hosted PG17 CI. Dormant acceptance is not permission to activate trusted-device/account restrictions.

## Critical path to a private MVP

The core student workflows already exist: verified sessions, semesters/courses/assignments, actual GPA, hypothetical predictor, target planner and settings. Avoid making every cosmetic roadmap slice a prerequisite for validating that usable product. Private staging still requires explicit acceptance; “private” is not permission to expose it publicly or use real student data.

| Order | Milestone / minimum deliverable | Dependency / acceptance gate |
| --- | --- | --- |
| 1 | Owner resolves unchanged independently approved #46; review this consolidated report | Owner exact-PR decision only; neither PR is merged here |
| 2 | Current-master #29 test candidate and accepted race fix | Prepared runbook above; real PG17 race/auth/role tests, all three browser suites, independent verification, owner exact-head merge authorization |
| 3 | #26 dormant-only integration | Separately approved #29 baseline; migration/role/device/generation proof, full combined tests, independent review and separate owner merge decision |
| 4 | Reconcile planning #42/#35/#34/#28; preserve historical audits #27/#32/#33/#38/#40 | Review documentation as documentation; update release/counts/conditions, preserve historical severity/verdict context and cost-estimate limits. Owner may resolve these docs in parallel with code evidence |
| 5 | Owner-authorized B1a→B1b→B1c→B1d | #29 on master is the explicit B1 prerequisite; Stage A combined baseline chosen separately. D-B1-1…6 decisions and each increment's scope authorization. Real PG17 §6.11 gates plus all three browser/auth/website regressions per increment; no intermediate accepted staging |
| 6 | Local synthetic staging harness and essential journey acceptance | Complete accepted B1, approved WSGI/proxy packages/settings scope; loopback-only, strict hosts/CSRF, HTTPS, verify-full DB TLS, separate roles/forced RLS/pgcrypto, static assets, no migrator in web env, sanitized worker/proxy logs, measured timeout budgets; independent review |
| 7 | Local mail sink/recovery outage, encrypted backup/restore, monitoring and incident rehearsal | Approved local test scope, safe token/log handling, key custody/RPO/RTO/retention decisions. Fresh isolated restore verifies complete academic/auth/RLS/grants state and restored-session policy; observed failures alert an assigned operator |
| 8 | Private provider qualification and access proposal | Provider matrix #34: actual PG17/role separation/forced RLS/pgcrypto/TLS/restore, immutable artifact and rollback, private access, region/privacy/cost/operator approval. No purchases, accounts, DNS or deployment in this work order |
| 9 | Independent security + product-quality acceptance | Core end-to-end CRUD/CSRF/foreign UUID/409/no-JS/recovery journeys, truthful math and query limits, physical-device/AT/actual zoom matrix, usability and performance evidence. Include UI6 header wrapping and UI10 shared14px metadata commitments; do not claim them fixed or all WCAG accepted |
| 10 | Owner private-MVP go/no-go | All evidence and unresolved-risk owners named; deployment/private pilot needs its separate explicit authorization. No public launch approval is implied |

**Planning estimate, not a promise:** security integration evidence1–3 focused engineer-days if no defects; B1's four separately reviewed increments roughly5–10 days; local staging/operational rehearsals roughly5–10 days; independent accessibility/product/provider qualification roughly3–7 days plus reviewer/owner/operator availability. These are unverified estimates, not measured throughput, parallel staffing commitments or a launch date. Failures or policy/provider constraints can add substantial time. Review/approval latency is a real critical-path dependency. Existing local test tools can supply most early evidence without a cloud purchase.

Optional visual work (new dashboard polish, broad dark theme or every remaining premium page treatment) must not displace password correctness, reliable recovery, restoration or actual student task usability. UI3–UI10 remain scoped roadmap items with their own approval/review gates; this report starts none of them. Essential accessibility defects and already accepted UI6/UI10 commitments remain real acceptance tasks, not optional defects hidden by a premium appearance.

## Security and launch blockers / owner decisions

- **Owner resolution:** authorize #46 at its approved exact head; decide closure of unsafe #31 without merging. No automatic draft promotion, merge or closure. Other documentary publications need their independent-review disposition; their age or green CI does not authorize acceptance.
- **Unintegrated authentication:** #29 race fix and #26 dormant foundation are still absent from master. Clean trees and historical approvals are insufficient combined-runtime evidence. Owner chooses exact source/merge sequence after independent candidate verification.
- **B1 scope/policy:** D1/D2 prior-session survival/renewal and failed password-change behavior, D3 timers and their limits, D4 privacy/logging diagnostics tradeoff, D5 increment gates, D6 classification policy. Preserve RB-1…RB-13 and #42 R5-T1/R5-T2 test-placement conditions. Neither statement timeout nor HTTP500/503 proves total request/COMMIT bounds or rollback. No new security implementation starts without its required approval.
- **Active restrictions:** S0-02B/C need separate design/implementation/recovery acceptance; do not issue device cookies, activate account restrictions, add trusted-device UX or the optional daily100 cap through this cleanup. Owner/security review must decide an acceptable private-MVP abuse/recovery baseline. Reliable verified email and accessible independent recovery are prerequisites to any hard account restriction, not promises from a local console backend.
- **Operations:** no accepted staging release, production WSGI/proxy setup, real email, tested encrypted restoration, provider compatibility, key rotation, privacy-safe monitoring, retention/support/incident ownership or release rollback is established by merged UI2. Proposed Gunicorn/Caddy and infrastructure spend need explicit owner/tool approval. Local synthetic experiments are not hosted operational evidence.
- **Academic/product quality:** keep exact Decimal mathematics, F versus ungraded, UUID ownership, RLS/roles, version conflicts and no invented academic trends. UI6 header readability and UI10 metadata remain unfinished; actual AT/mobile/zoom/load/privacy acceptance still needs evidence and named reviewers.
- **Risk acceptance:** current CI does not accept logging gaps, external proxy paths, device generation trust, lost-response sessions, provider outage or privacy/legal obligations for the owner. Assign explicit owners/decisions before private deployment; report **NOT LAUNCH READY** until the gates are met.

## Handoff and scope

First authorized safe slice completed: **one consolidated documentation report plus a concrete #29 integration-test preparation protocol**. Existing approved #46 was deliberately left unchanged. No application, tests, auth, RLS, migrations, grants, dependencies, CI workflow or historical reports changed. No real/student data, purchase, deployment, PR merge/closure or security activation.

Local checks: one-file documentation scope, links/fences, consistency with the captured15-PR inventory, repository safety and whitespace. Hosted CI for this report's exact head is recorded in its draft PR. Those checks run on the existing master implementation, **not** the unexecuted synthetic #29/#26 trees. The open-PR inventory predates this report's own new draft PR; re-fetch before any owner decision, particularly if another actor advances or merges a branch.

**Exact next safe engineering action:** review this report and execute the prepared isolated current-master #29 integration rehearsal within the existing fix's test scope; do not implement B1 or alter authentication policy. Stop at independent exact-candidate review. The immediate owner action available independently is the #46 merge decision. Later activation, provider spending, deployment and every security-sensitive increment remain separately gated.
