# UI2 — Academic Studio student dashboard

Branch: `frontend/ui2-academic-dashboard`. Verified base/master at start: **`ed8890982d99b7be5262d997e2e76266a4b65b0c`**, as requested. UI1 and premium auth were already merged. Dashboard presentation only; UI3 and security branches are untouched. Exact submitted head and hosted CI run are recorded in the draft PR.

## Before → after

Before: four equally weighted metric cards, always-promoted child creation links, a large selector/workload block before deadlines, and “Current semester” implying a persistent choice.

After: one prerequisite-aware primary action; conditional overdue attention; one dominant actual CGPA with compact supporting facts; upcoming work next; an accurately labelled **Selected semester** GET view; the full native semester comparison and supported quick actions. This brings real next work forward without adding requests for data or inventing metrics. One DOM/reading order works across desktop and mobile; no CSS order reversal.

[Before desktop](evidence/ui2/before-graded-1440.png) · [After desktop](evidence/ui2/graded-1440.png) · [Before phone](evidence/ui2/before-graded-390.png) · [After phone](evidence/ui2/graded-390.png)

## Design and scope

Warm ivory, deep green, system UI typography and the existing semantic tokens connect the dashboard to Academic Studio. The welcome surface alone optionally uses 96%-white frost with an opaque fallback. Academic values, deadlines, native controls and tables stay opaque. Dashboard cards retain the standard **12px** radius; auth's 20px radius/serif-story exception is not copied into academic UI.

The header keeps “Welcome back” and wraps long usernames. Its action is Create your first semester → Add course → Add assignment as actual prerequisites become available. View GPA overview is a supported secondary action. Footer quick actions have the same prerequisite checks. The empty comparison no longer promotes a course-create route without a semester.

Actual CGPA is supplied by `summary.gpa`, with a None check (not a truthiness check): **0.00 is real**, Not graded means missing actual grades. Attempted credits, graded/ungraded counts and real course count use the loaded context. No percentages, standing, predicted progress, reminders or chronology are invented. Warnings remain visible.

A positive real overdue count links to the existing filter. No attention block is rendered at zero. Upcoming rows keep the existing five-record maximum, exact dates, normalized course codes and owned-record edit links. No-upcoming wording still invites review of overdue work; it does not claim all work is complete. No completion/write control or assignment-management redesign is introduced.

The existing selector still submits GET with the same semester UUID values and Show semester GPA action. Its scope is explicitly this view, not a saved active semester. The complete existing comparison include, text values and meters remain, including separate rows for identical labels. Its keyboard-scrollable table retains its native semantics and scrollbar/hint.

Changed implementation files: only `student_web/dashboard.html`, new `student_web/dashboard.css`, dashboard/presentation tests, one existing browser asset-inlining helper and one CI browser command. There are **no changes to views, queries, services, calculations, models/migrations, ownership, RLS, authentication/session/recovery, minimal error handlers, application JS or dependencies**.

## Engineering evidence — zero additional database queries

[Recorded counts](evidence/ui2/query-counts.json) and [reproducible observation source](UI2_QUERY_PROBE.md), on real PostgreSQL **17.11**, compare the old template at the pinned base against UI2 using the same view, verified synthetic sessions and records. The old template was supplied through a test-only locmem loader; no application code or old template snapshot was added to the application.

| State | Baseline auth/runtime/migrator | UI2 auth/runtime/migrator |
| --- | --- | --- |
| Empty | 20 / 20 / 0 | **20 / 20 / 0** |
| Populated | 20 / 20 / 0 | **20 / 20 / 0** |

The committed regression additionally renders the already-loaded real view context under query capture: **0 auth, 0 runtime, 0 migrator reads** during rendering. Existing request query-budget/no-N+1 tests still pass. These are local observed counts, not a production latency guarantee.

No additional queryset access is hidden in an include. Course counts use the loaded list; deadline course codes use the existing select_related result. All authorization and snapshot/query bounds remain in their existing services/views.

The dashboard asset is **7,155 bytes**, plus unchanged site.css **21,923 bytes** = **29,078 CSS bytes per dashboard**, within the 30 KB page budget. The auth-only stylesheet is not loaded by the dashboard. Aggregate repository CSS is larger because the auth and dashboard entry styles are mutually exclusive; the budget here is explicitly page payload. This isolation avoids changing shared/auth styles. Application JS remains 1,774 bytes and no remote asset/framework/library is added.

## Regression evidence

Local: Python 3.12.14, Django 5.2.19, psycopg 3.3.8; PostgreSQL **17.11** with the established separate migration/auth/runtime LOGINs and forced RLS. Synthetic fixtures and local test email only; no SQLite and no real JSON imports.

| Suite | Result |
| --- | --- |
| Website | 90 passed (79 existing + 11 UI2) |
| Authentication | 76 passed |
| Restricted-role isolation | 46 passed |
| Foundation/academic database | 33 passed |
| Legacy CLI/Streamlit/calculations | 113 passed |
| Focused UI2 + polish rerun | 28 passed; final UI2 assertions also rerun separately |
| Baseline/new query observation | 1 method passed, empty and populated cases |
| UI1 browser | 10 passed |
| Premium-auth browser | 5 passed |
| UI2 browser | 7 passed |
| All three hashed dependency locks audited | No known vulnerabilities |
| Django check / migration drift | No issues / no changes detected |

