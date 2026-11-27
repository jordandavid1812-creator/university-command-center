# Current frontend audit

Baseline: `c19c1a3`, 12 November 2026 (Africa/Lagos). This audit inspects the **Django student website**, not a generic dashboard and not a replacement for the separate local Streamlit app. Proposed fixes are designs only.

## Evidence and limits

- Source inspected: `server/accounts/templates/accounts/{base,form,message}.html`; all student_web page and component templates; `static/student_web/site.css` (**1,021 lines / 18,228 bytes**) and `site.js` (**41 lines / 1,774 bytes**); navigation, views/forms/data, academic query bounds, URLs, accessibility/polish tests and `docs/MILESTONE_4B_REVIEW.md`.
- Fresh Chromium **156.0.8078.79** inspection rendered six **unchanged existing templates/styles/scripts** offline: populated/empty dashboard, courses, assignments, login and invalid course form, at 1440×900, 1024×768, 820×1180, 768×1024, 390×844, 360×800, 320×800 and 1280×600: **48 layout observations**. Separate short-height focus checks used 1280×500. Fixture values were synthetic and explicitly unrelated to student accounts.
- Static rendering used supplied visual contexts and the dummy/non-querying Django database backend; **no view, login, database, ownership or security behavior was exercised or bypassed**. It is not PostgreSQL verification or a full workflow test. No local server or infrastructure was provisioned. The fixtures are not real records and are not published as academic screenshots.
- Reviewed prior synthetic 4B desktop/mobile screenshots and associated smoke script/report. Those provide historical live-flow evidence, not new execution. 4B recorded 69 website tests, six viewport widths and zero axe violations across 19 states, with incomplete clipped-cell contrast checks and no real screen-reader verification. Do not promote that to a fresh WCAG certification.
- The initial default Playwright browser binary was absent; existing `/usr/bin/chromium` worked. Managed browser policy rejected file navigation, so the existing rendered markup was inspected via in-memory `set_content` with inline copies of its unchanged CSS/JS. No application code or managed browser policy was changed. No external requests, live email, cloud service or personal data were used.

## Existing technology and reusable foundation

| Area | Actual implementation | Preserve / reuse |
| --- | --- | --- |
| Rendering | Django 5.2 server templates; `accounts/base.html` shared between auth and academic pages | Progressive server rendering and URL contracts; no SPA rewrite |
| Styling | One local stylesheet, system font, grid/flex, responsive breakpoints, native controls; no remote assets | Small asset footprint, dependency-free delivery, CSS variables and reduced-motion/forced-color/print support |
| JavaScript | POST busy guard, status announcement, back-forward restoration, focus on error summary | All forms work without JS; no localStorage/sessionStorage, grades, credential or identity persistence |
| Navigation | Eight destinations from `student_web/context.py`; sidebar desktop; native details/summary mobile; POST logout | One trusted navigation source, active route state and no-JS disclosure |
| Forms | Shared `components/form_fields.html`, Django label/help/error associations, hidden-field-safe summary, explicit optional labels | Native validation semantics, visible focus, server-owned errors, hidden version preservation |
| Data UI | Shared metrics, semester performance, filter and pagination includes; real numeric text plus native meter | Actual versus hypothetical distinction, ungraded versus F, Decimal display and semantic alternatives |
| Security | Views use verified principal/capability and existing services; CSRF and optimistic locking; protected confirmation pages | UI changes never replace owner filtering, role checks, transactions or server decisions |

## Strengths

The product already explains its mathematics and limitations unusually clearly: weighted actual CGPA, F versus ungraded, hypothetical-only predictions, four-place target decisions and no inferred chronology. Empty states, dependency-aware form guidance, bounded literal search and hidden-version conflict messages are useful and should survive the redesign. Scroll regions are named/focusable, labels remain native, buttons generally meet a 44 px design target, menus/forms remain functional without JS and errors receive a focusable summary. Keep these behaviors rather than removing them for visual minimalism.

## Prioritized findings

Priorities below concern redesign work, not newly discovered authentication vulnerabilities. P1 is a release acceptance issue for its affected UI; P2 is a quality improvement. Distinguish measured findings from design judgments.

