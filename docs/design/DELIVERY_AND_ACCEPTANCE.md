# Implementation strategy, regression plan and approval gates

**Proposal only.** No work below is authorized by this blueprint. Changes must be small, independently reviewable and confined to the approved UI scope. Keep the framework, mathematics, storage/security contracts and CLI/Streamlit intact. Baseline for this design audit: master `c19c1a3`; re-pin the actual implementation baseline after any security merges.

## Proposed PR sequence

Effort ranges are unverified focused engineering days excluding review/user testing. They are sizing guides, not a delivery promise. Each PR includes relevant no-JS, responsive, keyboard and regression evidence; do not defer all accessibility work to the final PR.

| PR | Small concrete scope | Expected files / constraints | Acceptance / dependency | Estimate |
| --- | --- | --- | --- | --- |
| D0 design approval | Owner selects palette, hierarchy, mobile lists and system theme; resolve copy/test-policy decisions | This blueprint only | Review concept + screen/state tables; no implementation by merging docs | Review |
| UI1 tokens, shell and focus | Consolidate semantic variables, spacing/type and shared primitives; scrollable sidebar/short-height fix; mobile wordmark/menu styling. Keep route order initially | site.css, narrowly scoped accounts/base markup if needed; no service/view/query changes | Close UI-01 at 1280×500/200% text; no clipped focus or new overflow; shared auth/academic shell smoke; no raw new app dependencies | 1–2 d |
| UI2 dashboard pilot | Recompose existing summary/attention/upcoming/selector and prerequisite-aware first-use actions; keep complete semester table initially | dashboard.html, metrics include or isolated new includes, CSS; existing context only | Zero additional DB reads; no fabricated data; mobile attention/task reachability; actual 0 vs Not graded; no parentless primary CTA; owner approves presentation-copy/test changes | 1–2 d |
| UI3 assignment management list | One responsive list with visible completion/Edit/Delete controls; existing search/status/sort/pagination | assignments.html, a record include, CSS only unless reviewed presentation attributes needed | Same POST/CSRF/version payload, statuses/dates and safe GET links; foreign/stale records rejected; all primary controls visible at 320/360; no optimistic state | 1–2 d |
| UI4 course list and form polish | Responsive course records; refine native field spacing/validation/prerequisite guidance. Preserve all fields/validators | courses/edit/components templates, CSS; form widget attributes only after narrow approval | Unique account-wide code, Decimal credits, optional grade, changed-course UUID relationships and 409 retained values; search/page contracts unchanged | 1–2 d |
| UI5 semester organization | Compact semester records, clear display order, edit/delete consistency | semesters/delete templates + CSS; no reorder API | Duplicate labels stay distinct by UUID; server order preserved; protected deletion and hidden version unchanged | 0.5–1 d |
| UI6 actual performance | Higher-contrast actual-summary hierarchy and accessible semester meters/table | overview/performance templates + CSS | Same actual results/scope/precision, complete text table, no chronology/trend fiction; keyboard horizontal scrolling; ungraded versus zero explicit | 1–2 d |
| UI7 predictor and planner | Clear hypothesis/assumptions/result hierarchy; narrow/mobile forms; visible states | predictor/planner templates + CSS | No writes, no floats, unchanged course-selection/limit semantics, unrounded target decisions, existing precision; no saved scenarios | 1–2 d |
| UI8 account task presentation | Task-specific public composition, recovery links, native labels/autofill; clean settings identity/actions | accounts form/message/base and settings templates; limited widget attributes only if approved | **Coordinate with Claude's accepted security head first.** Generic responses/statuses/CSRF, reset/verify/change/session behavior unchanged. Do not wrap B1 static errors in a DB-dependent template | 1–2 d |
| UI9 system dark theme | Complete semantic token mapping, native-control color scheme, focus/status/table/print audit | CSS only for initial system mode | No local/session storage, auth cookie or DB preference; 24 proposed pairs plus rendered-state audit in both modes, forced colors and print | 1–2 d |
| UI10 cross-screen quality | Resolve integrated visual/AT/usability regressions and document evidence | Narrow presentation fixes and reviewed tests | Full acceptance matrix below; actual screen reader/phone checks and independent security regression status; no launch implication | 2–3 d + tester availability |

The sum is roughly 10.5–20 focused days; real validation/review may extend elapsed time. Do not scope a framework migration, third-party design system, SPA or new backend into a “polish” PR. Shared primitives must be checked on all consuming pages. Dark tokens are designed up front even if their implementation PR is later.

## Historical test and presentation-copy policy

Existing baseline suites are legacy **113**, foundation **33**, isolation **46**, auth **76**, website **69** on current master; the exact integrated security head can add auth tests (PR29 adds nine; PR26 adds 64). Record actual discovery and prior expected counts for the chosen SHA rather than carrying a stale total. Do not delete/rewrite calculation, validation, ownership or authentication tests to accommodate appearance.

