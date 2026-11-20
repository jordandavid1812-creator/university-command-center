# Editable full name and staged student-ID removal

Original implementation base: `5b0a01a5a0371886f61206aefb48585caff6f6f8`.
Current integration baseline: `4fd614206ef3eb1243d00bf6f98c59b66404be7e` (merged
PR #116 restores the reviewed dependency stack). Another actor merged #116 and
closed the equivalent draft repair #115; this task performed neither action.
Passing candidate CI is not a substitute for the master push run or final PR-head CI.
The owner requested a separate registration full name, editing for existing users and removal
of matric-number collection. No dedicated NIN/BVN fields existed; none are introduced.
A full name is optional, self-reported personal data, not verified identity.

## Behaviour

- Signup adds optional `full_name`, independently of username/email/password. Unicode names
  and mononyms are supported. Existing accounts start blank; no ID/nickname/username backfill.
- Settings offers a native HTML editing form; students can correct or clear their name.
  Password, verified email, username, session key/hash, ownership and results are unchanged.
- The separate optional display-name preference remains unchanged. Dashboard prefers it,
  otherwise account full name, then the existing username fallback. No new dashboard query.
- Export format version 2 adds `account.full_name` and omits `profile.matric_number`.
  Old downloaded version-1 files are not changed. Export remains owner-only.
- Names are NFC-normalised, whitespace collapsed, limited to 150 characters, and escaped.
  Control/surrogate characters are rejected; a database CHECK also rejects edge spaces and
  control characters. Not all Unicode formatting/confusable characters are rejected: some
  joining marks are needed in legitimate names. This is not name/identity verification.
- Identity is validated before its UUID is read and revalidated under the account row lock.
  Auth gains only UPDATE(full_name) in addition to its established columns. Runtime still
  cannot read/write account names. Unknown account/owner fields are rejected.
- The previous-name comparison rejects a currently different value in stale tabs. It is a
  cosmetic value guard, not a version-history token: A→B→A changes remain undetected.

## Two-step removal: erase values now, drop the empty column later (owner decision)

The current form/service rejects matric-number input, Settings does not display it, and
exports omit it. **`academics.0027_erase_legacy_matric_numbers` erases every saved value**
(sets it to `''`) when the migration is applied. The now-empty column stays until a later
reviewed release drops it, so old application code keeps working during the switch. Older
encrypted backups can still contain IDs until they expire (up to 30 days).

- `accounts.0007` adds `full_name` with persistent database default `''` (`db_default`) as
  well as the Python default. Old signup inserts that omit the column continue to work.
- `academics.0026_legacy_matric_database_default` retains the legacy column and CHECK,
  adds persistent blank database default, and marks the model field non-editable. It does
  not collect IDs through any current form/service. Existing grants needed by old code
  remain during the overlap; no new role gains access to existing private IDs.
- `academics.0027_erase_legacy_matric_numbers` sets every stored ID to `''`. Forced RLS
  also binds the table owner on plain PostgreSQL, so the migration lifts the forcing only
  inside its own transaction and restores it before commit (the migration test checks it).
  It cannot be undone: reversing it leaves the values empty. Old code that writes an ID
  between the migration and the new deployment could store one again; the later contract
  release removes the column entirely.
- `0014_schema.sql` and `0015_security.sql` are generated from those migrations/grants.
  Previously published DROP-column SQL from the earlier review head is superseded. Neither
  version was applied by this task. Inspect real migration history before any future action;
  if anyone has already applied the old unmerged variant, stop for a separately reviewed
  reconciliation. Never overwrite/fake a persistent migration history.

The proposed sequence, requiring separate deployment authorization:

1. Review the real migration history, backups, DDL-lock exposure and operational recovery plan.
2. Apply the additive schema through the authorized migrator, then provision/verify the
   reviewed auth/runtime grants. On Supabase apply generated numbered files in order; do not
   mix migration histories. Do this **before** deploying code that selects `full_name`.
3. Old code can still read profiles and insert accounts against the expanded schema. Deploy
   the new code, verify registration/verification, own-name editing/export and isolation,
   then retire old instances/deployment URLs. No Vercel maintenance switch is assumed.
4. Review a separate contract migration that removes the legacy CHECK/column and its grants
   only after old code cannot serve requests. That later destructive release needs its own
   tests, current-master CI and owner authorization. It is not included or approved here.

This avoids the previously proposed incompatible old-code/new-schema window. It does not
promise zero downtime: DDL can take locks; provisioning failures can still deny operations.
The name editor returns the existing safe failure response if its UPDATE grant is absent.
Before the contract stage, application rollback can use old code against the expanded schema;
leave the additive columns/defaults in place. Reversing the name migration would lose names
and break new code, so it is not an application rollback procedure.

After any future column drop, rollback cannot restore erased IDs. Restoring old backups into
an incompatible new schema can fail and roll back the restore transaction; it is not a way
to bypass schema compatibility. Create an isolated target at the backup's recorded schema
first (for a pre-change backup, accounts 0006 / academics 0025, Supabase files through 0013),
restore there, then apply the reviewed forward migration sequence. Verify all data, grants,
RLS and schema before any separate owner-approved cutover. Do not run an old backup against
an arbitrary latest schema or reverse a persistent database to accommodate it.
Older backups/downloads/provider copies can retain IDs and deleted accounts: their retention,
disposal and deletion-aware restore reconciliation remain separate unresolved privacy work.
No live database or real student records were accessed, migrated or erased.

## Review corrections and owner authorization

The reviewer requested changes at `7be90fd58e96c7c70c08bb8d87f2adb779fdd74e`:

| Finding | Disposition |
| --- | --- |
| Current-master CI | The old green run covered e4042dd. Merged PR #116 restores the baseline at 4fd6142; equivalent draft repair #115 was closed by another actor. Verify master push run 44688693905 and fresh final PR #114 integration CI; do not substitute historical candidate results. |
| Nine existing-test changes | Owner explicitly answered "Approve the listed test changes for re-review" in this conversation on 20 November 2026. This is not merge/deploy approval. The follow-up commit lists every file; earlier commits are preserved rather than rewritten. |
| Settings text | Remove the stale claim that a matric number is partly hidden. |
| Rollout incompatibility | Persistent blank DB defaults, retained legacy column, additive-first rollout, deferred contract. |
| Restore compatibility | Match the backup's schema in an isolated target, restore, then migrate forward. No direct incompatible-schema restore promise. |

Owner-approved existing-test files (scope: name/matric/privacy presentation and the necessary
historical-schema fixture only; academic/security assertions are retained):

- `server/auth_tests/test_trusted_devices.py`: while the disposable schema is at accounts
  0002, temporarily add/remove a blank full_name fixture column so the current login model
  can exercise the historical rollback assertions; restore all real migration leaves.
- `server/security_tests/test_student_profile.py`: check private display-name isolation in
  place of removed ID presentation; preserve owner/version/grant/RLS checks.
- `server/web_tests/test_ai_pages.py`: use actual account full-name sentinel; it is not
  automatically attached to provider requests.
- `server/web_tests/test_auth_presentation.py`: registration field set includes optional name.
- `server/web_tests/test_legal_pages.py`: revised notice date.
- `server/web_tests/test_profile.py`: no matric collection/display; old posted ID is rejected.
- `server/web_tests/test_results_pdf.py`: no removed ID label; retain existing PDF assertions.
- `server/web_tests/test_settings_data.py`: export version 2, own name, omitted matric key.

The historical test-column accommodation is test scaffolding, not a production missing-column
fallback. No credential, isolation, academic, query-budget or rate-limit assertion is relaxed.

## Tests and remaining privacy work

Use the hashed dependencies with Python 3.12 and real disposable PostgreSQL 17; see the PR
for exact local/hosted versions, counts, skips and current-source limitations:

```sh
python server/manage.py makemigrations --check --dry-run
python server/manage.py test accounts academics --settings=config.settings.test
python server/manage.py test web_tests --settings=config.settings.web_test
python server/manage.py test security_tests --settings=config.settings.security_test
python server/manage.py test auth_tests --settings=config.settings.auth_test
python tools/export_supabase_sql.py --check
python tools/test_premium_auth_browser.py -v
python -m unittest discover -v
python tools/check_repository_safety.py
git diff --check
```

The migration rehearsal tests old ORM signup/profile access after expansion, new account/profile
creation, actual DB defaults (including a rolled-back missing-default negative control), preserved legacy IDs and academic data, and disposable reversal.
The name suite covers optional signup, bounds/escaping, session/verification preservation,
CSRF/no-JS, stale tabs, missing account at lock time, owner-only export, runtime denial,
missing UPDATE grant and rejection of new ID collection. Each settings profile needs its
own documented roles/secrets; never relax fixture database permissions to fix a wrong-profile run.

Two new tests join premium-auth browser coverage for registration and editing at 390 px and
1280/1440 px with 200% text, native POST and visible focus. Historical local evidence used
Chromium 156.0.8078.79 / Playwright 1.65.0; hosted CI uses the current hashed browser lock.

Synthetic screenshots:

- [Registration, 390 px](design/evidence/editable-full-name/register-390.png)
- [Edit name, 390 px](design/evidence/editable-full-name/full-name-390-text-100.png)
- [Edit name, 1280 px, 200% text](design/evidence/editable-full-name/full-name-1280-text-200.png)

Privacy notice and LEGAL_UPDATED change together. AI document/question text is not automatically
redacted; embedded personal data can be sent even though account fields are not separately
attached. Provider/age policy, limits and keys are unchanged. Under-18/free-provider policy,
cleanup scheduling, restore reconciliation, diagnostic redaction, processor/transfer paperwork
and legal/controller obligations remain separate work. No legal-compliance certification,
GP2a approval, production migration, deployment or merge is implied by tests or this document.
