# Page-by-page experience and wireframe specifications

Planning only. These specifications use existing data/routes/forms. The [visual concept](PREMIUM_DESIGN_DIRECTION.png) shows the compositional direction; conditional states and accessible behavior below are authoritative. No academic values are fabricated, no new backend feature is promised and no auth flow is implemented.

## Shared frame and information architecture

Desktop: grouped ~15rem sidebar, local wordmark, clear active link, main content bounded to about 76rem and a short page header. Put page purpose in the H1/subtitle, not in a repeated decorative banner. Account identity remains available in Settings; a small existing username label can identify the current account but should not force a long username into every H1.

Phone/tablet below 1024px: brand + Menu disclosure, H1, primary action, priority content, supporting sections. Let the document scroll normally. Navigation disclosure is non-modal and works without JS; focus stays predictable. At all widths, skip-to-main is first reachable, all status text is readable and no fixed overlay masks focused inputs.

```text
DESKTOP                                    PHONE
Sidebar | Dashboard + primary action       UCC | Menu
        | Conditional attention            Dashboard + primary action
        | Actual summary | Upcoming work   Conditional attention
        | Selected term  | Comparison      Actual summary, compact counts
        | Complete overview link           Upcoming saved tasks
                                           Selected semester
                                           Semester comparison / overview
```

Use one explicit DOM/reading order at every breakpoint: **page header → conditional onboarding/attention → actual summary → upcoming work → selected semester → semester comparison**. Desktop puts summary and upcoming work beside each other in that order; phone stacks them. The overdue-count action is early when needed, and the first task no longer waits until after the large semester selector/workload panels. Do not use CSS reordering that makes keyboard focus jump against the visible sequence. Supporting counts belong to the summary region; they can wrap without becoming four oversized mobile cards.

## 1. Dashboard — first redesigned screen

**Purpose:** orient the student and expose the next useful task while showing actual academic performance. **Existing inputs:** summary, courses, semesters, selector, current/current_selected, totals and up to five upcoming assignments. **Routes:** dashboard GET with `semester`, existing create/list/overview URLs. **Primary action:** prerequisite-aware; see onboarding below.

Desktop composition:

1. Compact Dashboard header, one primary action. For an established workspace with a course, Add assignment is primary; Add course is secondary. With no courses/semesters, use the valid parent creation action instead.
2. Actual CGPA + explanation and “View GPA & CGPA”; distinguish Not graded from actual 0.00. Supporting units/graded/ungraded are quieter than the main result.
3. Next work: an attention link with the **real overdue count** if positive, then existing upcoming records, each with title, course code and exact date. Caption “Next up to five pending deadlines, due today or later.” Do not list individual overdue tasks without a separately approved query.
4. Selected-semester form, selected GPA/attempted units from the existing context, and explicit Show action. No persistent active-term claim, no inference from free-text label.
5. Semester comparison as a secondary complete section or a clearly labeled preview with a link to the complete overview. Do not compute a new CGPA from a truncated preview. First PR should keep the existing complete table to avoid unnecessary behavior changes.

Phone: put conditional urgent attention and the upcoming-work preview before the current large selector panel; keep actual CGPA high in the page and supporting counts compact. The first actionable saved record/overdue link should be encountered without passing four equal metric cards plus two forms. Exact above-fold positions vary with language/text zoom; accept logical priority and task reachability, not a brittle pixel screenshot.

States:

| State | Required presentation | Forbidden inference |
| --- | --- | --- |
| No semesters | “Start with one semester”; Create first semester primary, then explain course → assignment sequence | No fake CGPA, completion percentage or dismissible persisted onboarding state |
| Semester exists, no courses | Add course primary; link to semester management; Not graded | Do not tell the user to add an assignment before a valid course exists |
| Courses exist, all ungraded | Useful workload view + Not graded and ungraded count | Not 0.00 as missing-data fallback |
| Graded records exist | Actual values from summary, including a legitimate 0.00 | No prediction leakage |
| Overdue >0, upcoming empty | Attention count link + “No upcoming deadlines; review overdue work” | Do not celebrate “All caught up” |
| No assignment work | Neutral “Add an assignment when you have a deadline” | Do not infer productivity or academic success |
| Load/error/limit | Supported error state with no empty fallback | No cached student/global record substitution |

