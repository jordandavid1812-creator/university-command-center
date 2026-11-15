# Premium design system specification

Proposal only. Direction: **Academic Studio** — precise, warm and quietly confident. Keep the product name University Command Center; this is a visual language, not an institutional rebrand or a new feature set. See the [concept sheet](PREMIUM_DESIGN_DIRECTION.svg) and [audit](FRONTEND_AUDIT.md).

## Design principles

1. **One useful next step.** Each screen has one primary action tied to its real state; dependent actions never outrank their prerequisites.
2. **Make academic truth visible.** Actual, ungraded and hypothetical states have explicit text. A color or chart never invents a result, chronology, ranking or institutional policy.
3. **Clarity over decoration.** Use alignment, type, space and short labels before extra cards, shadows, icons or gradients. Avoid guilt, streaks, confetti and competitive grade colors.
4. **Accessible without a workaround.** Essential controls remain visible on phones, reachable with Tab, readable in dark/forced colors and usable without JS.
5. **Trustworthy feedback.** Distinguish accepted, invalid, conflicting, unavailable and outcome-uncertain states. An HTTP failure does not prove rollback.

## Color architecture

Use primitive swatches only to define semantic tokens; components consume semantic tokens, never hard-coded theme colors. Light and dark are **complete mappings**, not a filter/inversion. All proposed numbers below are hex sRGB.

| Proposed semantic token | Light | Dark | Usage / rule |
| --- | --- | --- | --- |
| `--color-canvas` | `#F7F8F6` | `#101918` | Overall page background |
| `--color-surface` | `#FFFFFF` | `#172321` | Panels, inputs, sidebar |
| `--color-surface-raised` | `#F0F4F0` | `#20312D` | Subtle sections; not an excuse for nested cards everywhere |
| `--color-text` | `#172A2A` | `#F0F5F2` | Body/headings/primary numbers |
| `--color-text-muted` | `#536466` | `#B4C4BC` | Supporting text; remains readable |
| `--color-primary` | `#176B5B` | `#87D4BD` | Primary fill, text links and restrained emphasis |
| `--color-on-primary` | `#FFFFFF` | `#10251D` | Primary-button label/icons |
| `--color-primary-hover` | `#105646` | `#A2E2CE` | Hover/pressed tonal step; keep label contrast |
| `--color-active-bg` | `#E5F3EC` | `#203E32` | Selected navigation; also use text/weight/position |
| `--color-active-text` | `#105646` | `#A2E2CE` | Active nav label |
| `--color-border-subtle` | `#D9E0DC` | `#41584D` | Decorative card separators, not essential control boundaries |
| `--color-border-control` | `#7B8D86` | `#76988A` | Input/secondary-button boundaries; ≥3:1 on the tested surface |
| `--color-focus` | `#925A00` | `#E8B75C` | 3px ring with 3px offset / surface-colored gap; never remove it |
| `--color-success-text/bg` | `#146344` / `#E7F4EC` | `#9DE3BE` / `#173A2B` | Confirmed completion/success, labeled in words |
| `--color-warning-text/bg` | `#7A4B00` / `#FFF3D6` | `#F2D28D` / `#3C301B` | Due today, caution or required attention |
| `--color-error-text/bg` | `#A52839` / `#FFF0F1` | `#FFADB6` / `#3F222A` | Validation/deletion/overdue context, with icon/text |
| `--color-info-text/bg` | `#254C87` / `#EDF3FC` | `#B4D0FF` / `#20314C` | Hypothetical/help/information, never a success claim |

Computed evidence: [24 pairings](COLOR_CONTRAST_EVIDENCE.csv). Standard small text target ≥4.5:1, large text ≥3:1; this design uses ≥4.5 for the tested text pairs regardless of size. Essential control/focus contrast target ≥3:1 against adjacent surfaces. Light primary text/surface is **14.99:1**, muted/canvas **5.83:1**, primary-button label **6.38:1**, control boundary **3.50:1**. Dark equivalents are **14.67:1**, **9.85:1**, **9.34:1** and **5.10:1**. These are opaque pair calculations, not full rendered-state acceptance; check hover, focus, disabled, translucent layers, native controls and selected text in actual browsers. Subtle decorative borders need not meet control contrast but must not become the sole indicator of an interactive boundary.

Reproduction method for the CSV: normalize each sRGB channel to 0–1; linearize with c/12.92 when c≤0.04045, otherwise ((c+0.055)/1.055)^2.4. Relative luminance is 0.2126R + 0.7152G + 0.0722B; contrast is (lighter+0.05)/(darker+0.05). Threshold decisions used unrounded values; the CSV displays two decimal places.

Do not color-code A–F into a moral ranking. Grade text remains explicit; ungraded is neutral; zero/F is a real result, not “missing.” Overdue status is text plus a semantic signal. All charts/meter information is repeated numerically and in an accessible table.

## Typography

Keep the **system UI sans-serif stack** for the first iteration: system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif. Brand wordmark may use installed Georgia/serif to introduce a restrained editorial character; UI headings remain sans. No CDN font, new font package or tracking request. A self-hosted custom font is an optional later owner/license/performance decision, not a prerequisite for premium quality.

