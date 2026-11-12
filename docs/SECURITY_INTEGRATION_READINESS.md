# Stage A — security-integration readiness

Planning/readiness only, checked 12 November 2026 (Africa/Lagos). Implements no authentication changes and performs no integration, PR merge/closure, deployment or purchase. Source scope: [owner's execution plan](REMAINING_ENGINEERING_LAUNCH_PLAN.md). Local architecture preparation: [Stage C](LOCAL_STAGING_ARCHITECTURE.md).

**Readiness: ready for an owner-authorized merge sequence. Stage A is not complete.** No accepted combined security release SHA exists yet. Master remains `8295fbdcf5db84342a46e4ecc7dcf6a4e813e6a5`, including merged PR #30; both security PRs remain open drafts.

## Current exact-head evidence

| PR / purpose | Head and disposition | Hosted Foundation quality run |
| --- | --- | --- |
| [#29 password reset/hash-upgrade race](https://github.com/jordandavid1812-creator/university-command-center/pull/29) | `42910ed09ed1a20aee556e77666cf6e347c724cd`; independent **APPROVE FOR MERGE**, scope pinned to this head | [43129590527](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43129590527), success |
| [#26 dormant trusted-device foundation](https://github.com/jordandavid1812-creator/university-command-center/pull/26) | `44c515f903cc35f1dfdd3d1c2b777a8d1a873222`; independent **APPROVE FOR MERGE, dormant S0-02A only** | [43129781953](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43129781953), success |
| [#27 earlier independent reviews](https://github.com/jordandavid1812-creator/university-command-center/pull/27) | `058220391e74ae9b3e23619fe0aaabfd78957dc4`; open, historical findings need later disposition context | [43105416209](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43105416209), success |
| [#28 5A roadmap/cost research](https://github.com/jordandavid1812-creator/university-command-center/pull/28) | `48d96ca5cc344da13fe12d441fdf017178950fbe`; open, planning only | [43105418737](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43105418737), success |
| [#32 PR29 audit](https://github.com/jordandavid1812-creator/university-command-center/pull/32) | `3949c8c3a29c8c9cba231f38de5f9324272c1d61`; open, documentation only | [43121636404](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43121636404), success |
| [#33 PR26 final verification](https://github.com/jordandavid1812-creator/university-command-center/pull/33) | `e2d6f811ffa64b6d6b4d7addc6febe566c233956`; open, original conditional review; subsequent integration satisfied its mandatory pre-merge conditions | [43122659048](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43122659048), success |
| [#34 5A backlog/provider/gates](https://github.com/jordandavid1812-creator/university-command-center/pull/34) | `9de431c271b85585c2b5972bcf0b0f6533e5b10e`; open, documentation only | [43122737311](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43122737311), success |

Both security integrations were independently re-compared: the entire binary diff from reviewed `bec0a44` → `42910ed`, and from reviewed `e262442` → `44c515f`, exactly equals `64fe874` → master `8295fbd`. Only PR #30's seven added lines in `server/web_tests/test_polish.py` changed. Authentication, device primitives, migrations, dependencies and workflow implementation are unchanged. Earlier independent PostgreSQL 17.11 probes therefore retain relevance; a new full audit is not required for that test-only delta.

The hosted security-head runs passed all three jobs (tests, dependency-audit, database-tests) with PostgreSQL 17. Verified DB-suite counts: PR29 foundation 33 / isolation 46 / auth 85 / website 69; PR26 foundation 33 / isolation 46 / auth 140 / website 69. These are individual-branch results, not combined-release results. This preparation rechecked GitHub state and Git diffs; it did not run a new database suite or create a merged tree.

## Owner-authorized future sequence and stop conditions

1. Owner authorizes PR #29 integration first. The implementation owner confirms the exact reviewed head and branch protections, takes the PR out of draft if appropriate and merges through the approved workflow. This document does none of those actions.
2. Record new master SHA and CI. Reassess PR #26 against that updated master before separately authorized integration. Current changed-path intersection is only `docs/AUTHENTICATION.md`; production implementation paths are disjoint. This is encouraging static evidence, **not** proof of a conflict-free combined merge or passing tests. Resolve any documentation conflict without losing the two distinct security descriptions. Any implementation change requires targeted review.
3. Owner separately authorizes PR #26. Preserve dormant behavior and no login imports/cookie activation. Verify migration/grant plan and require current exact-head CI before accepting integration.
4. On the accepted combined candidate run legacy with Streamlit, foundation migrations, restricted-role isolation, auth and website suites separately on actual PostgreSQL 17. Retain role identities, skipped-case count, schema drift and dependency/safety audit outcomes. Rerun the independent race and device probes from PR #32/#33 appendices against that exact candidate.
5. Expected discovery is roughly 410 existing tests if the only additions are PR29's nine and PR26's 64 to the current 337-test baseline: legacy 113 + foundation 33 + isolation 46 + auth 149 + web 69. Treat this as a reconciliation expectation, **not an executed result**. Investigate unexplained test disappearance/skips; do not adjust the claimed baseline to hide them. Independent probes are additional.
6. Verify merged source has no active trusted-device lane/cookie handling or hard account restrictions, and test that password reset/change, session invalidation and exact role/RLS boundaries still work together. Record new exact CI links and release SHA; independent reviewer confirms changed scope.
7. Review documentation PRs separately. Preserve historical SHA-specific findings and append/update current dispositions rather than presenting obsolete findings as current blockers. Green documentation CI does not review accuracy or authorize infrastructure.
8. [PR #31](https://github.com/jordandavid1812-creator/university-command-center/pull/31), head `9f09c0c72d11d7d4f20a993f8db1f697c31453f4`, is still open. Its alternative date fix is redundant with #30. Its present diff against master would remove #30's explicit next-day overdue assertion. Recommend authorized closure rather than merging it; **no closure performed**.

Stop for a changed security implementation SHA, failed CI, unexpected migration state/privilege escalation, unexplained missing tests, active device wiring, personal data in fixtures or missing owner authorization. Do not bypass branch protection, weaken grants or skip failing security tests to finish Stage A.

## Release/evidence record to complete after authorization

| Field | Current value |
| --- | --- |
| Accepted combined security release SHA / artifact digest | **Not available: not integrated** |
| Owner authorizations for #29, then #26 | **Pending** |
| Exact combined CI run and full suite/probe outcomes | **Pending combined release** |
| PostgreSQL patch/client version and actual role evidence | Earlier independent tests: 17.11; combined-run evidence pending |
| Dormant-feature assertion, schema/grant revision and migration inventory | Individual-branch evidence retained; combined verification pending |
| Unresolved risks / independent acceptance | Below; no staging/deployment acceptance |

## Risks retained after Stage A

- **Baseline race:** master has not yet received PR29's fix. Approval of a branch does not repair running/master code. The combined release must actually contain it before accepted staging authentication.
- **Migration history:** unmerged accounts.0003 was revised in place. An old applied 0003 is not upgraded by fetching new code; inventory persistent databases and require a reviewed forward migration if necessary. Never fake migrations or discard persistent data.
- **Generation counter:** service increments/locking protect in-flight issuance when callers captured the old generation before verification. The auth SQL role can lower the counter directly; grants alone do not enforce monotonic values. This is a documented trusted-auth-role limitation, not a reproduced student-controlled bypass.
- **S0-02B/C:** account/device admission, successful-quota accounting, campus fairness, correct-password behavior under restrictions, replay/response-loss/session-finalization failures and independent accessible recovery need separately approved implementation/review. No hard restrictions before real delivery and recovery are independently verified. The optional daily 100-attempt cap remains deferred.
- **Operations:** private origin/HTTPS, exact provider roles/pgcrypto/TLS, complete backup/restore, key custody, restored-auth/throttle state, privacy-safe telemetry and real email remain unqualified. Green CI is not launch acceptance.

Stage C design can proceed independently. Stage C implementation, Stage B implementation/activation and every later stage require their own explicit scope approval under the owner's plan.