## 2. Semesters

**Purpose:** organize records using explicit display order. Existing paged records expose UUID, label and order; the current template has a View courses link, **not an available per-semester course count**.

Layout: page header + Add semester; a compact record list with label, “Display order: …”, View courses, Edit and Delete. Mobile stacks these within one record so the ordering and actions remain discoverable. Keep actual order from the server, even when labels match. “Display order” help explains organizational purpose and does not claim chronological progression.

Creation/edit: retain label/order fields and hidden version, with explicit Save/Cancel. No drag-to-reorder or bulk persistence is shown: it would require a reviewed endpoint, multi-record concurrency and accessibility design. Delete opens the existing confirmation; dependent records remain protected. Same-label semesters are distinguished by their record context/order, never merged into one grade group. Empty: Create first semester; invalid form: summary/field links; 409: keep submitted values and explain reload.

## 3. Courses

**Purpose:** maintain actual course identity, units, semester and grade. Preserve unique code across the student's semesters and UUID relationships. Existing fields/search/semester filter and pagination remain unchanged.

Desktop: course code/name is the dominant row identity; semester is secondary; credits and actual-grade text align consistently; Edit is the visible primary row action, Delete secondary. Phone: use one semantic record list, with code/name first, labeled Semester/Credits/Actual grade values, then Edit/Delete. No duplicate desktop/mobile forms, hidden action carousel or icon-only editing. Performance comparisons remain in the Overview table rather than making every management view a dense spreadsheet.

```text
Courses                                  [Add course]
[Search code or name] [Semester] [Apply]  [Clear filters]
────────────────────────────────────────────────────────
SYN-CODE · [saved course name]
Semester [saved label]    Credits [value]    Actual grade [value/Ungraded]
[Edit course]                                      Delete
────────────────────────────────────────────────────────
Previous          Page n of n · real count          Next
```

The wireframe's bracket text is a binding slot, not a fabricated course. No new enrollment status, lecturer, timetable or completion policy is introduced.

Form order: course name/code → semester → credits → actual grade; final order should be tested with beginners. Preserve server fields/IDs/limits even if their visual grouping changes. Help explicitly says ungraded is excluded, F counts, codes are account-wide unique and valid credits retain up to four places. Do not narrow numeric limits to match a guessed university convention. No inline autosave or grade dropdown that changes actual records on selection.

Empty with active filters: No matching courses + Clear filters, not “your account is empty.” Unfiltered empty: Add first course if a semester exists. A direct child-create route with no parent retains its visible parent link and disabled save explanation. Search input remains bounded/literal; clearing/pagination preserve expected GET behavior.

## 4. Assignments and deadlines

**Purpose:** make the next action obvious and retain overdue work. Existing search/status/sort choices, records and completed/version fields are sufficient; no task priority, reminders or calendar backend exists.

Desktop: scannable task rows; title/course first, exact due date, labeled status and one complete/pending toggle action. Phone: full-width record; title, course/date/status, then a visible ≥44px primary completion control and Edit/Delete links. Use a **single responsive semantic list/article**, not two hidden sets of forms. Preserve exact POST action, CSRF and hidden record_version/completed values. The button's accessible name includes the task title. A task is not shown as completed until the real server outcome supports it.

```text
Assignments                           [Add assignment]
[Search]  [Status: existing choices]  [Deadline sort] [Apply]
┌──────────────────────────────────────────────────┐
│ [saved title, allowed to wrap]                    │
│ [course] · Due [exact date] · [status words]       │
│ [Mark complete / Mark pending]       Edit  Delete │
└──────────────────────────────────────────────────┘
```

