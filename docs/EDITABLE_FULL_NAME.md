# Editable full name and student-ID removal

Implementation base: `5b0a01a5a0371886f61206aefb48585caff6f6f8`.
The owner requested a separate registration full name, editing for existing users, and
removal of matric-number collection after the privacy assessment. No dedicated NIN/BVN
fields existed; none are introduced. A name is personal data, not verified identity.

## Behaviour

- Signup adds optional `full_name`, independent of the unchanged username/email/password
  fields. It permits Unicode names and mononyms; no forced Western first/last-name split.
- Existing accounts start with a blank full name. No ID, nickname or username is copied
  into it. The existing optional display-name preference remains separate and unchanged.
- Settings shows the self-reported full name and links to a native HTML editing form.
  Users may correct or clear it. Name changes do not change username, verified email,
  password, session hash/key, ownership or academic results.
- Dashboard prefers the existing display-name preference; otherwise it uses the account
  full name, with the existing username fallback. It adds no academic query or account join.
- Own-data export uses format version 2 because the matric key is removed and the account
  full_name key is added. Historical downloaded version-1 files remain unchanged. Export includes full name. It never exposes another student's account name.
- Names are NFC-normalised, surrounding/repeated whitespace is cleaned, and inputs are
  bounded to 150 characters. Control/surrogate characters are rejected; output is escaped.
  A PostgreSQL CHECK also rejects edge spaces/control characters. No identity verification
  or protection against all visually confusable Unicode names is claimed.
- Editing is owner-scoped through the existing live-session capability. The account row
  is locked and the live identity is revalidated before any write. The auth role gets UPDATE
  of `full_name` only in addition to its established columns; runtime still cannot read or
  write account names. Extra owner/username/email parameters are rejected.
- An expected previous-name field rejects overwriting a currently different value from a
  stale tab. It is a cosmetic value comparison, not a complete change-history/version token:
  an intervening A→B→A sequence is not detected. No broader concurrency guarantee is claimed.

## Matric-number removal and deployment impact

The current profile form/service no longer accepts `matric_number`, Settings does not show
it, and export no longer includes it. A forward migration drops its CHECK and column from
StudentProfile, erasing active stored values. Historical migrations remain intact as history.
The new full-name column is on accounts_student, not a renamed/reused student-ID column.
Dropping matric numbers does not delete profiles, grades, courses or accounts.

No live migration or deployment was performed. Before any separate owner-authorized rollout:

1. Inspect the real migration history and approve the erasure/maintenance plan. Ensure the
   new code, migrations and generated SQL are reviewed together; old code references the
   removed column and cannot safely serve requests after it is dropped.
2. Stop website requests. Apply the two new Django migrations through the authorized migrator,
   or the generated Supabase files `0014_schema.sql` then `0015_security.sql` in their correct
   complete numbered history. Never mix/fake migration histories or edit previous SQL files.
3. Re-provision the reviewed runtime/auth grants and verify RLS, exact allowed columns and
   Data API denial. The name edit fails closed if its new auth UPDATE grant is absent.
4. Deploy/start the reviewed application version and verify registration/verification, name
   editing, owner export, sessions, academic results and the absence of ID collection.

Reversal recreates an empty matric column; it cannot recover erased values. Do not advertise
an application-only rollback after dropping a column. Persistent rollback/recovery requires
an approved plan and compatible schema/code/grants. Restoring an older backup can also restore
IDs and deleted accounts; the separate privacy restoration/reconciliation issue remains open.

Older encrypted backups, manually downloaded copies and provider copies are not erased by this
migration. Their retention and controlled disposal must be verified separately. No real student
records were read, copied or deleted during development. Only synthetic fixtures were used.

## Privacy and remaining work

Privacy notice and LEGAL_UPDATED change together. Full-name collection is optional and editable;
it is not described as anonymous or risk-free. AI text is not automatically de-identified: the
notice and confirmation now distinguish omitted account fields from personal data embedded in
a document/question. No AI provider/age policy, limits, keys or activation were changed here.
The earlier audit's under-18/free-provider, cleanup scheduling, deletion-aware restore, diagnostic
redaction, transfer/processor documentation and legal/controller obligations remain separate work.
Do not treat this field change as legal-compliance certification or approval of GP2a.

## Verification and evidence

Use current hashed dependencies with Python 3.12 and disposable PostgreSQL 17:

```sh
python server/manage.py makemigrations --check --dry-run
python server/manage.py test academics.tests.test_privacy_migrations --settings=config.settings.test
python server/manage.py test web_tests.test_full_name web_tests.test_profile web_tests.test_settings_data --settings=config.settings.web_test
python server/manage.py test security_tests.test_student_profile --settings=config.settings.security_test
python tools/export_supabase_sql.py --check
python tools/test_premium_auth_browser.py -v
python -m unittest discover -v
python tools/check_repository_safety.py
git diff --check
```

Each test settings profile needs its documented dedicated roles/secrets. Do not run standalone
security_tests under web_test; the historical fixtures deliberately use a different capability
adapter. This wrong-profile invocation failed during development and was corrected, without
relaxing isolation or changing the fixtures' database permissions.

New tests cover optional registration, Unicode/invalid names, unchanged verification/session/
credentials, editing/clearing, forged account fields, stale tabs, escaped markup, CSRF, no-JS,
owner-only export, runtime-role denial, direct database validation, missing ID column and
migration erasure/reverse behaviour preserving academic data. Existing matric-display tests
were updated because the owner explicitly requested removal; mathematical, ownership, session
and query-budget assertions were not weakened.

Two browser tests join the existing premium-auth suite: optional signup name vs username,
and responsive/keyboard/native POST for authenticated editing, including 390 px and 1280/1440 px
with 200% text. They run with dummy DB settings and synthetic fixtures. Real workflows use PG17.
Local evidence used Chromium 156.0.8078.79 with Playwright 1.65.0 via /usr/bin/chromium because
the Playwright-managed binary was absent; hosted CI uses the current hashed browser lock.

Synthetic screenshots:

- [Registration, 390 px](design/evidence/editable-full-name/register-390.png)
- [Edit name, 390 px](design/evidence/editable-full-name/full-name-390-text-100.png)
- [Edit name, 1280 px, 200% text](design/evidence/editable-full-name/full-name-1280-text-200.png)

See the implementation PR for exact-head local/hosted results, counts, failures and skips. CI
passing does not authorize merge or applying this destructive migration to a persistent DB.
Independent review and separate owner merge/deployment authorization remain required.

Historical trusted-device rollback coverage retains all existing assertions. While its accounts
schema is at 0002, it adds/removes an unrelated blank full_name fixture column for the current
login model, then restores the full migration graph. This is disposable-test scaffolding only;
production does not guess missing columns or gain a schema-bypass fallback. The fixed-label
logging route allowlist adds only student_web:full-name, preserving its closed vocabulary.