Known presentation assertions need a conscious decision: `web_tests.test_pages` expects “Welcome back, alpha”; `test_polish` checks Actual CGPA before “Current semester” and the no-browser-storage script behavior. The proposed primary H1 “Dashboard” and honest “Selected semester” wording need either preservation of useful existing wording **or explicitly approved, narrowly justified presentation-test updates**. Do not hide obsolete copy off-screen solely to satisfy old assertions. The first UI PR must list affected assertions before coding; keep backend/security/math checks unchanged. If that approval is absent, retain those visible labels in the first dashboard iteration while improving layout.

New tests should verify meaningful contracts (visible keyboard target, retained hidden version, no new reads, correct state, same saved math), not simply mirror every CSS class. Visual snapshots supplement functional assertions and need human review of each intentional change.

## Regression matrix

| Area | Required evidence / assertions |
| --- | --- |
| Academic truth | Actual all-ungraded → Not graded; real zero/F remains 0.00 and counts units; mixed grades/units weighted correctly; no averaging semester GPAs; Decimal boundaries and duplicate/invalid legacy handling unchanged. Predictor never contaminates actual summary; planner status uses unrounded server result |
| Record integrity | Create/edit semesters/courses/tasks; repeated semester labels remain separate; account-wide normalized-code uniqueness; exact units; original/normalized display; title/code edits preserve UUID relations; status toggle payload and record_version retained; stale update/deletion gives existing conflict; dependent deletion protected |
| Forms | Empty/bound/invalid/hidden-version/parent-empty/conflict states; explicit labels/optional markers; native Enter/submit; no-JS; paste/autofill; no duplicated IDs/form controls or accidental GET writes; double-click/bfcache behavior |
| Search/pagination | Literal %, _, quotes and HTML escaped; bounded 80-character inputs; q/semester/status/sort preserved appropriately; clear filters returns real state; page counts/bounds; no data-empty fallback on 400/503; no infinite/unbounded list |
| Isolation/auth | Two synthetic students, known/forged foreign UUIDs, expired/stale sessions, CSRF denial, logout POST, password reset/change/verification and no-new-authority failure cases on accepted security SHA. UI cannot choose owner, expose hidden identities or mint capability |
| Performance | Preserve query-budget/no-N+1 checks and snapshot limits (1000 courses/200 semesters, predictor 200); upcoming preview remains ≤5 and list page 25. Dashboard redesign adds zero reads; record-list layout adds zero reads. No remote fonts/icons/trackers, no data-bearing client cache |
| Responsive | 320, 360, 390, 768, 820, 1024, 1280 and 1440 CSS widths; 1280×500 and short landscape; portrait/landscape actual devices; long labels/username/code/units/date; no document overflow. Named real-data tables may scroll locally with visible hints and keyboard access |
| Error/security copy | Validation versus conflict versus unavailable versus uncertain outcome; no fabricated success/rollback/delivery; no raw usernames/IPs/passwords/cookies/token paths/body/SQL in new telemetry; safe route linking and no external URLs based on user input |
| Themes/states | Light/dark/system, hover/focus/active/disabled, autofill, native selects/date inputs, badges, meters, browser zoom, print, reduced motion, forced colors; all important content remains readable if CSS/JS enhancement is absent |

Existing math/CLI/Streamlit suites remain separate. Django and isolation regressions run against **real PostgreSQL 17** with actual restricted auth/runtime logins and offline test provisioning, never SQLite or a privileged web connection. Full browser/task evidence must name the tested release, database patch, browser/OS/device and fixture revision. This planning task has not run those new implementation suites.

## WCAG 2.2 AA and mobile acceptance gates

| Gate | Required check / evidence |
| --- | --- |
| Structure/sequence | One H1 and meaningful title, landmarks, skip link, headings, labels and native semantics; source/focus/reading sequence matches meaningful visual order; active route announced; decorative icons hidden |
| Keyboard/focus | Every task reachable without mouse; no traps; focus visible and not obscured at all widths/heights, particularly the reproduced sidebar case; return focus for any future dialog; no hover-only actions |
| Contrast/semantics | Text ≥4.5:1 (or permitted large-text ≥3), essential controls/state/focus ≥3; status not color alone; tested actual surfaces in both modes. Opaque token-pair calculations are supporting evidence only |
| Reflow/zoom | 200% text resizing and 400% browser zoom/320px-equivalent reflow; no clipping of labels/messages/actions; supported two-dimensional tables scroll within their region, not the page. Browser text-size settings and OS enlargement tested, not only screenshot dimensions |
| Touch/inputs | 44px preferred targets with spacing; applicable WCAG 2.5.8 minimum 24px/spacing exceptions documented, not silently treated as 44px compliance. Real iOS/Android select/date controls, orientation and text zoom work; no drag-only action |
| Forms/errors/status | Error summary focus, links to visible fields, aria-describedby/invalid relationships, retained values, announced success/conflict, one announcement channel rather than doubled nested live regions; no critical timed dismissal |
| Accessible authentication | Paste/password managers/autofill remain available; no cognitive puzzle or extra re-entry; generic auth errors and recovery path remain discoverable; no JS-only trust/recovery step |
| Motion/preferences | Reduced motion removes non-essential transitions; no fake animated grades; forced colors preserve boundaries/focus/current state; print supplies actual/hypothetical labeling and values |
| Real assistive tech | At least NVDA/Firefox or equivalent Windows combination and VoiceOver/Safari on actual iOS/macOS; exact versions recorded. Test nav, list/table, error summary, completion, predictor/planner and auth recovery. Missing environment is Not tested, not Pass |
| Automated support | axe with applicable WCAG 2.0/2.1/2.2 A/AA rules across representative pages/states; investigate incomplete contrast/scroll checks; no blanket compliance claim from zero violations |

