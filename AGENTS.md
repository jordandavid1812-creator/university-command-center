University Command Center is a Python app for managing university life. It tracks courses, assignments and GPA.

Files:
main.py runs the app.
web_app.py runs the local Streamlit interface.
academic_logic.py contains pure shared grading, validation, summaries, and planning calculations.
It also validates assignments before they enter dashboard pending counts.
web_actions.py validates form edits and returns new records without writing files.
web_data.py safely loads and saves web records, with snapshots, backups, and atomic replacement.
courses.py handles courses.
assignments.py handles assignments.
gpa.py calculates GPA.
gpa_predictor.py tries temporary hypothetical grades.
academic_overview.py displays a read-only summary of actual saved grades.
target_cgpa.py estimates the average needed across remaining credits for a target CGPA.
storage.py saves and loads data in JSON files.

Goal: finish the GPA calculator so it works fully.

Rules:
Keep the code simple. I am a beginner.
Explain every change in plain words.
The web MVP uses Streamlit from requirements.txt. Do not add other application libraries without asking.
Make small changes, one at a time.
Keep the academic overview read-only. Never save data or use predictor grades there.
Use the shared GRADE_POINTS scale in gpa.py and weight GPA by credit units.
Ungraded courses are not F grades. Count attempted units only for valid graded courses.
Preserve semester record order; free-text names do not establish chronological order.
Course codes are unique across the app. In the overview, use the first valid record per code and skip duplicates.
The target CGPA planner shares the overview's validation and deduplication helper.
Keep planning read-only and exclude hypothetical grades. Students supply remaining credits.
Do not infer graduation, repeated-course, or excluded-credit policies.
Keep calculation helpers free of print, input, Streamlit calls, and filesystem writes.
Keep the CLI working without Streamlit installed. Run the full unittest suite with web requirements installed before finishing web changes.
The web app is local and single-user only. Do not deploy it publicly with shared JSON data.
Never use empty fallback data after a web load error. Preserve original files, extra fields, and backups; reject stale saves.
Use synthetic data and temporary directories for tests and screenshots. Do not commit student data or backups.
Milestone 1 uses Python 3.12. Install runtime packages from requirements-lock.txt with --require-hashes.
Preserve the original 91 tests. Run the complete suite with Streamlit installed and run pip-audit before finishing.
Credit calculations accept 0.0001–1000000 and at most four decimal places. Targets accept 0–5 with four decimal places. Do not silently round unsupported inputs.
Use checked_credits, checked_grade, checked_target, and validate_assignments instead of duplicating validation. Keep the documented legacy zero-credit warning compatible.
Do not count invalid or incomplete assignments as pending work. Warn and preserve their records.
Run tools/check_repository_safety.py before committing. Never print student records while auditing history.
Do not rewrite history, delete personal records, merge, deploy, or start Milestone 2 as part of foundation work.

Django foundation: server/ is independent of the CLI/Streamlit entry points.
See docs/DATABASE_FOUNDATION.md before changing its schema or settings.
Use Python 3.12, the hashed requirements-django-lock.txt, and real PostgreSQL 17
for Django tests. Never substitute SQLite for database constraint verification.
Preserve the composite same-owner foreign keys and exact numeric credit checks.
Owner integrity is not complete owner isolation; Milestone 2B needs separate review.
Do not expose account routes, deploy, or migrate JSON as part of Milestone 2A.

Milestone 2B: use academics.services with a trusted capability for academic CRUD.
Read docs/DATABASE_SECURITY.md first. Never mint identities from client owner IDs.
Never replace signed transaction/backend context with an unsigned PostgreSQL GUC.
Runtime must have no schema ownership, bypass rights, role memberships or account/key access.
Run legacy, original 2A database and restricted-role security suites separately.
Preserve all original tests. Never run application requests with the migration connection.

Milestone 3: read docs/AUTHENTICATION.md before changing authentication.
Web default DB credentials are academic runtime; accounts/sessions use the separate auth role.
Never put migration/DBA credentials in web settings or grant runtime account/key access.
A Student/is_authenticated flag alone must never mint a web capability.
Use principal_for_request plus the live session/password-bound factory.
ALLOW_INTERNAL_TEST_PRINCIPALS is only for historical 2B non-web fixtures.
Run auth_tests separately on real PostgreSQL; preserve all 192 historical tests unchanged.
Use only console/private local or in-memory test email, synthetic identities and hashed tokens.
Do not deploy, add social login, migrate JSON or start the full dashboard without a new task.