| ID / priority | Finding and evidence | Design correction / acceptance |
| --- | --- | --- |
| UI-01 / **P1 accessibility** | Sticky sidebar uses height:100vh, no internal overflow rule (`site.css:60`). At **1280×500**, keyboard Tab reached Logout but its rectangle stayed at y=595.31–639.31, fully outside the 500 px viewport even after the browser scrolled. At 600 px height it was only partly visible. Reproduced on the unchanged template/CSS | Give navigation a scrollable, bounded block-size with a viewport-height fallback and visible focus; ensure every nav item/logout can scroll into view at short heights and text zoom. Treat as a focus-visibility/2.4.11 concern to close, not an acceptable cosmetic compromise |
| UI-02 / **P1 task usability** | Tables have universal min-width:640px (`site.css:439`). At **360 px**, assignment actions begin around **x=536.45** in the fixture; table scrolling is required to complete/edit. Scroll hints and keyboard regions already work | Make management records a single responsive list with visible primary action and metadata; preserve native comparison tables for GPA. Horizontal scrolling itself is **not automatically a WCAG failure** for genuine two-dimensional tables |
| UI-03 / **P1 hierarchy** | Dashboard places greeting/CTAs, four metrics, semester selection and workload before deadlines. At 360×800 the fixture deadline list begins around **y=1621.39**; at 1280×600 around y=891.36. Exact values depend on content | Put a conditional overdue-count link and existing upcoming tasks earlier on mobile; make actual CGPA the clear summary, not one of four equally emphasized cards. No extra queries or invented urgency |
| UI-04 / **P1 onboarding** | No-semester dashboard explains the sequence, but header still presents Add course/Add assignment before their parents exist (`dashboard.html`). Empty edit paths recover with a notice | First-use primary CTA becomes Create first semester; next actions follow available parents. Keep an explicit route back if a direct link reaches an unavailable child form; do not invent an onboarding database flag |
| UI-05 / **P1 security copy dependency** | Website login copy says “Changes are saved only after a successful submission” (`accounts/form.html`). Independent B1 reviews establish that a failed/uncertain response may follow a committed write | Coordinate copy with Claude's accepted outcome contract. A visual refresh must not promise rollback/no save on every error, reveal eligibility or change retry/session behavior. Do not edit security error renderers through a blanket shared-shell rewrite |
| UI-06 / P2 token consistency | Later `:root` overrides radius 16→12 and focus color; later mobile rules override earlier one-column small-phone metrics back to two columns (`site.css:887,963–1006`). Many foreground/background values remain hard-coded | Consolidate semantic tokens and breakpoint ownership; remove audited redundant/legacy rules only after dependency search. No wholesale CSS framework replacement |
| UI-07 / P2 brand/navigation | Dark sidebar + indigo selected pill + numbered flat list is functional but familiar. Numbers are not hidden from AT; mobile hides the branded sidebar and keeps a generic topbar. Eight equal items compete for attention | A light editorial sidebar, grouped existing routes, recognizable mobile wordmark and visible Menu label. Hide purely decorative icons/numbers from AT; keep route names and current state explicit |
| UI-08 / P2 visual hierarchy | Meta/caption/nav text ranges roughly 10–13px, while multiple large numeric/card treatments compete. Repetitive “academic workspace” headings add length | Define a readable scale, one H1 per page, one dominant numeric result, concise descriptions and supporting labels. Small text is not itself a WCAG failure; measure actual readability and contrast |
| UI-09 / P2 work states | Courses/assignments use nearly the same no-record message for first-use and filtered empty results | Distinguish unfiltered empty, no matches, invalid filter, unavailable data and loading using only known server state. Never treat a fetch/error as an empty account |
| UI-10 / P2 scope labeling | Dashboard “Current semester” is actually an explicit GET selection, not a stored active semester (`views.py:54–64`) | Prefer “Selected semester” with a clear Apply/Show button; do not suggest persistent preference or infer latest semester from a label/order |
| UI-11 / P2 auth journey | One generic form wrapper/navigation serves login, registration, recovery and verification. Existing labels/errors are sound; secondary actions lack task-specific placement | Per-screen composition and near-field recovery links, with shared field primitives. Keep generic server messages, paste/autofill and browser password managers; no new auth method or public entry mechanism |
| UI-12 / P2 themes | `color-scheme:light`; no dark semantic palette | Complete system-driven light/dark mapping, including native fields, tables, focus, alerts, meters and print. Do not invert colors mechanically |
| UI-13 / **P1 verification gap** | Historical review explicitly did not test a real screen reader; this static audit does not either | Add actual VoiceOver/Safari or NVDA/Firefox and real mobile browser testing before accessibility acceptance. Automated checks cannot close this gap |

No document-level horizontal overflow was observed in the 48 static viewport cases. That is a limited positive result, not proof that every long string, zoom setting, browser or authenticated workflow works. The short-sidebar focus failure is new evidence and must be reconciled with older viewport-only “no overflow” results; no-overflow is not the same as visible keyboard focus.

## Product/backend inventory: what can honestly be shown

| Available now | Safe design use | Do not imply without new backend work |
| --- | --- | --- |
| Owner-scoped summary gpa/units/graded/ungraded and per-semester rows | Actual overview, accessible numeric cards/bars and complete tables | Historical monthly trends, percentile rank, graduation progress or academic standing |
| Assignment totals pending/completed/overdue; **up to five** upcoming records due today or later | Attention count linking to existing overdue filter and a clearly labeled “Next up to five” preview | Individual overdue records on dashboard when only a count was loaded; push reminders, calendar sync or an all-task agenda |
| Semester UUID/label/display order and GET selector | Selected-semester panel, links to courses in that semester | Stored active semester, label-derived chronology, drag/drop bulk reorder endpoint |
| Paged course/assignment records, literal search, semester/status/deadline sort | Server GET filters, responsive management lists and pagination | Global live search, bulk save/delete, offline record cache, optimistic saves or arbitrary sorting |
| Predictor form/result and planner result/status | Separate hypothetical cards, clear assumptions and read-only output | Predicted final institutional CGPA across omitted courses, saved scenarios or guaranteed graduation |
| Username/email/verified identity; change-password/logout routes | Account identity/security actions and neutral help | Avatar upload, email changes, account deletion, MFA, remembered-device management or theme stored on the account |

## Security and frontend ownership

Workspace template/CSS work can be prepared independently of authentication implementation. Auth error handling, uncertain outcomes, cookies, recovery and generic response text are Claude's security scope. No client owner IDs, global caches, new URLs, extra reads or UI flags may bypass the trusted principal. See the [delivery plan](DELIVERY_AND_ACCEPTANCE.md) for explicit overlap gates.