Critical security/data/math defects, invisible focused actions, unmanageable forms or inaccessible core journeys block acceptance. Fix/retest High/Critical usability defects before a private representative reviewer session; severity and any exception need a named owner. A premium visual score cannot override these gates.

## Performance and maintainability budgets

Preserve the current tiny local asset footprint (CSS ~18.2 KB, JS ~1.8 KB uncompressed). Proposed first-pass ceilings are **≤30 KB CSS and ≤5 KB JS uncompressed**, excluding existing third-party runtime dependencies and test-only tools; owner approves any justified exception. Target no new runtime request/dependency/font payload, no extra dashboard SQL and no query growth from rendering children. Use the repository's benchmark on a fixed environment and current real data bounds; report p50/p95/query counts and compare, not invented production latency or a timing assertion in ordinary CI. A local screenshot or synthetic 1/5/10-user run is not a launch SLA.

Keep existing CSS/JS URLs, use semantic tokens instead of append-only overrides, and add includes only where reuse is real. Do not build a giant component framework, CSS-in-JS layer or arbitrary UI library. Use default browser controls/progressive HTML; introduce a dependency only with a concrete gap, license/security/performance review and owner approval.

## Security-work dependencies and ownership

| Area | Restriction / coordination gate |
| --- | --- |
| PR29/PR26/Stage A | Current master still lacks the approved security implementations. Re-pin after owner-authorized integration; run the combined PG17 suites. A UI plan does not merge them or resolve migration history |
| B1 failure classification/rendering | Independent reviews in PR37/PR38 requested changes. Do not implement a visual error-handler replacement, assume 503 means rollback, promise no session renewal, or make B1 minimal responses depend on rich templates, account context or DB reads |
| Authentication templates/routes | Shared accounts/base/form/message files overlap Claude's work. Require a file-level coordination check and exact baseline before UI8. Credential fields, generic responses, CSRF, role boundaries and reset/session semantics remain security-owned |
| S0-02B/C device/throttling/recovery | Do not add trust-browser controls, account-quota meters, retry countdown logic, remembered-device management, delivery promises or recovery enforcement merely because a design resembles another SaaS product |
| Data/rendering | Pass existing authorized view context; no browser owner IDs, ad hoc queryset inside include, global/private cache, hidden network call, local drafts or storage. Synthetic fixtures only for previews/tests |
| Theme/telemetry | Initial CSS system theme adds no persistence. No analytics SDK, session replay, grade/identity capture or external font/image requests. Any preference storage and historical no-storage-test change needs explicit scope approval |
| Error/logging privacy | Styling can share static colors after review, but cannot copy token URLs, exceptions, account state or raw metadata into the DOM/telemetry. Proxy/server logging and Stage C requirements remain separate |
| Roadmap operation | No deployment, infrastructure provisioning, external email, JSON migration, purchasing or public pilot is included. Modals/new routes/backend helpers remain separate proposals, not implicit scope |

A workspace-only template/CSS PR can be independently reviewed before every future security feature exists, but it must use the approved current boundaries and cannot claim launch readiness. Avoid changing auth files unnecessarily in the dashboard pilot; scope shared CSS changes and test their auth consumers. Any integration conflict is reviewed, not solved by overwriting Claude's branch.

## Owner decisions before coding

1. Approve the Academic Studio visual direction or request adjustments to palette/wordmark/type hierarchy.
2. Authorize the smallest UI1 slice and the dashboard pilot, with exact file scope and baseline. This blueprint alone authorizes neither.
3. Approve the “Dashboard”/“Selected semester” presentation-copy changes and narrowly corresponding presentation-test updates, or retain tested visible wording initially.
4. Approve responsive management lists and retention of native GPA comparison tables; keep full-page confirmation/edit flows initially.
5. Choose system-driven light/dark first; persistent manual theme, custom fonts, modals and extra preferences remain deferred decisions.
6. Assign actual screen-reader/mobile testers and confirm accessibility/performance budgets and who can accept a documented non-blocking limitation.
7. Coordinate UI8/auth copy with Claude after the accepted security review; explicitly exclude new auth/backend/data features and launch authorization.

## Evidence this planning task actually produced

Source/template audit, inspection of historical synthetic screenshots/report, 48 fresh static Chromium viewport observations, a reproduced short-height Tab-focus issue, 24 computed proposed contrast pairs, static desktop/phone/dark concept artifacts and documentation checks. No live backend/security flow, real screen reader, device/browser matrix, load test, new axe pass, new PostgreSQL behavior or implemented redesign is claimed. Read [the audit](FRONTEND_AUDIT.md) for exact limits. The next action is review of this design, not implementation.
