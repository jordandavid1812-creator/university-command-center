# AI study assistant

The approved design is [AI_STUDY_ASSISTANT_PLAN.md](AI_STUDY_ASSISTANT_PLAN.md)
(revision 4). This page records what is built. It is built in four stages, each
with its own PR and review.

| Stage | Status |
| --- | --- |
| 1. Records: tables, RLS, grants, startup checks, services, security tests | **Built (this PR)** |
| 2. Text extraction (TXT, PDF via `pypdf` in a child process) | Not started |
| 3. Provider client (Gemini, Grok), pages, export, `prune_ai_ledger`, key scanning | Not started |
| 4. Manual check on the owner's PC with the owner's keys | Not started |

Nothing calls Gemini or Grok yet. No page uses these records yet, and no file
content leaves the server.

## Stage 1: records

Migrations `0011_study_ai_records` (Django models and constraints) and
`0012_study_ai_security` (same-owner keys, result size limit, forced RLS).

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
- `(id, owner)` is unique, so results can use a same-owner key.
- `(owner, consent_token_hash)` is unique, so one consent token is used once.
- A partial unique index allows at most one `sent` row per student.
- Runtime grants: SELECT, INSERT, and UPDATE of only `status`, `error_category` and
  `updated_at`. **No DELETE.**

### `academics_studyairesult`: saved outputs

Each row holds owner, material, request, tool, question, the result (JSON) and a
shape version.

- Same-owner keys `(material_id, owner_id)` to the material and
  `(request_id, owner_id)` to the request. There is one result per request.
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
| `fail(...)` | Marks a `sent` request `failed` with a category from the fixed list |
| `find_request`, `get_request`, `get_result`, `results_for`, `delete_result`, `usage` | Owner-only reads and deletion. Deleting a result keeps its ledger row, which still counts |

`reserve` first changes this student's `sent` requests older than two minutes to
`interrupted`, in its own short transaction, so a refusal cannot undo it. Then,
in one transaction under a per-student advisory lock:

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

## Tests

| Suite | Covers |
| --- | --- |
| `security_tests.test_study_ai_rls` | Raw SQL as the runtime role: forced RLS on both tables, no-context access, own-only rows, cross-student writes and links, no ledger DELETE, status-only UPDATE, no result UPDATE, no TRUNCATE, material delete refused around Django, every CHECK value list |
| `security_tests.test_study_ai_service` | One request per consent token, the 51st request refused whatever earlier outcomes, material deletion keeps the count, Lagos midnight boundary (23:59 and 00:00), saved-result cap, one in flight and stale requests interrupted, closing rules, invalid results, value lists, owner isolation and forged identities, result deletion keeps the ledger row, **two real connections** for the same-token race and the race at 49, startup refusal of missing RLS and each stray grant |

No historical tests were changed. `security_tests/test_migrations.py` already
restores the latest academics migration.

## Upgrade order

As before: run `migrate`, then `configure_runtime`, with the migration settings,
then start the website. The website refuses to start student services until both
new tables exist with forced RLS.
