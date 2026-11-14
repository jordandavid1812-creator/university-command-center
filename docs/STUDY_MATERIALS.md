# Study materials — upload, private storage and downloads

Signed-in students can upload PDF or UTF-8 TXT study files for their own courses,
list them, download them and delete them. This is the storage foundation for the
planned AI study assistant. No AI provider is called, no file content leaves the
server, and no public deployment is approved. CLI and Streamlit are unchanged.

## Pages

| Page | Behaviour |
| --- | --- |
| `/materials/` | The student's own materials with course, file name, type and size. **Download** appears only when a file is stored; older details-only records show "File not stored. Upload again to keep a copy." |
| `/materials/new/` | Plain HTML multipart form (works without JavaScript): title, one of the student's own courses, file. |
| `/materials/<id>/download/` | Owner-only download. |
| `/materials/<id>/delete/` | The shared delete page: confirmation, version check, owner-only 404. Deleting a material deletes its stored file. |

All routes are registered in the privacy-safe logging route list
(`accounts/logging.py`). Signed-out visitors are redirected to login; another
student's material answers 404, as elsewhere on the site.

## Upload checks

Checks run in this order, and anything rejected is never stored:

1. **Request size.** Web settings keep uploads in memory only
   (`FILE_UPLOAD_HANDLERS` = memory handler; `FILE_UPLOAD_MAX_MEMORY_SIZE` =
   10 MiB + 64 KiB). Nothing is written to a temporary file on disk. A request
   that announces a larger `Content-Length` gets a 413 page. Django's CSRF check
   reads the body before any view, so an oversized body is still received and
   discarded; it is not stored.
2. **Form** (`student_web.forms.MaterialUploadForm`, a `StrictForm`): title
   (max 200), a course from the student's own list only, no extra fields.
3. **File** (`student_web/upload_validation.py`): simple name with a base name,
   no folders or control characters, and a `.pdf` or `.txt` extension
   (case-insensitive; bare `pdf` or `.pdf` is refused), 1 byte to
   10 MiB, at most 10 MiB + 1 byte read. A PDF must start with `%PDF-`; a TXT
   must be UTF-8 text without unsupported control characters (tabs, line
   breaks and form-feed page breaks are allowed).
4. **File facts** (name, type, size) come only from the checked bytes. The
   browser's content type and size claims are ignored.

The PDF signature check does not prove a PDF is safe. Files are never rendered
inside the site (see Downloads).

## Database design

| Table | Holds | Protection |
| --- | --- | --- |
| `academics_studymaterial` (migrations 0005, 0006) | Title, course, original filename, type, size, version | Same-owner FK `(course_id, owner_id)` → course; forced RLS `student_owner` policy; CHECKs for non-empty title, simple filename, `pdf`/`txt`, size 1 B–10 MiB, version ≥ 1; `(id, owner)` unique (0007) |
| `academics_materialfile` (migrations 0007, 0008) | The bytes and their SHA-256 fingerprint, one row per material | Same-owner FK `(material_id, owner_id)` → material; forced RLS `student_owner` policy; CHECKs for 1 B–10 MiB content and a 64-character lower-case hex fingerprint |

The RLS policies use the same signed `ucc_security.current_student()` context as
the academic tables ([DATABASE_SECURITY.md](DATABASE_SECURITY.md)). Bytes live in a
separate table so listing materials never loads file content.

Runtime grants (`configure_runtime`):

- `academics_studymaterial`: SELECT, INSERT, DELETE; UPDATE only on `course_id`,
  `title`, `record_version`, `updated_at`. File facts, owner, ID and creation
  time cannot be changed.
- `academics_materialfile`: SELECT, INSERT, DELETE and **no UPDATE at all**. A
  stored file is never edited; it is removed together with its material.

`require_runtime_role` now requires forced RLS on all five academic tables. It
also refuses a runtime role holding TRUNCATE, REFERENCES or TRIGGER on any of
them, or any UPDATE on stored files, so a stray later grant is caught at
startup. The authentication role must not be able to read either new table
(`accounts/boundary.py`).

## Services

`academics.services.materials` is a `MaterialRecords` (based on `StudentRecords`):
signed capability, field allowlists, same-owner course checks, optimistic
versions and sanitized errors.

- `update` accepts only `title` and `course_id`; other fields raise `InvalidRecord`.
- `create_with_file` saves the material and its bytes in one transaction (both or
  neither). It takes a per-student `pg_advisory_xact_lock`, checks the quota, sets
  the size from the real bytes and stores a SHA-256 fingerprint.