| Role / token | Desktop | Phone | Weight / line-height |
| --- | --- | --- | --- |
| Page title / `type-title` | 32px | 28px | 650–700 / 1.2 |
| Section title / `type-section` | 22px | 20px | 650 / 1.3 |
| Record/card title / `type-record` | 16–18px | 16–18px | 600 / 1.4 |
| Body / `type-body` | 16px | 16px | 400–450 / 1.55 |
| Controls/labels/table data / `type-control` | 14–16px | 16px inputs; ≥14px data | 500–600 / 1.45 |
| Supporting metadata / `type-meta` | 13–14px | 13–14px | 400–500 / 1.5 |
| Eyebrow/caption / `type-caption` | 12px | 12px | 600 / 1.4; sentence case preferred |
| Main actual result / `type-result` | 40px | 32px | 650 / 1.15; allow wrap/scale for long values |

Express the eventual scale in rem with fluid limits, not fixed-height text containers. Numeric values use tabular/lining numerals. Right-align comparable numeric columns; left-align names and course codes. Use normal case for long labels; avoid dense all-caps paragraphs. Keep body text to roughly 65–75 characters per line and single-column forms around 36–40rem. Do not use tiny text to make a large data page appear to fit.

Retain current mathematical display contracts initially: two places for GPA/CGPA, four for planner results, exact supported credit precision and unrounded logic for decisions. Trimming redundant trailing credit zeroes is a separately tested presentation change using Decimal/string formatting, never float conversion or numerical rounding.

## Layout and spacing

- Spacing scale: **4, 8, 12, 16, 20, 24, 32, 40, 48, 64px**. Component internals use 12–24, section gaps 24–32 and page gaps 32–48.
- Below **64rem / 1024px**: full-width main column and branded native disclosure navigation; no icon-only rail. Desktop ≥64rem: ~15rem sidebar, minmax(0,1fr) content; main content max around 76rem, centered. Validate the breakpoint with actual text zoom, not only device width.
- Page gutters: 16px at 320–390, 24px tablet, 32–40px desktop. Dashboard may use a 12-column conceptual grid (summary 4, next-work 8); every region stacks in meaningful **DOM order** rather than CSS reordering a confusing keyboard path.
- Sidebar is bounded to the available viewport (`dvh` with fallback), internally scrollable, with no clipped footer/Logout at 500px height or zoom. Avoid sticky mobile header/footer controls initially; they can obscure focused fields and consume scarce space.
- Card radius **12px**, controls **8px**, small inset elements **6px**; circles/pills reserved for compact status, not all surfaces. Borders 1px. Shadow only a faint elevation for truly raised surfaces; no required shadow to perceive a field/control.
- Layers: content → sticky desktop nav if used → dropdown/dialog. Avoid arbitrary z-index escalation; overlays must not mask focus/errors.

## Navigation specification

Keep all eight existing routes and one server-derived active state. Group them by task, with no new backend destination:

- **Study:** Dashboard, Assignments, Courses, Semesters.
- **Results and planning:** GPA & CGPA, GPA Predictor, Target CGPA Planner.
- **Account:** Account settings and POST Logout near the sidebar footer.

On phones show UCC + Menu in a compact brand bar, then the page H1. Use native details/summary as an **inline non-modal disclosure**, styled as navigation; closed means its links are not focusable. Opening does not trap focus or hide the main content, and works without JS. Do not add menu-role keyboard semantics to ordinary navigation. Duplicate responsive nav representations must have only the visible one in the accessibility tree. `aria-current=page` stays on the exact active destination, including edit/create subroutes as appropriate.

Use a small consistent inline SVG set, drawn/maintained locally, 20px, approximately 1.75px stroke. Decorative icons `aria-hidden=true`, non-focusable. Every important action has visible text; no unlabeled mystery toolbar, fake notification bell, avatar uploader or global search field. Numbers 01–08 are not needed for navigation; if retained as decoration, hide them from AT.

## Component contracts