Milestone 4A: read docs/STUDENT_WEBSITE.md before changing website pages.
Use web_development/web_test profiles; old auth/foundation profiles stay compatible.
All writes use existing services; all new reads need signed context and owner filters.
Preserve Decimal credits and semester UUID grouping; never merge semesters by labels.
No calculation formulas were changed. Do not convert database credits through float.
Do not truncate analyses into misleading partial GPAs or persist hypothetical grades.
Keep the 255 historical tests unchanged and run web_tests on real PostgreSQL.
Keep mobile table regions keyboard-scrollable and all forms functional without JavaScript.
Do not deploy, import JSON, add account deletion/email changes or start 4B without a new task.

Milestone 4B: preserve bounded literal search and its owner/semester/status filters.
Read a capability's student_id only inside validated student_transaction; never
replace its live-session/signature checks with direct trust or cache identities.
Keep error summaries keyboard-focusable and linked only to visible controls.
Preserve all historical tests (307 from 4A plus 13 from PR #24) and polish
regressions; run real PostgreSQL.
The opt-in web_tests.benchmark is not part of ordinary discovery/CI latency checks.
Read docs/MILESTONE_4B_REVIEW.md for accessibility/performance evidence and limits.
No deployment or Milestone 5 without a new task.

Study materials (PR #60): read docs/STUDY_MATERIALS.md before changing uploads or file storage.
Uploads stay in memory, 10 MiB per file; never add a disk-spilling upload handler.
StudyMaterial and MaterialFile keep forced RLS and same-owner foreign keys.
Stored files are never updated: runtime gets no UPDATE on academics_materialfile.
Keep the 50 files / 200 MiB per-student quota under the advisory lock; it sums stored bytes.
Downloads are owner-only attachments with nosniff and a sandbox CSP; never display files inline.
After migrate, re-run configure_runtime before starting the website.
No AI provider calls or file content leaving the server without a new reviewed task.

Display modes (PR #62): System (default), Light and Dark are saved only in the allowlisted ucc_display
cookie; never in the database or browser storage. Dark values come from docs/design/DESIGN_SYSTEM.md
in theme-dark.css (screens only). Keep the dark-mode contrast browser tests passing for new colours.
Student profile (PR #62): academics_studentprofile keeps forced RLS, no DELETE and a masked matric
number. Username and email are not editable there; email change needs its own reviewed task.

Download my data (PR #65): the export reads only through academics.queries.export_records
in one signed student_transaction. It never includes file contents or fingerprints, keeps
credit units as exact decimal strings, and returns 413 with no partial file when too large.

AI study assistant: read docs/AI_STUDY_ASSISTANT_PLAN.md (approved, revision 4) and
docs/AI_STUDY_ASSISTANT.md first. Build one stage per PR. The ledger (studyairequest) has no
material link and no runtime DELETE; results are never updated. Keep forced RLS on all eight
academic tables. Never call a provider from tests or CI, never store or log keys, file text,
questions or responses outside the saved result, and never send without the confirm-page POST.
PDF text (AI stage 2): pypdf runs only in student_web/pdf_text_child.py, a child started with -I,
an empty environment, a time limit, an output cap and lowered pypdf limits (jbig2dec_binary=None).
Never import pypdf in the website process or pass the website's environment to the child.
The child must limit its own memory (RLIMIT_AS; Windows Job Object) before reading and stop if it cannot.
AI providers (stage 3a): only student_web/ai_providers.py talks to Gemini/Grok, on fixed hosts with
keys in headers only, no redirects, one 60 s deadline and a 1 MiB cap. Never add default model names,
retries, fallbacks, logging of prompts/replies/keys, or tests that reach the network.
Never pass or patch ai_providers._connect outside tests; AI tests use tests/network_guard.NoNetworkMixin.
AI pages (stage 3b): only ai_views.send may call ask(), after a valid consent token, a ledger reservation
and with no transaction open. Look up the token hash before rejecting an expired token. AI text is
inserted with textContent only. ai.js/ai.css load only on AI pages; keep every AI page working without JS.
prune_ai_ledger runs only as the table owner with the website stopped.