- `read_file` returns the bytes to the owner only. If the fingerprint no longer
  matches it raises `StoredFileDamaged`; the download page then shows "File
  unavailable" (status 500) and sends no bytes.
- `stored_ids` lists which of the student's materials have a stored file.

## Quota

Per student: **50 stored files and 200 MiB** (`MAX_FILES_PER_STUDENT`,
`MAX_STORED_BYTES_PER_STUDENT` in `academics/services.py`; owner decision).
The count and total use the real stored bytes, not the recorded size.
Details-only records do not count. Deleting a material frees its space. When the
limit is reached the upload form explains it and nothing is saved.

## Downloads

Every download response is an attachment with:

- `Content-Disposition: attachment` and a filename encoded by
  `django.utils.http.content_disposition_header`;
- `Content-Type` `application/pdf` or `text/plain; charset=utf-8`;
- `X-Content-Type-Options: nosniff`;
- `Content-Security-Policy: default-src 'none'; sandbox`;
- never-cache headers from the shared `protected` view decorator.

## Upgrade order for an existing database

Run these with the migration settings and role, in this order, before starting
the new website code:

1. `python server/manage.py migrate` creates the study material tables
   (academics migrations 0005-0008).
2. `python server/manage.py configure_runtime` grants the runtime role access to
   the new tables. Without it, student pages fail with permission errors.
3. Start the website. Its startup check requires forced RLS on all five academic
   tables, so code started before step 1 refuses to serve student pages.

## Tests

| Suite | Covers |
| --- | --- |
| `security_tests.test_study_material_rls` | Raw SQL as the runtime role: forced RLS, no-context access, own-only reads, cross-student inserts/updates/deletes, same-owner course link, fixed file facts |
| `security_tests.test_study_material_service` | Service allowlists, server-owned fields, invalid facts, versions, course deletion protection |
| `security_tests.test_material_file_rls` | Raw SQL on stored files: forced RLS, own-only bytes, no updates, size/fingerprint checks, delete with material |
| `security_tests.test_material_file_service` | Owner-only reads, all-or-nothing saves, per-student count and size quotas |
| `security_tests.test_material_hardening` | Two real connections proving the quota lock, TRUNCATE denial, startup refusal of missing RLS and stray grants, stored-byte quota, damaged files |
| `web_tests.test_material_form`, `test_material_upload`, `test_material_list`, `test_material_download`, `test_material_boundaries` | Form checks, pages, size guard, list status, safe download headers, quota message, exact 10 MiB boundary, damaged-file page |

Run them on real PostgreSQL with the security and web test settings described in
[DATABASE_SECURITY.md](DATABASE_SECURITY.md) and [STUDENT_WEBSITE.md](STUDENT_WEBSITE.md).

### Deliberate historical test changes

- `security_tests/test_migrations.py`: the reverse/reapply test now restores the
  latest academics migration instead of `0004_student_rls`, because later
  migrations would otherwise be left unapplied. Its checks are unchanged.
- `tools/test_frontend_foundation_browser.py`: the mobile menu has nine routes
  after adding Study materials, so the Tab count to Logout is 9 instead of 8.
  Its assertions are unchanged.
- `tests/test_foundation.py` (commit c85f706): the Git-ignore regression test
  now uses `git check-ignore -z` with bytes so it also works on Windows. The
  check is equivalent.

## Known limits

- Simultaneous uploads by one student are serialized by a transaction-scoped
  advisory lock taken before the quota count, proven with two real connections
  in `security_tests.test_material_hardening`. This relies on PostgreSQL's
  default READ COMMITTED isolation (no override is configured). Re-review the
  quota if the lock, its order or the isolation level ever changes.
- Upload settings apply to every multipart request, including signed-out pages:
  bodies up to about 10 MiB are held in memory before CSRF and login checks, and
  an oversized body is read in full before the 413. This is acceptable for the
  local single-user app. Any deployment first needs a front-server request-body
  limit (for example 11 MiB).
- Checking a 10 MiB text file takes under a second of CPU, and model
  validation may send the bytes to PostgreSQL more than once while checking
  constraints. Not measured further; acceptable for local use.
- `materials.create` (details only, no file) remains for internal use and
  tests. It is outside the quota and is not reachable from the website.
- File bytes are stored in PostgreSQL, so database backups grow with stored
  materials (up to 200 MiB per student).
- No malware scanning or PDF sanitization. Files are only ever downloaded as
  attachments, never displayed inside the site.
- Files are removed when their material is deleted. Account deletion is not
  available, as elsewhere on the site.
- The AI study assistant (summaries, quizzes, flashcards, provider calls,
  consent) is not built and needs its own reviewed task.
