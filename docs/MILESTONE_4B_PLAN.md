# Milestone 4B: audit and prioritized plan

Base: fefd3cae4efeac5539bc3f02e9ffdc53bfb88766; PR #23 verified merged.
All eight pages, create/edit/delete pages and shared account forms reviewed in
source; the unchanged 4A Chromium journey passed before editing. Synthetic phone
and desktop screenshots inspected. PostgreSQL 17.11, Python 3.12.14/Django 5.2.19,
restricted runtime/auth LOGIN roles, localhost only.

## Findings and work order

1. Phone dashboard: large hero and single-column metrics push actual CGPA and
   deadlines down. Replace decorative greeting with compact heading/quick actions;
   retain recognizable actions and all academic semantics. Keep primary metrics
   compact and provide a short next-step onboarding sequence for empty accounts.
   Link overdue counts directly to filtered work. Never invent progress percentages.
2. Lists: all safety bounds exist but locating records requires paging. Add bounded
   literal code/name/title search to course and assignment lists, preserving filters,
   pagination and owner/RLS scope. Keep all numeric limits and global GPA analysis.
3. Forms: summaries already link errors, but hidden-version errors link invisible
   fields and no focus is moved to errors. Render hidden errors without dead links,
   show a required-field explanation, add contextual parent/grade help and focus
   summaries progressively. Keep inputs after errors and no-JS flows.
4. Design: consolidate spacing/color tokens, flatten hero, improve sidebar focus
   contrast, touch targets and phone/tablet density. Keep native scrollable tables,
   text statuses, reduced-motion and no remote assets/framework.
5. Performance: seven warmed authenticated GETs/page with 61 courses/61 assignments
   found dashboard 20 runtime +28 auth queries and course list 19+28. Each read
   repeats require_identity inside an already authenticated student_transaction.
   Use the capability's student_id ONLY inside that existing validated transaction;
   preserve its live-session/signature/database checks, explicit filters and RLS.
   Do not cache private records or edit authentication/ownership implementations.
   Re-run identical fixture/harness and add query-growth/authorization regressions.
6. Verify all original 307 tests unchanged, focused new tests, actual PostgreSQL,
   six viewports, keyboard/no-JS, axe supplement if available, 200% text sizing,
   two students, expired session/back/refresh and password/session invalidation.
   Record actual accessibility coverage; do not claim WCAG certification.

## Baseline (local, seven warmed requests; includes auth, SQL and rendering)

| Page | Median ms | Runtime/auth/migration queries |
| --- | ---: | --- |
| Dashboard | 78.67 | 20/28/0 |
| Courses | 72.18 | 19/28/0 |
| Semesters | 45.83 | 11/20/0 |
| Pending assignments | 55.90 | 11/20/0 |
| Performance | 45.94 | 11/20/0 |
| Predictor | 336.58 | 11/20/0 |
| Planner | 34.96 | 11/20/0 |

These are local diagnostic observations, not production latency promises. A first
scratch benchmark used the generic Django runner and failed on role grants; it was
corrected to the project's AuthenticationTestRunner before collecting this baseline.
No permission or product behavior was weakened. Preserve local raw timing JSON in
ignored work/; publish summarized outcomes in MILESTONE_4B_REVIEW.md.

## Completion boundary

Document full changes, before/after and limitations, run all tests/audits/checks,
push feature/student-web-polish and open PR to master. No deployment, automatic
merge, schema/role changes, formulas, JSON migration or Milestone 5 work.
