University Command Center is a Python app for managing university life. It tracks courses, assignments and GPA.

Files:
main.py runs the app.
web_app.py runs the local Streamlit interface.
academic_logic.py contains pure shared grading, validation, summaries, and planning calculations.
It also validates assignments before they enter dashboard pending counts.
grading_policy.py defines immutable letter-grade policies and the explicit legacy five-point default.
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
On Vercel the per-file cap is 4,000,000 bytes (request body limit 4.5 MB); change it only with
web_common.set_upload_cap, never above 10 MiB, and keep the database limit at 10 MiB.
StudyMaterial and MaterialFile keep forced RLS and same-owner foreign keys.
Stored files are never updated: runtime gets no UPDATE on academics_materialfile.
Keep the 50 files / 200 MiB per-student quota under the advisory lock; it sums stored bytes.
Downloads are owner-only attachments with nosniff and a sandbox CSP; never display files inline.
After migrate, re-run configure_runtime before starting the website.
No AI provider calls or file content leaving the server without a new reviewed task.

Display modes (PR #62): System (default), Light and Dark are saved only in the allowlisted ucc_display
cookie; never in the database or browser storage. Dark values come from docs/design/DESIGN_SYSTEM.md
in theme-dark.css (screens only). Keep the dark-mode contrast browser tests passing for new colours.
Student profile (PR #62): academics_studentprofile keeps forced RLS and no DELETE. Matric/student ID collection
is removed from current forms/services/export; a non-editable legacy column is retained for the additive rollout. Its erasure needs a separate reviewed contract release. Never reintroduce collection or backfill IDs into names. Username and email are not editable there; email change needs its own reviewed task.

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
AI providers (stage 3a): only student_web/ai_providers.py talks to Gemini/Grok/Groq, on fixed hosts with
keys in headers only, no redirects, one 60 s deadline and a 1 MiB cap. Never add default model names,
retries, fallbacks, logging of prompts/replies/keys, or tests that reach the network.
Never pass or patch ai_providers._connect outside tests; AI tests use tests/network_guard.NoNetworkMixin.
AI pages (stage 3b): only ai_views.send may call ask(), after a valid consent token, a ledger reservation
and with no transaction open. Look up the token hash before rejecting an expired token. AI text is
inserted with textContent only. ai.js/ai.css load only on AI pages; keep every AI page working without JS.
prune_ai_ledger runs only as the table owner with the website stopped.

Launch milestone (invited trial): the owner approved putting the website online for invited
classmates. Read docs/LAUNCH.md first. One small PR per step; do not skip ahead.
Use only config.settings.web_production behind Caddy on one server; config.settings.production
stays disabled and serve_local_website.py stays local-only. Keep accounts.E105 blocking until a
reviewed real-email backend is approved (step 4). The owner chose open sign-up confirmed by an
emailed code (see "Open sign-up" below). Keep every RLS role, signed-context and runtime-privilege rule; the web process never
gets migration or DBA credentials. Secrets live only in the server's private environment file,
never in the repository, images, logs or chat. gunicorn and whitenoise are approved packages;
ask before adding any other. Use synthetic data in tests; never copy real student data off the server.
Server package (launch step 2): deploy/ holds the only supported server setup. The web container
must keep no published port, a read-only file system, no capabilities and only runtime/auth logins;
migrations run only in the one-off migrate container. Never print or commit deploy/secrets/.
Run tools/test_server_package.py (Docker) before changing deploy/; never use `down -v` on the server.
Invites (launch step 3): store only code digests; codes are made only by the owner's `invites` command
with the migrator login. The auth role keeps exactly SELECT + UPDATE(used_at) on accounts_invitecode.
Open sign-up (owner's choice, replaces invite-only on the public site): the public profiles must keep
UCC_SIGNUP_CODE (check E106). Codes are 6 digits, 1 minute, 5 tries, stored only as an HMAC keyed with
the secret key; a new code retires the old one; replies never reveal whether an account exists. The auth
role keeps exactly SELECT, INSERT, DELETE + UPDATE(attempts, consumed_at) on accounts_signupcode; the
runtime role has no access to either table. The code page must work without JavaScript.
Supabase (owner's choice, replaces the server for the database): supabase/migrations/ is generated by
tools/export_supabase_sql.py and must stay in step with the Django migrations (CI supabase-sql). Never
grant anon/authenticated/service_role anything; the website refuses to start if they can reach a table.
Keep RLS on every table. Never put passwords or the signing key in the numbered files.
Vercel (owner's choice): vercel_app.py must keep forcing config.settings.web_vercel and running
check --deploy (fail level WARNING) before serving. uv.lock must match requirements-django-lock.txt.
Keep .vercelignore sending only the website; Vercel env vars go to Production only, never Preview.
The PDF child may only append a folder that really holds pypdf; never import pypdf in the website.
Real email (step C): ReviewedSMTPBackend is the ONLY approved backend (E105 refuses all others); keep
its fixed hosts, port 587 STARTTLS with verified TLS 1.2+, one recipient per message and generic failure
logs. Email credentials come only from the private env (UCC_EMAIL_ADDRESS, UCC_EMAIL_APP_PASSWORD).
AI limits (launch step E): the public profiles keep UCC_AI_REQUESTS_PER_DAY = 10 and
UCC_AI_SITE_REQUESTS_PER_DAY = 200. Count the site total only through academics_aisiteusage in
the same signed transaction as the ledger row; never give the runtime DELETE, TRUNCATE or
UPDATE(day) on it, and keep its forced RLS. Add the AI key only after these limits are live.
Privacy notice and terms (launch step G): /accounts/privacy/ and /accounts/terms/ must stay true. Any
change to stored data, cookies, outside services or their regions updates privacy.html and
LEGAL_UPDATED in the same PR. The AI pages still never name the provider; the privacy notice must.
Backups (launch step H): read docs/BACKUPS.md. ucc_backup stays read-only (SELECT on BACKUP_TABLES
only, default_transaction_read_only) and never reads sessions, tokens, counters or the signing key.
Backups are always age-encrypted before touching disk; never print or log data, keys or passwords.
The backup workflow never runs on pull requests. Run tools/test_backup_restore.py when changing it,
and add new student tables to BACKUP_TABLES, backup_role.sql and the privacy notice together.
Account deletion (launch step F): only through ucc_security.delete_my_account() in a signed student
transaction; it takes no arguments. Any new table referring to accounts_student must be added to the
function (new migration) and to security_tests.test_account_deletion.OWNED in the same PR.
Groq backup (owner's choice, replaces "no fallback" for this one case): api.groq.com is the third
fixed host; a "/" in the model name is allowed only for Groq (Gemini's model goes in the URL path).
When Gemini is busy (5xx, timeout, network) send() tries Groq automatically for texts up to
ai_providers.CHARACTER_LIMITS["groq"] (free-tier 8K tokens/minute), still as ONE ledger row: record
it first with services.ai.switch_to (answered_by, answered_by_model only); if that fails, send nothing
more. Never switch on 4xx, blocked, invalid or truncated answers; never more than one switch; Groq is
never a Send button. The privacy notice must keep saying texts may go to Groq automatically.
Grade scale (4- or 5-point): each student's choice is academics_studentprofile.grading_scale, changed
only through services.profiles.set_scale. Never convert saved letters; refuse 4-point while any course
is graded E; clear own class bands on a change; 5-point pages stay exactly as before. The 4-point scale
has no built-in class guide. Read docs/STUDENT_WEBSITE.md "Grade scale" first.
Email change (step F, part 2): only through accounts.email_change, after the current password and a
code sent to the NEW address (accounts_signupcode rows with new_email). The auth role may UPDATE only
email (plus the existing password/last_login/email_verified_at/full_name/updated_at) on accounts_student, never
username, id or is_active. Never reveal whether another account uses an address; tell the old address.

Self-reported full names: accounts_student.full_name is optional, editable and independent of username.
Use the existing live-session boundary and auth role; runtime cannot read or update account names.
Name edits may update only full_name/updated_at and must never rotate credentials or sessions.
Never infer a verified legal name from a nickname, username, matric number or an AI response.