Do not add a “Due today” filter chip backed by an unsupported status value; today may be labeled on returned rows. Overdue/upcoming links use current supported values. Optional relative wording must accompany the exact Africa/Lagos date and use the server's supplied date, not browser-local recalculation. Completed old tasks must not be styled overdue. The list is paged; no claim of all tasks displayed or global counts from one page. Keep tasks under every supported filter discoverable and preserve server sort order.

Empty results offer reset/another filter; no-results and an unavailable request are distinct. 409 status changes explain stale input and require reload; no double-submit retry, local queue, global cache or optimistic UI.

## 5. GPA/CGPA overview and performance visualization

**Purpose:** understand actual credit-weighted results with transparent rules. Use existing summary; no new calculation or historical data model.

Hero region: Actual CGPA, attempted units, graded/ungraded; visible grade scale explanation. Semester comparison: a native table in explicit display order, with readable numeric values, units and counts. A restrained **horizontal 0–5 bar/native meter** may supplement each value, using existing semester GPA only. It is not a temporal line chart. Ungraded has text and no misleading zero bar; actual F/0 has an explicit numeric zero. Give meters labels and keep the complete data table/text available without graphics/JS.

Phone: summary stacks; table stays an explicitly named keyboard-scrollable region with hint/visible scrollbar. A true comparison table may use horizontal scrolling under WCAG's two-dimensional-content exception; the document itself must reflow. Sticky row labels are optional only if tested in Safari/AT/forced colors. Do not turn graph color into a standing/classification scheme or invent “improving 12%,” predicted final degree, rank, grade distribution not supplied by the backend, or semesters ordered by guessed dates.

Keep A=5…F=0, attempted-credit semantics, Decimal precision and global-versus-filtered scope explicit. A filtered course page never silently redefines the actual global CGPA. No control writes grades from this read-only overview.

## 6. GPA Predictor

**Purpose:** explore the selected hypothetical course set, never write actual results. Existing semester filter, optional per-course hypothetical grade fields, selection bound and POST result stay intact.

A permanently visible “Hypothetical · not saved” notice precedes the form; course identity and credit units are legible. Each optional field says “Do not include” when omitted; avoid inventing a saved scenario or automatic inclusion rule. Calculate prediction is the only primary action. Show the result after submission in a distinctly labeled panel, with selected units/quality points and the existing per-semester breakdown. Do not label it final CGPA for all courses.

Phone: normal stacked fields, not a huge modal or horizontal grade matrix. For many courses retain server bounds and the current narrow-by-semester message; no client virtualization masking form submission requirements. Result should be discoverable by heading/link; focus behavior after calculate must be designed and tested without disrupting validation summary focus. Reset predictions remains the existing safe GET route. No local drafts, browser storage or actual-grade mutation.

## 7. Target CGPA Planner

**Purpose:** calculate the required weighted average under explicit assumptions, not promise graduation. Current target/remaining-credit fields and achievable/guaranteed/impossible statuses remain authoritative.

Layout: actual summary, concise input panel, assumptions in a readable adjacent panel on desktop/below on phone, then one result. Target and remaining credits stay exact Decimal input with supported limits. Show the required result to four places; status derives from the unrounded server result. “Mathematically achievable under these assumptions,” “At least this target is guaranteed under the stated non-negative-points model,” and “Required average exceeds the supported scale” are explanatory concepts, not new policy classifications; final copy must preserve existing meaning/tests.

Never silently count remaining units from current ungraded records: the student supplies **all** remaining credits. No slider that rounds away valid inputs, animated progress-to-graduation ring, autosave or fabricated target. Values and assumptions remain available in text/print. An impossible result is useful information with a next step to revise inputs, not a validation error or shaming celebration.

## 8. Registration, login, verification and recovery

**Purpose:** complete one account task with clear context, generic safe responses and accessible errors. Style/composition work does not authorize changing the security protocol or accepted copy.