UI2 covers no semesters, semesters without courses, all ungraded, actual zero, mixed grades, overdue without upcoming work, five-record previews, same-label UUID rows, full comparison, foreign account data/forged semester rejection, native GET and page asset budgets. Existing academic/security tests are preserved.

Only presentation assertions in `test_polish.py` changed: Current → Selected semester; zero-overdue attention is now absent (the actual zero count is still asserted); the one-overdue accessible label uses singular grammar. These implement the requested copy/conditional behavior, not weaker calculation or security expectations.

The browser investigation caught two issues before submission: a duplicate outer/inner “Semester performance” region name (outer redundant label removed, inner native scroll region retained), and UI1's row flex-basis becoming a tall blank column above mobile actions. A dashboard-only override and a header-spacing regression prevent that blank gap. No auth/shared stylesheet change was needed.

## Accessibility and responsive checks actually performed

The seven UI2 browser methods cover **eight states × eight required widths = 64 layout cases**, plus 18 compact-header cases. Widths: 320, 360, 390, 768, 820, 1024, 1280, 1440 CSS px. Empty/graded/long states also use 1280×500 and 1440px at 200% root text size, and **320×200 equivalent reflow for a 1280×800 viewport at 400%**. This is equivalent-layout evidence, not a claim of actual browser-zoom testing.

Checks: no document overflow; meaningful H1/source order; actual mobile section order; readable action grouping; long username/title wrapping; keyboard-reachable primary action in short viewports; unchanged sidebar focus; no-JS GET submits the selected UUID; comparison keyboard scrolling and complete two-row text. Overdue attention precedes actual results only when positive. Native controls and full-page navigation remain.

Rendered important text pairs pass ≥4.5:1; control borders/focus pass ≥3:1 on adjacent opaque/attention/welcome surfaces using alpha-aware composition. Frost is optional and has an opaque fallback. Forced colors remove blur/shadow, preserve boundaries/focus, and keep text/links native. UI2 adds no motion; reduced-motion behavior and the existing meaningful motion-probe regression remain. No fixed mobile overlay, tooltip-only control, chart-only value or focus trap is added.

**Not tested:** real screen readers, physical phones, Safari/Firefox, actual browser zoom or a complete axe/WCAG 2.2 AA audit. Automated/Chromium evidence is not certification. Existing two-dimensional comparison-table local scrolling remains an intentional supported pattern; assignment-list adaptation is UI3, not this PR.

## Synthetic screenshot pack

All records, names, grades and dates below are **explicit synthetic test fixtures**, not real students or fabricated production data. Values are calculated by the existing `academic_summary`/presentation helpers. [Actual browser metadata](evidence/ui2/browser-metadata.json): system Chromium **156.0.8078.79**, Playwright **1.65.0**, Django **5.2.19**. Hosted CI prints its own managed Chromium version.

| State | Desktop | Phone |
| --- | --- | --- |
| Empty | [1440](evidence/ui2/empty-1440.png) | [390](evidence/ui2/empty-390.png) |
| Graded | [1440](evidence/ui2/graded-1440.png) | [390](evidence/ui2/graded-390.png) |
| Ungraded | [1440](evidence/ui2/ungraded-1440.png) | [390](evidence/ui2/ungraded-390.png) |
| Actual zero | [1440](evidence/ui2/zero-1440.png) | [390](evidence/ui2/zero-390.png) |
| Overdue only | [1440](evidence/ui2/overdue-1440.png) | [390](evidence/ui2/overdue-390.png) |
| Long content | [1440](evidence/ui2/long-1440.png) | [390](evidence/ui2/long-390.png) |

[1280×500 / 200% text](evidence/ui2/long-1280x500-text-200.png). Before images use the pinned baseline template with the **same graded fixture**, not another student's records.

![Synthetic graded dashboard](evidence/ui2/graded-1440.png)

## Reproduction / independent review gate

Use existing hashed Python/browser dependencies and the PostgreSQL instructions in [STUDENT_WEBSITE.md](../STUDENT_WEBSITE.md) / [DATABASE_SECURITY.md](../DATABASE_SECURITY.md). Each database suite uses its existing offline runner and private environment, never a migrator for web requests.

```sh
python server/manage.py test web_tests --settings=config.settings.web_test
python server/manage.py test auth_tests --settings=config.settings.auth_test
python server/manage.py test security_tests --settings=config.settings.security_test
python server/manage.py test accounts academics --settings=config.settings.test
python -m unittest discover -v
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py --screenshots-dir work/ui2-evidence -v
```

Set `UCC_CHROMIUM_EXECUTABLE=/usr/bin/chromium` to reproduce the local screenshot browser; otherwise use the installed Playwright-managed Chromium. Static browser fixtures use the dummy DB backend and no running app; they are presentation checks, not authentication or RLS verification. The database suites provide separate runtime evidence.

Hosted CI is reported with the exact head/run after completion, not predeclared by this document. Owner/Claude review must assess visual hierarchy, evidence and test changes. No UI3, security integration, infrastructure provision, deployment, service purchase or merge is included. Existing security/B1 work and real AT/device validation remain separate dependencies before launch readiness.
