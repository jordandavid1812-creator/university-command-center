# AI study assistant

The approved design is [AI_STUDY_ASSISTANT_PLAN.md](AI_STUDY_ASSISTANT_PLAN.md)
(revision 4). This page records what is built. It is built in four stages, each
with its own PR and review.

| Stage | Status |
| --- | --- |
| 1. Records: tables, RLS, grants, startup checks, services, security tests | Built (PR #67, #68) |
| 2. Text extraction (TXT, PDF via `pypdf` in a child process) | **Built (this PR)** |
| 3. Provider client (Gemini, Grok), pages, export, `prune_ai_ledger`, key scanning | Not started |
| 4. Manual check on the owner's PC with the owner's keys | Not started |

Nothing calls Gemini or Grok yet. No page uses these records or the extracted text
yet, and no file content leaves the server.

## Stage 1: records

Migrations `0011_study_ai_records` (Django models and constraints) and
`0012_study_ai_security` (same-owner keys, result size limit, forced RLS),
then `0013_study_ai_result_tool` (the result's key to its request also includes the
tool; added after the PR #67 review).

### `academics_studyairequest`: the usage ledger

One row per request sent to a provider. It holds:

- tool, provider and model;
- status and error category;
- characters sent and whether the text was cut short;
- the SHA-256 hash of the consent token (never the token);
- created and updated times.

It has **no link to the study material**, so deleting a material cannot reset the
daily count. It stores no file name, file text, question or response.

- Fixed value lists, each enforced by a CHECK constraint:
  - tool: `summary`, `quiz`, `flashcards`, `answer`
  - provider: `gemini`, `grok`
  - status: `sent`, `succeeded`, `failed`, `interrupted`
  - error category, present exactly when the status is `failed`: `network`,
    `timeout`, `redirect`, `http_error`, `too_large`, `invalid_response`,
    `blocked`, `truncated`, `save`
- Model names must match `^[a-z0-9][a-z0-9.\-]{0,63}$`, so a trailing newline is
  refused.
- Characters sent must be 1 to 60,000. The token hash must be 64 lower-case hex
  characters.
- `(id, owner)` and `(id, owner, tool)` are unique, so results can use a same-owner
  key that also matches the tool.
- `(owner, consent_token_hash)` is unique, so one consent token is used once.
- A partial unique index allows at most one `sent` row per student.
- Runtime grants: SELECT, INSERT, and UPDATE of only `status`, `error_category` and
  `updated_at`. **No DELETE.**

### `academics_studyairesult`: saved outputs

Each row holds owner, material, request, tool, question, the result (JSON) and a
shape version.

- Same-owner keys `(material_id, owner_id)` to the material and
  `(request_id, owner_id, tool)` to the request, so a result always has its
  request's tool, even for raw SQL. There is one result per request.
- The material link follows the stored-file pattern. The database key is
  `NO ACTION`, and Django's `CASCADE` deletes a material's results inside the
  material delete. A raw-SQL delete of a material that has results is refused.
- CHECKs:
  - the tool is in the fixed list;
  - only `answer` has a question, and it is not blank (at most 500 characters);
  - the shape version is at least 1;
  - the result is at most 64 KiB as text.
- Runtime grants: SELECT, INSERT, DELETE. **No UPDATE.**

Both tables have forced RLS with the `student_owner` policy and the signed context
from [DATABASE_SECURITY.md](DATABASE_SECURITY.md). The auth role cannot read
either table.

### Startup checks

`require_runtime_role` now requires forced RLS on **eight** academic tables. It
also refuses a runtime role holding any of these:

- UPDATE on results;
- DELETE on the ledger;
- UPDATE on any ledger column other than `status`, `error_category` and
  `updated_at`;
- TRUNCATE, REFERENCES or TRIGGER on either table.

### Services: `academics.services.ai`

| Method | Behaviour |
| --- | --- |
| `reserve(...)` | See the steps below. Returns `(request, created)` |
| `succeed(...)` | Saves the checked result and marks the request `succeeded` together, but **only while it is still `sent`**. A late answer for an interrupted request raises `AiRequestClosed` and saves nothing. An invalid result raises `InvalidRecord`, saves nothing and leaves the request `sent`, so the caller then records `fail(..., "save")` |
| `fail(...)` | Marks a `sent` request `failed` with a category from the fixed list. Like `succeed`, it raises `RecordNotFound` for a request that is not this student's and `AiRequestClosed` for one no longer in progress |
| `find_request`, `get_request`, `get_result`, `results_for`, `delete_result`, `usage` | Owner-only reads and deletion. Deleting a result keeps its ledger row, which still counts |

`reserve` must be the outermost call; inside another transaction it raises
`RuntimeError`, because a refusal could then undo step 0.

0. In its own short transaction, it changes this student's `sent` requests older
   than two minutes to `interrupted`, so a refusal cannot undo it. This step takes
   no advisory lock; row locks make concurrent markings safe.

Then, in one transaction under a per-student advisory lock:

1. A request already made with the same consent token hash is returned unchanged
   (`created=False`), so a repeated Send never sends twice.
2. Otherwise these checks run in order: no request in flight (`busy`), fewer than
   50 requests today (`daily`), fewer than 500 saved results (`results`).
3. The new row is inserted.

Refusals raise `AiLimitReached` with that reason. If the unique token constraint
ever fires despite the lock, the existing request is returned instead of an error.

"Today" is 00:00 to 00:00 in **Africa/Lagos** (`ai_day_range`). Every ledger row
counts, whatever its status, because a failed or interrupted call may still cost
money.

## Stage 2: text extraction

`student_web.text_extraction.extract_text(file_type, content)` returns an
`ExtractedText` (text, truncated flag, and pages for PDFs or the total characters for
TXT) or raises `ExtractionFailed` with a reason and a message that is safe to show.
`describe()` gives the confirm page's wording, using only facts extraction knows:

- "All 12,400 characters (all 8 pages)"
- "The first 60,000 characters (pages 1–40 of 120)"
- "The first 60,000 of 95,000 characters" (TXT)

Characters are Unicode code points after cleaning. Cleaning turns `\r\n` and `\r`
into `\n` and removes control characters (except tab and line feed), C1 controls and
lone surrogates. Text is capped at **60,000 characters**.

- **TXT:** the stored bytes are already checked UTF-8; they are decoded strictly,
  cleaned and capped. Empty or whitespace-only text is "no selectable text".
- **PDF:** parsed only in a separate child process, `student_web/pdf_text_child.py`.
  It uses only the standard library and `pypdf`, never project or Django code.
  - It is started as `sys.executable -I` with a fixed argument list, no shell, a fresh
    temporary working directory and an **empty environment**. On Windows the only
    variable is `SYSTEMROOT`. So it never sees API keys, database passwords or the
    signing key.
  - Before reading anything, the child limits its own memory to **768 MiB**. On Linux
    it uses `RLIMIT_AS`. On Windows it puts itself into a new **Job Object** (through
    `ctypes`, standard library only) with a per-process memory limit and an
    active-process limit of 1, so it also cannot start any other program. If the limit
    cannot be set, the child stops with "could not be read" **without reading the
    file** (fail closed).
  - The file bytes go in on stdin. `pypdf` messages can contain file fragments,
    so the child points its own stderr (where Python's last-resort log handler and
    warnings print) at the null device and ignores warnings. It changes no logging
    settings, which the logging source audit forbids, and the parent discards stderr
    as well.
  - `pypdf` limits are lowered from its 75 MB defaults to 20 MB per decompressed
    stream, 11 MB declared stream length and 50 MB decoding work per stream.
    `jbig2dec_binary=None`, so `pypdf` never starts an outside program.
  - Encrypted files are refused without supplying any password. Pages are read one
    at a time, stopping at 300 pages or as soon as 60,000 characters are collected.
    Any exception, including `RecursionError` and `MemoryError`, means "could not be
    read".
  - Output is one JSON metadata line (`pages_read`, `pages_total`, `truncated`), a
    newline, then the text as UTF-8 bytes (not the console code page, which matters
    on Windows). Exit codes: 0 text, 3 encrypted, 4 no selectable text,
    5 unreadable.
  - The parent kills the child after **20 seconds** or beyond **1 MiB** of output.
    It checks the metadata strictly (exact keys, integers that are not booleans,
    1 ≤ pages read ≤ min(total, 300), total ≤ 100,000), decodes the text strictly as
    UTF-8, then re-cleans and re-caps it. Anything else means "could not be read".
  - At most **two PDF extractions** run at once per website process. A third gets
    "Busy, try again in a moment" immediately. TXT files need no slot.

`pypdf` 6.21.4 is pinned with hashes in `requirements-django-lock.txt`, generated
with the same `pip-compile` command, and `pip-audit` reports no known
vulnerabilities. Only `pypdf` was added; it has no other dependencies on
Python 3.12. The newer 7.x releases were less than two weeks old when pinned.

## Tests

| Suite | Covers |
| --- | --- |
| `security_tests.test_study_ai_rls` | Raw SQL as the runtime role, with positive controls (the baseline rows are accepted): forced RLS on both tables, no-context access, own-only rows, cross-student writes and links, no ledger DELETE, status-only UPDATE, no result UPDATE, no TRUNCATE, material delete refused around Django, every CHECK value list, a result whose tool differs from its request |
| `tests.test_pdf_child_memory` (no database) | Job Object structures match the Windows 64-bit layout, the right limits are sent in the right order (fake kernel32), any failed step means no limit, the child stops before reading without a limit, a real 1 GiB allocation is refused under the limit. **Windows only** (run on the owner's PC): the child cannot start another process, and a normal PDF still reads with the limit in place |
| `web_tests.test_text_extraction` | TXT cleaning, cap and refusals; PDF text through the real child, Greek and maths text, the 60,000-character and 300-page stops and their wording, scans, encrypted and broken files, a decompression bomb stopped only by the lowered limits, no `pypdf` output on stderr; with stand-in children: no `UCC_`, `PG` or `DJANGO_` variables reach the child, the time limit, the output cap, strict metadata and UTF-8 checks, parent re-cleaning and capping, exit codes, the busy slot limit and oversized input refused before a child starts. The bomb, stderr and environment tests were each shown to fail when their protection is removed |
| `security_tests.test_study_ai_service` | Runs on a fixed clock (noon in Lagos), so no result depends on the real time of day. One request per consent token, the unique-violation fallback, the outermost-call guard, the 51st request refused whatever earlier outcomes, material deletion keeps the count, Lagos midnight boundary (23:59 and 00:00), saved-result cap, one in flight and stale requests interrupted, closing rules, invalid results, value lists, owner isolation and forged identities, result deletion keeps the ledger row, **two real connections** for the same-token race and the race at 49 (the first connection is held after its checks, just before its insert, while the second waits for the lock; locks are counted in this test database only), startup refusal of missing RLS and each stray grant |

No historical tests were changed. `security_tests/test_migrations.py` already
restores the latest academics migration.

## Upgrade order

As before: run `migrate`, then `configure_runtime`, with the migration settings,
then start the website. A database already at stage 1 (0012) needs only `migrate`
for 0013; it adds no grants, but re-running `configure_runtime` is harmless. The website refuses to start student services until both
new tables exist with forced RLS.
