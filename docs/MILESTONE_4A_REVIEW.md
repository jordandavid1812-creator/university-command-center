# Milestone 4A implementation and verification report

Base master: `2208f8d2e4b7a612ed4cea3bd69312446de915b0` (PR #22 verified merged).
Branch: `feature/student-web-app`. Verified 11 November 2026.
No public deployment, automatic merge or Milestone 4B work is included.

## Delivered website

A complete local server-rendered Django academic workflow now includes:

- Personalized dashboard with actual CGPA/attempted credits, course and graded/
  ungraded totals, assignment completion/pending/overdue counts, upcoming deadlines,
  semester performance and an explicit current-semester selector.
- Semester create/list/edit/order/confirmed protected delete and semester course links.
- Course create/list/filter/edit/code/credit/semester/actual-grade management,
  genuinely ungraded state, duplicate feedback and protected removal.
- Assignment create/list/edit/complete/pending/delete, date sorting, filters and
  Africa/Lagos due-today/overdue handling. No overdue records are auto-deleted.
- Credit-weighted GPA/CGPA overview, selected-course hypothetical GPA prediction
  with reset, Decimal target planning with all three engine outcome states.
- Verified account settings, password-change link and secure POST logout.
- Reusable shared account/website templates, local responsive CSS, semantic
  navigation, skip/focus support, labelled forms/errors, empty/success/conflict
  states, native accessible meters and horizontally scrollable mobile tables.
- Minimal optional busy/duplicate-submit feedback JavaScript; no framework/HTMX
  or external assets, and core forms work with JavaScript disabled.

The page inventory/plan was written before implementation in
[MILESTONE_4A_PLAN.md](MILESTONE_4A_PLAN.md). Setup, architecture, bounds, security
and 4B deferrals are detailed in [STUDENT_WEBSITE.md](STUDENT_WEBSITE.md).

## Backend and calculation compatibility

All writes use the existing owner-scoped CRUD services and version checks. New
bounded read services in academics.queries use signed context, explicit owner
filters, evaluated page results, joined metadata and SQL assignment aggregates.
No models, schema migrations, RLS policies, database grants or role boundaries were
replaced. Web requests still have no migration/DBA connection and keep separate
restricted academic/auth logins. Website tests verify zero migration queries.

PostgreSQL Decimal credits are adapted without float conversion. The only change
to academic_logic is accepting Decimal in its course-credit type guard; every
formula, grade scale, target boundary and existing warning behavior is unchanged.
Semester UUIDs, not labels, group calculations, preserving separate same-labelled
semesters. Current semester is explicitly selected, never inferred from order.
Course-code edits retain assignment links through UUID relationships.

All 255 historical test sources are unchanged. CLI/Streamlit, JSON storage/action
code and original calculation entry points remain unchanged. No personal JSON was
read, migrated, rewritten or deleted; all database/browser records were synthetic.
No new application dependency or runtime lock change was required.

## Automated verification

Actual local versions: Python 3.12.14, Django 5.2.19 LTS, psycopg 3.3.8 and
PostgreSQL 17.11. Database tests used actual PostgreSQL and distinct LOGIN roles,
not SQLite or a runtime simulated by SET ROLE from a superuser.

| Suite | Result |
| --- | --- |
| Legacy CLI/Streamlit/academic/storage | 113/113 passed, no skips |
| Original Milestone 2A database tests | 33/33 passed |
| Original Milestone 2B security tests | 46/46 passed |
| Original Milestone 3 authentication tests | 63/63 passed |
| New website integration/calculation/security tests | 52/52 passed |
| Total distinct automated tests | **307 passed** |

The website suite also passed using the exact CI role-bootstrap helper with NEW
non-superuser test migrator, runtime and auth logins on a fresh test database.
The final additional generic permission/error-cache checks passed in the full
52-test website suite. Test-only CREATEDB belongs solely to the migrator; no
application role receives migration, bypass or schema ownership rights.

Coverage includes empty/populated dashboards, all CRUD, exact Decimal/weighted
GPA, duplicate labels, F/ungraded distinction, prediction non-persistence/reset,
planner boundaries/outcomes, form validation, duplicate codes, protected deletion,
stale edit/delete/status conflicts, scoped parent choices, foreign/forged UUIDs,
CSRF, XSS escaping, safe redirects/errors, no-store error handling, two concurrent
student sessions, bounded pagination/analysis and accessible control structure.

Checks passed: no migration drift, Django system checks, Python compilation,
JavaScript syntax, whitespace/repository safety, pip check and strict pip-audit of
both existing hashed runtime locks. The audit found no known vulnerabilities and
used no advisory suppressions. Local passing checks do not establish hosted CI;
read the pushed commit/PR's workflow results separately.

## Browser and visual verification

Real Chromium 156.0.8078.79 with Playwright 1.65.0 exercised the LOCAL website on
127.0.0.1 using only restricted application credentials and in-memory email:

- Registration/verification/login, all eight primary pages and navigation.
- Semester/course/assignment creation, edits, completion/pending, filters and deletion.
- Protected deletion feedback, safe course-code changes retaining assignment links,
  and two-tab version conflicts retaining unsaved input until explicit reload.
- Expected weighted actual GPA, selected-course prediction/reset without actual
  changes, planner outcome, account settings and logout.
- Labelled controls, one main page heading, keyboard mobile navigation and native
  horizontal table scrolling. Table headers remain readable at phone widths.
- No document horizontal overflow at 1440, 820, 390 and 360 pixel widths.
- Semester creation/deletion with JavaScript disabled.
- No browser page JavaScript errors or unexpected HTTP 5xx responses.

Desktop and phone screenshots were visually inspected using synthetic data; no
student screenshots or email/cookie/link secrets were committed. The browser harness
kept email links in memory and suppressed token-bearing access logs. Local static
serving remains explicitly development-only, with DEBUG off.

Initial verification found and fixed an aggregate alias shadowing the completed
field and a phone table-header layout issue. A test harness SessionStore iteration
was corrected to inspect keys. Browser assertions were corrected for ambiguous
status-option text/numeric scale and foreground keyboard focus. CSRF, authorization
and RLS were not weakened to make tests pass. No test failures remain locally.

## Limits, risks and Milestone 4B deferrals

Technical bounds are explicit: 25 rows/page, page <=10000, 1000 analysis courses,
200 semesters/selectable parents, 200 predictor courses per form, 64 KiB/600-field
POSTs. Over-limit analysis is rejected instead of reporting a partial GPA. No
records are removed. Very large pre-existing accounts require reviewed selector/
query-limit expansion. Current-semester selection is URL-local, not a saved preference.

Formal real-device/screen-reader accessibility review, external-pool/load tests,
production HTTPS/email/secrets/proxy configuration, distributed abuse protection,
monitoring, backup/restore and account/data lifecycle policy remain necessary before
public use. IP throttles retain the limitations documented in AUTHENTICATION.md.
Academic snapshots use normal statement-level transaction behavior; concurrent
changes may appear on refresh. Trusted Python/auth DB/DBA compromise and stolen
valid sessions/email links remain outside the request-isolation guarantee.

Milestone 4B may consider preferences, advanced search, saved scenarios, additional
visualizations, larger-account UX and broader device polish. No full production
launch, mobile app, payments/subscriptions/social login, email change, account deletion
or real JSON migration is included. The repository is ready for review of 4A,
not for public hosting.
