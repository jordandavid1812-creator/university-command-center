# Milestone 4A page inventory and implementation plan

Base: 2208f8d2e4b7a612ed4cea3bd69312446de915b0 (PR #22 verified merged).
Branch: feature/student-web-app. Source inspection completed before coding.

## Feature inventory and mapping

| Existing Streamlit/CLI feature | Django destination |
| --- | --- |
| Dashboard: actual CGPA, graded/ungraded, attempted credits, pending work, semester performance | Personalized dashboard, explicit current-semester selector, completed/pending/overdue totals and upcoming deadlines |
| Courses: add/edit name, credits, semester and actual grade; protected removal | Paginated course list plus create/edit/confirmed delete; code edits supported safely through UUID assignment FKs |
| Free-text semesters grouped in record order | Explicit semester create/list/edit/order/delete and course filtering |
| Assignments: add, complete/pending, confirmed removal | Paginated due-date list, create/edit/status/delete, pending/completed/upcoming/overdue filters |
| Academic performance: weighted actual GPA/CGPA and semester bars | Read-only overview using academic_summary, accessible meter/table and no fabricated grades |
| Predictor: temporary grades, all selected courses require a prediction | Optional per-course hypothetical selections, weighted prediction for selected courses only, reset via GET, no writes |
| Target planner: desired CGPA, remaining credits and required average | Decimal form using target_plan and its achievable/guaranteed/impossible states |
| Milestone 3 account/session flows | Basic account settings, verified identity, password link, POST logout and styled existing auth pages |

## Input mismatches and preserved semantics

- Streamlit course forms currently offer integer credits 1–6; the established
  database/shared credit contract is 0.0001–1000000 with four decimal places.
  The Django forms use that existing full contract, without changing Streamlit.
- PostgreSQL credits are Decimal; the engine currently restricts course records
  to int/float. Extend ONLY that accepted numeric type to Decimal, retaining
  checked_credits and every existing formula. Do not convert through float.
- JSON semester labels are not identities. PostgreSQL permits duplicate labels;
  adapt semester UUID strings as engine grouping keys and attach display labels
  afterward. Explicit display_order controls presentation, not chronology.
- No current-semester field exists. Dashboard selection is an explicit read-only
  GET choice; never guess current chronology from a label/order.
- Courses use normalized per-owner codes, fixed precision and nullable A–F grades.
  Preserve NULL versus F and credit weighting. UUID assignment links make safe
  course-code edits possible, unlike old JSON string links.
- PostgreSQL records already have typed dates/Boolean completion and owner FKs;
  no personal JSON load/import/repair is part of this work.
- Use timezone.localdate in the website's Africa/Lagos timezone for deadlines.

## Implementation and security plan

1. Add student_web templates/forms/views/read adapters and opt-in web settings.
   Keep original auth/foundation profiles and all 255 tests intact.
2. Reuse account templates for a consistent local CSS layout, semantic navigation,
   skip links, keyboard focus, labels/errors, mobile navigation and empty states.
   No frontend framework/HTMX is necessary. Minimal optional JavaScript adds busy feedback and duplicate-submit protection; all flows work without it.
3. Extend owner-scoped read services with bounded pagination/filtered reads and
   dashboard aggregates. All mutations stay in existing version-checked services.
4. Add strict forms with shared credit/target/grade validators and scoped parent
   choices. Confirm deletes, retain submitted values on validation/conflict and
   show safe understandable messages; never send owner/server fields to services.
5. Bound pages to 25 rows (max page 10000), analysis to 1000 courses/200 semesters,
   predictor forms to 200 courses and POST bodies to 64 KiB. Reject over-limit
   analyses instead of displaying a misleading partial GPA. No records are deleted.
6. Preserve session-bound capabilities, distinct roles, forced RLS, CSRF/POST,
   escaped templates, safe redirects and generic errors. No web migration credentials.
7. Test all CRUD/calculations/security/layout on real PostgreSQL, run all historical
   suites, verify Chromium desktop/mobile/keyboard flows, audit dependencies and
   extend CI. Document limits and 4B deferrals, push and open a master review PR.
8. No deployment, real JSON migration, backend replacement, formula rewrite,
   social login/payments/mobile app, automatic merge or Milestone 4B.