Login: wordmark, “Sign in,” short username/case-sensitive guidance, labeled username/password, one submit action, adjacent existing reset link, secondary registration link. Keep autofill/password-manager support, allow paste and retain Django/browser autocomplete semantics. Do not add “remember me,” social login, email-as-username, public registration promises, trust-device checkbox, account-existence feedback or per-account limit counters without the corresponding separately approved backend work. A show-password control is optional future progressive UI subject to security/accessibility review, not required for the first redesign.

Registration: existing username/email/two-password fields, visible constraints, generic response. No fictitious university verification claim, unsupported school selector or policy/consent checkbox with no reviewed meaning. Verification/reset request and confirmation: short purpose, server-owned safe next step; never echo token URLs, claim actual email delivery or infer whether an account exists.

Validation keeps the same summary-to-field links; non-field authentication messages remain generic. Decorative branding does not delay form access or add remote images/fonts. B1's minimal template-free failure responses must **not** inherit a rich shell/context processor or look up account state to become visually consistent. Coordinate static tokens/copy with Claude only after independent security approval. A reset/change may have committed despite an error; visual copy must not say “nothing saved” unless the backend establishes it. Auth redesign should follow workspace stabilization and security coordination.

## 9. Account settings

**Purpose:** review the real account and use the existing security actions. Separate “Account identity” (username/email/verified state) and “Password and session” (existing change-password/logout links/forms). Use copy explaining current capabilities without exposing implementation internals that do not help a student.

Do not show inert controls for email editing, profile photos, deletion, MFA, device revocation or stored appearance preferences. These require other scope. A future approved security feature can enter the design through its own branch/review. Keep POST logout and safe password-change navigation; no optimistic “all devices removed” status based only on a UI action. System theme can be explained without pretending it is stored on the account. Avoid including the full username/email in repeated navigation, screenshots, error pages or telemetry unnecessarily.

## 10. First-time onboarding and repeat use

Use existing server context only. No tutorial database flag, modal tour, email campaign, notifications or task-completion telemetry is needed.

1. No semester: one clear Create semester action, brief next steps and assurance that ungraded is distinct from F.
2. Semester but no course: Add course, explain exact units and the optional actual grade.
3. Course but no tasks: optional Add assignment invitation; actual results still remain available independently.
4. Repeat user: remove introductory clutter based on current data, show saved summaries/real deadlines. Do not reintroduce the entire tour on every visit.

Do not render a percentage-complete onboarding bar: “added an assignment” does not establish a universal definition of account completion, and a filtered page is not an account inventory. Persistent dismissal or onboarding analytics is a separate feature decision.

## Forms, confirmation and failures across all screens

Keep full-page creation/edit/deletion for the first release, explicit Save/Cancel and version conflict behavior. The design-system dialog specification is conditional; it does not authorize modal implementation. Labels and helpers remain visible, optional grade remains optional, required indicators are explained and invalid values are not discarded. Native date/number controls remain usable on actual phone browsers, with no float conversion or client-only enforcement. Success, validation, conflict, unauthorized/unavailable and uncertain outcomes are separately designed states, with keyboard focus and safe copy. Never hide a data-loading error behind an empty illustration.

## Accessibility/mobile acceptance for these wireframes

Target applicable WCAG 2.2 AA: native landmarks/headings/labels, meaningful order, no reliance on color, visible focus not obscured, 24×24 CSS px minimum where applicable with the design target of 44×44 and spacing, readable contrast, status announcements and accessible authentication. No cognitive puzzle, paste blocking or gratuitous re-entry. Test at 320px reflow, 200% text and 400% browser zoom, six historical widths plus short landscape windows; record exact browsers/OS/AT. Controls remain usable without hover, JS, animation or persistent browser storage. See the [delivery gates](DELIVERY_AND_ACCEPTANCE.md) for the actual test matrix; this blueprint is not a compliance certificate.
