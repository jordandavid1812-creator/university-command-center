# Milestone 4B: student website polish and quality review

Original base: `fefd3cae4efeac5539bc3f02e9ffdc53bfb88766` (PR #23 verified merged).
Delivery base: `e04dd4d76bde599da43f055065908678cd3768eb` (PR #24's S1 source-address
throttle fix, merged while 4B was in progress). The unpublished feature branch was
fast-forwarded to updated master with the polish reapplied, preserving the security
fix and its 13 tests. No published history was rewritten or PR merged by this work.
Branch: `feature/student-web-polish`. Local verification: 11 November 2026.
No deployment, automatic merge, personal JSON import or Milestone 5 work.
The prioritized [plan](MILESTONE_4B_PLAN.md) was written before implementation.

## Original problems and improvements

- The phone dashboard began with a tall decorative welcome panel and four stacked
  cards. Actual CGPA was below the first screenful. A compact heading and consistent
  quick actions now precede two-column phone metrics. The same saved results and
  grade rules are shown, without invented progress percentages. New accounts get
  a three-step semester → course → assignment guide; overdue counts link to work.
- Finding a course/task required repeated pagination. Lists now offer literal,
  case-insensitive search (80 characters maximum) by course code/name and assignment
  title/course. Search combines with the existing semester/status/sort filters,
  persists across pagination/refresh, is escaped in feedback and has a clear-filter
  link. It is an ordinary GET and works without JavaScript.
- Form error summaries existed but lacked automatic keyboard focus. The optional
  local script now focuses a returned summary after invalid submission. Summary
  links lead to fields; hidden version errors explain reloading without linking
  an invisible input. Values remain on screen after validation/version conflicts.
  Shared website account forms reuse the same summary. Existing non-website auth
  profiles retain their original presentation and authorization behavior.
- Required/optional guidance, scoped parent help, larger checkboxes and comfortable
  action links make forms easier to understand and operate. Login explains what to
  do after session expiry; no client-controlled redirects or automatic resubmission
  were added. Delete confirmations and dependency protection remain intact.
- Added named spacing/focus tokens, consistent compact panel radii, high-contrast
  sidebar focus, 44 px secondary action targets and forced-colors support. Existing
  semantic tables, status text, reduced-motion rules and local assets are retained.
  No framework, tracking, external font, animation or runtime dependency was added.

## Performance and PostgreSQL

The original read helpers called require_identity again *inside* student_transaction,
which already checks the capability, live session and signature before yielding.
Read helpers now obtain student_id from the immutable capability **only inside that
validated transaction**. Explicit owner filters, signed database transaction/backend
context, role checks and forced RLS remain in place. Authentication, capability,
CRUD-service, database-model, migration and grant implementations are unchanged.
No private-record cache or cross-request identity cache was introduced.

Measurements use Python 3.12.14, Django 5.2.19, psycopg 3.3.8, PostgreSQL 17.11,
Linux x86_64/glibc 2.41, localhost SCRAM connections and separate actual restricted
runtime/auth LOGIN roles. A synthetic student owns 61 courses and 61 assignments;
a second student owns separate records. Each page gets one warmup and seven measured
GETs via Django Client, including authentication, SQL, calculations and HTML rendering.
SQL counts include transaction/context statements; migration connection counts are zero.
The baseline and isolated polish measurements below were collected before PR #24;
the complete updated-master suites/browser journey were then rerun successfully.
Timing varies with shared-machine contention; query reductions are the reproducible
result, not a production SLA or a statistical performance guarantee.

| Page | Before ms | Isolated polish ms | Updated-master repeat ms | Runtime queries | Auth before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dashboard | 78.67 | 43.64 | 64.79 | 20 | 28 → 20 |
| Courses | 72.18 | 37.91 | 62.51 | 19 | 28 → 20 |
| Semesters | 45.83 | 25.69 | 36.53 | 11 | 20 → 16 |
| Pending assignments | 55.90 | 41.08 | 63.94 | 11 | 20 → 16 |
| Performance | 45.94 | 30.89 | 38.69 | 11 | 20 → 16 |
| Predictor | 336.58 | 152.24 | 204.31 | 11 | 20 → 16 |
| Planner | 34.96 | 35.53 | 73.31 | 11 | 20 → 16 |

Isolated after-run minimum/maximum ranges were dashboard 38.96–57.28 ms, courses
35.08–48.74 ms and predictor 127.09–255.55 ms. A previous post-change repetition
measured dashboard 64.57 ms and planner 35.04 ms; the initial post-change run
measured dashboard 51.49 ms. Planner is within noise of baseline (34.96 →35.53 ms),
so no universal latency improvement is claimed. All query counts were stable. The updated-master repetition retained those exact
query reductions; pending assignments (63.94 ms) and planner (73.31 ms) were slower
than baseline in that repetition. These local runs do not support a universal
latency-improvement claim. Shared-machine load and page/auth overhead require
controlled follow-up profiling before making production timing promises.


The opt-in reproducible harness is `server/web_tests/benchmark.py`:

```sh
# Same disposable three-role PostgreSQL environment used for web_tests.
# PGTESTDATABASE must name a separate disposable database, never personal data.
python server/manage.py test web_tests.benchmark --settings=config.settings.web_test -v 1
```

It creates synthetic data in a runner-created/dropped database and prints aggregate
JSON measurements only. It is excluded from normal test*.py discovery and CI timing
assertions. CI uses deterministic query-count/growth assertions instead: increasing
records across page boundaries adds no per-row queries and never uses the migrator
for page requests. No fragile wall-clock thresholds were added.

EXPLAIN ANALYZE for the owner-scoped pending assignment list used the existing owner
index in one run and a sequential scan in the final tiny-table run, then sorted and
limited the result (isolated run 0.392 ms). The updated-master repetition used the
owner index again (0.378 ms). Existing owner, foreign-key and unique-code
indexes were inspected. No additional index/migration was justified by this small
fixture. Literal substring search can scan an owner's matching records; it is not
promised constant-time or trigram-indexed. Large-scale search, deep OFFSET pages,
external pool and load behavior still need representative data and review.

## Large accounts and mathematical correctness

All original limits remain: 25 rows/page, page 1–10000, 1000 courses/200 semesters
for analysis, 200 predictor courses, 1000 course/200 semester parent options,
64 KiB/600-field POSTs. Search narrows lists without changing account-wide GPA.
Over-limit analysis still rejects the request rather than displaying a partial CGPA.
Predictor semester narrowing remains available; no prediction is persisted.
Parent selectors are still bounded dropdowns, not newly paginated remote widgets.
Search improves locating records but does not resolve every unusually large account.
No grading rule, Decimal adapter, semester UUID grouping or calculation formula changed.

## Accessibility methodology and limits

Target: applicable WCAG 2.2 AA criteria, without a compliance claim. Checked semantic
landmarks/headings, labels/help/error associations, status text, keyboard focus/skip,
mobile navigation, native scroll-region keyboard operation, touch targets, reduced
motion/forced-colors CSS and text resizing. All information remains readable as text;
GPA meters supplement numeric values, never replace them.

Supplementary axe-core 4.11.1 runs use WCAG 2 A/AA, 2.1 AA and 2.2 AA tags in
Chromium 156.0.8078.79/Playwright 1.65.0 on Linux. QA-only axe lives in ignored work/;
it is not a shipped dependency. Audited empty dashboard, all eight populated pages
at 1440 and 390 px, the invalid course form and invalid search filter (19 states).

Final automated outcome: **zero axe violations across 19 states**. Five phone
states reported incomplete color-contrast checks for horizontally clipped table
cells/actions. These were not counted as passes: computed foreground/opaque ancestor
background contrast was checked separately (minimum 7.47:1 for affected actions,
15.53:1 for affected plain table text), and the same tables were fully checked at
desktop width. This limited computed-color inspection is not a full manual audit
of every visual state or assistive-technology combination.

Initial axe testing found tightly stacked error-summary links violating target-size.
They now have separate 44 px click areas and the rerun passed. Keyboard checks cover
skip-to-main, form entry/submission, summary-to-field focus, mobile navigation and
horizontal table scrolling. Text was explicitly doubled using computed CSS font
sizes to check reflow; this simulates text enlargement and is not a complete native
browser-zoom/device text-settings certification.

No real screen-reader behavior was tested. Orca is not installed in this Linux
executor; no NVDA/JAWS/VoiceOver environment is available. Automated names/landmarks
and focus tests do not establish screen-reader usability. Manual assistive-technology,
real-device, OS text scaling, high contrast and a wider browser matrix remain needed.

## Browser journeys and responsiveness

Synthetic users only; actual restricted runtime/auth credentials, no migration
connection in the localhost WSGI process, in-memory verification email and real CSRF.
Before implementation, the unchanged 4A browser smoke passed. Final Chromium checks:

- Registration/email verification/login, empty workspace onboarding and all pages.
- Semester/course/assignment CRUD, status changes, actual grades, correct weighted
  GPA/CGPA, read-only predictions/reset and target planning.
- Cross-tab optimistic conflicts retaining input; dependency-protected deletion.
- Six widths: **360, 390, 768, 820, 1024 and 1440 px**, with no document overflow.
- Keyboard skip-to-main and complete semester creation by Tab/type/Enter, mobile
  navigation, horizontal table scrolling and summary links focusing invalid fields.
- JavaScript-disabled semester creation/deletion and course search.
- Search/filter submission, refresh/back, clear filters, invalid forms and doubled
  text sizes without document overflow. Native tables remain horizontally scrollable.
- Two separately registered/verified/authenticated students; a known foreign edit
  UUID returns the same safe unavailable-record page.
- Password change invalidates copied old session; new login works. A synthetic
  session's server expiry is set in the test fixture through the narrow auth role;
  the next request returns to login with clear guidance. Logout/back/refresh cannot
  re-enter authenticated pages.
- No JavaScript page errors or unexpected HTTP 5xx responses.

Desktop/phone screenshots were visually inspected. Screenshots, cookies, verification
links and test environment files are not committed. No student records were read
from legacy JSON. No public service was started.

## Automated/security verification

| Suite | Result |
| --- | --- |
| Legacy CLI/Streamlit/academic/storage | 113 passed |
| Original 2A database | 33 passed |
| Original 2B security | 46 passed |
| Authentication including PR #24 | 76 passed |
| Original 4A website | 52 passed |
| New 4B regressions | 17 passed |
| Total unique ordinary tests | **337 passed** |

The final website suite reports 69 passing tests. The optional synthetic benchmark
also passed separately (one experiment, excluded from the 337 count). No test
failures remain.

All 307 Milestone 4A historical test sources and the 13 upstream S1 tests are unchanged. All new records use synthetic names
and example.invalid email. PostgreSQL integration/security tests use actual LOGIN
roles and real migrations, never SQLite or privileged SET ROLE impersonation.
Existing suites verify RLS SQL bypass attempts, owner-consistent relationships,
role separation, CSRF/XSS, session/password invalidation, optimistic conflicts and
rollback/context reuse. New regressions additionally test read rejection for missing,
forged and logged-out identities, search ownership/escaping/literal SQL wildcards,
query counts, pagination/filter combinations, exact global GPA and retained limits.

System checks, migration drift, Python compilation, JavaScript syntax, pip check,
strict pip-audit of both hashed runtime locks, repository safety and whitespace checks
passed. Both runtime locks report no known vulnerabilities; no advisory suppressions.
CLI/Streamlit, original academic helpers, storage/actions, dependencies, models,
services, ownership/authentication code and migrations are unchanged from master.

Verification fixes: a scratch benchmark initially used the generic Django runner
and failed on missing role grants; it was corrected to the existing authentication
runner. Two new test assertions incorrectly expected different HTTP status codes;
expectations were fixed without changing product responses. npm/pip-audit initially
hit read-only default caches and were rerun with ignored workspace caches. Repeated browser rehearsals also hit the existing registration IP throttle; only
the disposable synthetic fixture counters were reset between runs, without changing
application throttling. The keyboard harness initially compared a URL without allowing the preserved
skip-link fragment; the saved record was correct. A session-expiry fixture initially
called synchronous Django ORM inside Playwright’s async context; it was replaced
with parameterized SQL over the existing narrow auth login, without disabling
Django’s async guard. The first axe attempt lacked the QA asset until installation succeeded. No authorization was
weakened to address tooling or test failures.

Hosted CI is verified separately on the pushed commit/PR. The implementation
report records local evidence; do not infer hosted success from it. Refer to the
PR checks and final delivery report for GitHub-confirmed workflow results.

## Complete file-change summary

| File | Change |
| --- | --- |
| `.github/workflows/quality.yml` | Enable push checks on this feature branch; existing website discovery includes new tests |
| `server/academics/queries.py` | Bounded literal course/task search; eliminate redundant in-transaction identity lookups |
| `server/student_web/views.py` | Pass validated search filters to scoped read services |
| `server/student_web/forms.py` | Bounded labelled search fields, optional labels, parent help |
| `server/student_web/static/student_web/site.css` | Spacing/focus tokens, compact mobile metrics, touch/error targets and forced colors |
| `server/student_web/static/student_web/site.js` | Progressive focus on server-rendered error summaries |
| `server/student_web/templates/student_web/dashboard.html` | Compact greeting/actions, first-time steps and overdue-work link |
| `server/student_web/templates/student_web/courses.html` | Escaped search feedback and clear-filter action |
| `server/student_web/templates/student_web/assignments.html` | Escaped search feedback and clear-filter action |
| `server/student_web/templates/student_web/components/filter.html` | Focusable filter errors and links to visible search/filter controls |
| `server/student_web/templates/student_web/components/form_fields.html` | Required-field guidance, accessible hidden-version feedback |
| `server/accounts/templates/accounts/form.html` | Website-only shared summary and session-expiry guidance |
| `server/web_tests/test_polish.py` | 17 focused PostgreSQL regression tests |
| `server/web_tests/benchmark.py` | Opt-in reproducible synthetic page/query/index benchmark |
| `docs/MILESTONE_4B_PLAN.md` | Prioritized pre-implementation audit/plan and baseline |
| `docs/MILESTONE_4B_REVIEW.md` | This implementation/verification report |
| `docs/STUDENT_WEBSITE.md` | Current workflows, tests, benchmark and limitations |
| `README.md` | Review/website guide pointers |
| `AGENTS.md` | Preserve quality/security contracts for future changes |

## Remaining risks and suggested Milestone 5 priorities

No public-readiness claim. Production HTTPS, email delivery, secret rotation,
proxy/cookie configuration, monitoring, distributed abuse protection, backups/restore,
retention/recovery policy and independent security review remain necessary. The
existing auth-role/trusted-Python/DBA compromise and stolen-session limitations remain.
The newly merged [security audit](security/SECURITY_AUDIT.md) and
[remediation plan](security/REMEDIATION_PLAN.md) remain authoritative additional
inputs: per-account login throttling is owner-paused (S0-02), per-student write quotas
are absent (S0-03), and further audit findings require separate security work. Read/
form limits are not write quotas. These were not silently changed as UI polish.
Future operational logs should redact query strings because searches can contain
student-entered terms. Current-semester choice is URL-local; no preferences or saved scenarios were added.

Suggested priorities, subject to a new task: real student usability sessions and
screen-reader/device testing; representative larger-account/query/pool load review;
then a production operations/security plan before considering public hosting.
Prioritize paginated parent selection/indexed search only after measuring real needs.
Do not infer graduation/repeat-course policies. No Milestone 5 implementation started.