| Component | Anatomy / variants | Behavior, accessibility and data rules |
| --- | --- | --- |
| PageHeader | H1, short purpose, optional one primary action, secondary text link | One H1, useful document title; real primary action changes with available parents, not a fabricated onboarding state |
| Surface/Section | Heading, optional supporting link, content | Section only when heading creates useful navigation; avoid card-inside-card fragmentation |
| AcademicSummary | Dominant Actual CGPA + unit/graded/ungraded supporting values | `None` → Not graded; actual zero remains 0.00; never load estimates here; warnings remain visible |
| AttentionSummary | Real overdue count/link + existing next-up-to-five tasks | Positive count triggers attention style; no overdue row titles without data; completed tasks do not appear as urgent |
| ActionButton | Primary, secondary, text, destructive; optional leading icon | ≥44px recommended height/width, 8px gaps; focus separate from hover; disabled with an explanation; no progress/success until real response |
| FieldGroup | Visible label, field, optional marker, helper, inline errors | Preserve Django IDs/help associations, values and error summary anchors; native input semantics and autofill; error text + border/icon, not color alone |
| FilterBar | Search, supported select(s), Apply filters, clear/reset link | Native GET and existing bounds; preserve safe query params on pagination; no live request on each keypress or new filter values |
| ManagementRecordList | One semantic list/article per course/task, CSS grid on desktop, stacked phone content | One set of action controls/POST form per record; label values on phone; no hidden primary action/duplicate IDs or cached data |
| DataTable | Caption, scoped headers, exact numeric text, scroll region/hint if needed | Performance comparison stays a native table; first-column stickiness only after browser/AT tests; visible scrollbar and keyboard scrolling |
| StatusBadge | Neutral, completed, due today, overdue, hypothetical | Always words; no status from a guessed trend; native dates remain explicit |
| MetricMeter | Visible value plus 0–5 native meter/accessible equivalent | No zero-length meter for ungraded, no chronology implied, no decorative fabricated chart fill |
| Pagination | Previous, page/total, next | Real server counts, bounds and links preserved; no infinite scroll hiding total or breaking keyboard/back |
| StateNotice | Information, confirmed success, warning, error, conflict | Single appropriate announcement region, persistent readable copy; do not double-announce nested live/status roles or auto-dismiss critical content |
| Confirmation | Full-page default; optional later dialog | Label record and consequence; server confirmation, CSRF/version and protected deletion remain mandatory |

### Dialog/modal specification, if separately approved

Keep full-page edit/delete routes for the first redesign. A future modal is progressive enhancement of the existing GET confirmation and POST action, not a new deletion API. Prefer native dialog: visible title/description, explicit Cancel/confirm, Escape cancellation, contained keyboard focus, background inert while open, focus restored to the invoker, long-content scrolling and mobile viewport safety. The fallback navigates to the existing confirmation page. Test no-JS, stale version, protected dependency, foreign UUID, back navigation and forced colors. Do not put large course/predictor forms into tiny modals or introduce JS-only validation/autosave.

## Light/dark policy

First release follows **prefers-color-scheme** with complete semantic mappings and the correct native `color-scheme` value. Print remains light, readable and free of navigation/actions. Dark mode is available through the OS/browser preference; it is not a new database preference.

Do not add localStorage/sessionStorage: `web_tests.test_polish.test_error_focus_script_does_not_store_private_state` currently forbids them explicitly.

**Owner decision (PR #62, UI9 delivered):** a manual choice is approved. Account settings offers System (default), Light and Dark, saved only in this browser in the `ucc_display` cookie (allowlisted values, HttpOnly, SameSite=Lax, one year, Secure follows the session cookie; no database preference, no JavaScript). The dark mapping is the token table above, in `student_web/static/student_web/theme-dark.css`, loaded only on screens (print stays light). Sign-in and error pages follow the same saved choice; only the colour scheme carries over between people on a shared browser, never personal data. The historical light-only browser check now expects System to follow the device; rendered contrast of every visible text element in dark mode is tested in `tools/test_frontend_foundation_browser.py`.

## State and interaction language

- **Empty:** explain what is absent and offer the next valid parent-aware step. “No matches” uses filter reset; “Unavailable” is an error, never zero data.
- **Loading:** retain submitted content/labels; local busy text and aria-busy for full-page POST are sufficient. No fake counters, skeleton grades or artificial loading delay. Restore controls on bfcache; no automatic retries of writes or invented request-status endpoint.
- **Success:** show after the backend confirms its supported outcome; preserve server messages. Do not mark assignment completion optimistically or announce Saved on button click.
- **Validation:** summary focus + per-field links; hidden version errors give a visible reload action without focusing hidden inputs. Keep entered values and the explicit Save action.
- **Conflict (409):** show that another version exists, keep the submitted values visible and make reload/discard intentional. No silent overwrite, autosave or local draft cache.
- **Unavailable/uncertain:** static safe error copy must follow Claude's approved failure contract. It must not claim no writes occurred, preserved login, account existence or guaranteed email delivery. B1 minimal responses stay independent of this rich shell.
- **Motion:** optional color/background transitions of 120–160ms; no parallax, zooming cards, page-route animations, animated grade rises or autoplay. Reduced motion removes transitions; progress remains readable as text. No animation is required to understand state.

## Proposed token/component file architecture (not created now)

Keep the public entry asset/URLs stable for initial migration. Introduce temporary documented aliases for existing token names only where their semantic role matches; migrate hard-coded component colors deliberately and remove aliases after all consumers are checked. Do not enable a partial dark palette while legacy white fills/text remain unmapped. UI1 may deliver the approved light foundation first; UI9 enables dark only after the complete rendered-state audit. Consolidate current variables at the top of site.css with documented layers: primitive → semantic light/dark → layout/type/space → component rules → responsive/print/forced-color overrides. Move pieces into separately cached local files only if measurement/maintainability justifies it; do not add a CSS build system solely to rename tokens.

Continue using the existing template includes for metrics, performance, fields, filters and pagination. Add narrowly scoped includes for page headers, attention summaries, management records and state notices as repetition appears. Pass already-authorized context explicitly; includes never fetch records or mint identities. Keep JS as small named progressive behaviors in the existing local entry point; no framework, browser data store, remote icon/font host or new service dependency is justified.
