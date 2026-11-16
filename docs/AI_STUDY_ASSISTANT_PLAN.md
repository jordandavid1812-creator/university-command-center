# AI study assistant: plan for review

Status: **plan only, nothing built.** AGENTS.md says AI provider calls and file
content leaving the server need a new reviewed task. This document is that task's
plan. Code starts only after the owner approves it. Revisions 2, 3 and 4 answer
the three reviews; the [review response](#review-response) tables map
each finding to its fix.

## Owner decisions (2026-11-15)

| Topic | Decision |
| --- | --- |
| Providers | **Gemini** (Google) and **Grok** (xAI) |
| Tools | **Summary**, **Quiz**, **Flashcards**, **Ask a question** (one study file each) |
| Consent | **Confirm every time** on a separate page; nothing is sent without that click |
| Choosing a provider | **The student picks for each request**; only providers with a configured key are offered |
| Results | **Saved to the student's account** (new protected table) |
| Usage limit | **50 requests per student per day** |
| PDF | **TXT and PDF**; adds the `pypdf` library (hash-pinned, pip-audited) |

Proposed default the owner can change in settings: at most **500 saved results per
student**. Revision 3 drops the site-wide daily ceiling: the runtime role sees only
the current student's rows under RLS, so it cannot count fairly, and on a local
single-user site the per-student limit already bounds cost.

## What stays the same

- Local, single-user website only. No deployment.
- The CLI and Streamlit apps are unchanged.
- Stored study files are never changed. Results are separate records.
- Only the chosen file's extracted text is sent, plus the typed question for "Ask a
  question". The student's name, username, email, matric number and the file name
  are **not** sent.
- Automated tests and CI never contact Gemini or Grok. A test guard fails any test
  that opens a real network connection.

## User flow and consent

Routes (all owner-only; another student's material gives a 404):

| Route | Method | Effect |
| --- | --- | --- |
| `/materials/<id>/tools/` | GET | Tools page: four tools, the question box, saved results for this file, today's usage |
| `/materials/<id>/tools/confirm/` | POST | Shows the confirm page. **Never sends and never counts.** The question travels in this POST body, never in a URL |
| `/materials/<id>/tools/send/` | POST | The only route that can call a provider. Always redirects |
| `/ai-requests/<id>/` | GET | One request's state: in progress (with a "reload this page" note), failed (with its category), interrupted, a redirect to its result, or "result deleted" if the student deleted it |
| `/ai-results/<id>/` | GET | One saved result |
| `/ai-results/<id>/delete/` | GET/POST | Dedicated delete confirmation (results have no version; see Database) |

The confirm page shows:

- the file, the tool and the question;
- a provider choice (Gemini or Grok; only providers with keys);
- how much text will be sent, counted in characters (Unicode code points after
  cleaning), using only facts extraction actually knows: "All 12,400 characters
  (all 8 pages)" or "The first 60,000 characters (pages 1–40 of 120)". The same
  wording is used when the 300-page stop applies. A partial file is never presented
  as the whole.
- what is sent, what is not sent, and the warnings:
  - "This file's text will be sent over the internet to the company you choose:
    Google (Gemini) or xAI (Grok). Their terms apply. Some plans may keep or use
    what you send to improve their products."
  - "Sent text cannot be recalled. Deleting a result here does not delete it at
    the provider."
  - "Do not send other people's personal information, or material you are not
    allowed to share (for example a lecturer's copyrighted slides)."
- a **Send to Gemini** or **Send to Grok** button (one per configured provider, so
  the button names the provider) and a Cancel link.

**Exactly once:** the confirm page includes a one-time **consent token**. It is
random and signed, bound to the student, material, tool, question and character
count, and expires after 10 minutes. The request row stores only its **SHA-256
hash**, under a unique `(owner, consent_token_hash)` constraint, as the project
already does for authentication tokens. **Send looks the hash up first**: after
checking the signature, but **before** rejecting an expired token, and before
extraction and any limit check. So an old token for a finished request still
redirects to it. If a request already exists, Send redirects
to `/ai-requests/<id>/` without sending: the result if finished, the in-progress page
if the first click is still calling, or the failure page. So a refresh or double
click sends once, even at 50 used. If two Sends with the same token both pass the
lookup at the same moment, the unique constraint stops the second at reservation;
that unique violation is caught and redirects to the existing request, not to an
error page. Every Send response is a redirect (POST-redirect-GET).

**One click is one call to one provider.** There are no automatic retries and no
fallback to the other provider. A failure shows an error page; trying again needs
a new confirm and a new click.

## Request sequence (the order matters)

0. Verify the consent token and look up its hash (see above). An existing request
   redirects; nothing else happens.
1. Read the stored file with the owner-only `read_file` (fingerprint checked) and
   extract text (see Text extraction). A bad PDF stops here: **nothing is sent and
   nothing is counted.**
2. **Reserve** in one short transaction under the per-student
   `pg_advisory_xact_lock`:
   - check today's count (below 50);
   - check the saved-result count (below 500), before any money is spent;
   - check there is no request in flight for this student. A partial unique
     index allows only one `sent` row per owner; a `sent` row older than 2 minutes
     is first changed to `interrupted`.
   - insert the request row (`sent`, with tool, provider, model, characters sent,
     truncation flag and consent token hash).

   Commit.
3. **Call** the provider with **no database transaction open**. The protected
   profiles' 15-second idle-in-transaction timeout would kill one held across the
   call, and a test proves none is.
4. **Save** in a new short transaction: validate the response, then update the
   request **only `WHERE status = 'sent'`**. If no row matches (it was already
   marked `interrupted`), the output is discarded and nothing is saved. Otherwise
   insert the result and set `succeeded`, or set `failed` with an error category.
   Redirect to `/ai-requests/<id>/`.

Outcomes:

| Case | Result |
| --- | --- |
| Server crash or restart after step 2 | The request stays `sent`. It is shown as "interrupted" (and changed to `interrupted` at the next reservation). Never retried. Still counted. |
| The session ends during the call | The live-session capability check refuses step 4, so the output is discarded. The request becomes `interrupted` later. Counted. |
| The save fails after a successful call | A second short transaction sets `failed` with category `save`. If that also fails, the request stays `sent` and becomes `interrupted`. Counted either way. |

## Database (one migration set; same patterns as study materials)

| Table | Holds | Protection |
| --- | --- | --- |
| `academics_studyairequest` (the **ledger**) | owner, tool, provider, model (CHECK: the model-name pattern), status, characters sent, truncated flag, consent token hash (64 hex characters), error category, created and updated time. **No link to the material.** | Forced RLS `student_owner`; `(id, owner)` unique; `(owner, consent_token_hash)` unique; partial unique index on owner where status = `sent`; CHECKs for tool, provider, status and category values and characters sent 1–60,000. Runtime: SELECT, INSERT, UPDATE of `status`, `error_category`, `updated_at` only; **no DELETE**. |
| `academics_studyairesult` | owner, material, request, tool, question, result JSON, shape version, created time | Forced RLS; same-owner FKs `(material_id, owner_id)` → material and `(request_id, owner_id)` → request; **one result per request** (unique `request_id`); CHECKs for tool, question length 0–500 and result size ≤ 64 KiB. Runtime: SELECT, INSERT, DELETE; **no UPDATE**. |

- Fixed value lists (each a CHECK constraint):
  - tool: `summary`, `quiz`, `flashcards`, `answer`
  - provider: `gemini`, `grok`
  - status: `sent`, `succeeded`, `failed`, `interrupted`
  - error category (empty unless `failed`): `network`, `timeout`, `redirect`,
    `http_error`, `too_large`, `invalid_response`, `blocked`, `truncated`, `save`
- The ledger has no material link, so **deleting a material deletes its results
  but never the counted requests**. Today's count cannot be reset. The ledger keeps
  no file name or text.
- Results follow the existing, tested stored-file pattern (migration 0008): the
  database FK is `NO ACTION` and Django's `CASCADE` deletes the results inside the
  material delete. A raw-SQL test proves a material with results cannot be deleted
  around Django, and a service test proves the results go with it.
- Results are never edited, so they have no `record_version`. They use a dedicated
  delete view (confirmation, owner-only, 404 if already gone) instead of the shared
  versioned delete page.
- A student can keep at most 500 results; reservation refuses with a clear message
  at the cap, so nothing is sent.
- **Retention:** a `prune_ai_ledger` management command, run only with the migration
  settings and role (never the runtime), deletes ledger rows older than 365 days
  that have no saved result. The runtime still has no DELETE. With at most 50 rows a
  day, the ledger stays under about 18,300 rows, below the export limit.
  - Forced RLS applies to the migrator too, so with no student context it would see
    no rows. The command therefore runs **one transaction** that sets
    `NO FORCE ROW LEVEL SECURITY` on the ledger, deletes, then restores `FORCE`
    before commit (`ALTER TABLE` is transactional in PostgreSQL, so a failure rolls
    all of it back).
  - It is **offline maintenance**: stop the website first. It prints only a count.
  - It is **not part of stage 1**. It comes with stage 3, when the export uses the
    ledger.
- `require_runtime_role` grows to eight forced-RLS tables. It refuses each stray
  grant: any UPDATE on results, DELETE on the ledger, UPDATE on ledger columns
  other than the three above, and TRUNCATE, REFERENCES or TRIGGER on either. Each
  gets a startup-refusal test.
- The auth role cannot read either table (`accounts/boundary.py`).
- After `migrate`, re-run `configure_runtime` as usual.

## Daily limit

- "Today" is the timestamp range from 00:00 Africa/Lagos to the next 00:00,
  computed in Python and compared with `created_at`. Tests cover 23:59 and 00:00.
- Every request row counts, whatever its status, because a failed or interrupted
  call may still cost money.
- The confirm page shows "N of 50 used today". At 50 it explains why and shows no
  Send button.

## Text extraction

- **TXT:** the stored bytes are already checked UTF-8.
- **PDF:** `pypdf` runs in a **separate child process** with a hard 20-second
  limit, killed on timeout. On Linux it also gets a memory limit; Windows has no
  equivalent, which is recorded as a known limit. How it is started:
  - `sys.executable -I` with a fixed argument list, no shell, and a neutral working
    directory (a fresh temporary directory);
  - a **minimal explicit environment**: none of the website's variables. On
    Windows it gets only `SYSTEMROOT`, which Python needs to start. So the child
    never sees API keys, database passwords or the signing key. A test checks it
    sees no `UCC_`, `PG` or `DJANGO_` variables.
  - file bytes go in through stdin. Output comes back as **UTF-8 bytes written to
    `stdout.buffer`** (surrogates already removed), so non-Latin text works on
    Windows code pages.
  - the parent reads at most 1 MiB of output and kills the child beyond that. It
    decodes strictly as UTF-8, then re-applies the cleaning and the 60,000-character
    cap itself.
  - the output starts with **one metadata line**, a small JSON object
    `{"pages_read": n, "pages_total": n, "truncated": true|false}`, then a newline,
    then the text. The parent validates it strictly (exact keys, non-negative
    integers, pages read ≤ pages total ≤ 100,000) before using any text. The
    confirm page's wording comes from these values.
  - exit codes: 0 text, 3 encrypted, 4 no selectable text, 5 unreadable. Anything
    else, a timeout or bad output counts as unreadable.

  Inside the child:
  - encrypted PDFs are rejected without trying to decrypt (no crypto dependency
    is added);
  - pages are read one at a time, stopping at 300 pages **or as soon as 60,000
    characters are collected**;
  - every exception, including `RecursionError`, becomes "This PDF could not be
    read";
  - the `pypdf` logger is silenced and stderr is discarded, so file fragments never
    reach logs.
- Cleaning (both types): remove null, control (except tab and line breaks) and
  **lone surrogate** characters, then cap at 60,000 characters.
- No text (a scan) gives "This PDF has no selectable text" and nothing is sent.
- Extraction runs on the confirm page (to show the character count) and again on
  Send. Both are bounded by the child-process limit. At most two extractions run at
  once per website process; a third immediately gets a short "Busy, try again in a
  moment" page instead of waiting. The confirm extraction is not counted against
  the daily limit; see Known limits.
- When pinning `pypdf`, check whether that version exposes its own decompression
  output limits, and if so set them low (the main defence on Windows, where there is
  no memory limit).

## Provider calls

- **No SDKs.** A small client uses Python's standard `http.client` over HTTPS with
  certificate verification. It has:
  - **fixed hosts** in code, not settings: `generativelanguage.googleapis.com` and
    `api.x.ai`;
  - **no redirects**: any 3xx is a failure, so a key header can never go to another
    host;
  - an **overall 60-second deadline** for connect, send and read, not per socket
    operation;
  - a **response cap** of 1 MiB, read in chunks and abandoned beyond the cap,
    before any JSON parsing.
- **Keys only in headers:** `x-goog-api-key` for Gemini and
  `Authorization: Bearer` for Grok, never `?key=` in a URL. Keys come only from the
  environment variables `UCC_GEMINI_API_KEY` and `UCC_GROK_API_KEY`. A key that is
  not printable ASCII without spaces is refused at startup, and that provider is
  not offered. Error messages and exceptions are rebuilt without
  headers or URLs, so a key cannot leak through them. Keys are never stored in the
  database, logged, shown or committed.
- Model names are settings (`UCC_GEMINI_MODEL`, `UCC_GROK_MODEL`) checked with
  `re.fullmatch(r"[a-z0-9][a-z0-9.\-]{0,63}", name)`, so a trailing newline is
  refused, because the Gemini model name goes into the URL path. Defaults are confirmed against each provider's current docs at build time.
- **Maximum output** is set per tool: 2,048 tokens for summary and answer, 4,096
  for quiz and flashcards. A response cut off at the limit (finish reason not a
  normal stop) or blocked by the provider's safety filter is a failed request.
  Some models spend output tokens on internal reasoning; at build time, confirm the
  budget is enough for each default model, or set its reasoning budget low.
- The name lookup (DNS) for the two fixed hosts is not covered by the 60-second
  deadline; see Known limits.
- The prompt marks the file text as material to study, not instructions. It asks
  for a fixed JSON shape:

  | Tool | Shape |
  | --- | --- |
  | Summary | 1–10 points |
  | Quiz | 5–10 questions, each with exactly 4 options, a correct index from 0 to 3 and a reason |
  | Flashcards | 5–20 front/back pairs |
  | Answer | an answer plus a "not covered by this file" flag |

- **Validation** rejects extra keys, wrong types, out-of-range indexes, and fields
  or totals over their length limits (the stored result is at most 64 KiB). Each
  result stores a **shape version**, and it is validated again when shown; an
  invalid old row shows "This result can no longer be displayed."
- Output is shown with Django's normal escaping. It is never rendered as HTML or
  Markdown, and links are not clickable. Pages label it "AI-generated; check it
  against your notes."
- Logs record only the provider, the HTTP status class and the error category.
  They never include the key, file text, question or response.

## Secrets on the owner's PC

- Keys live in the existing private file `%LOCALAPPDATA%\UCC\local-web-secrets.json`,
  outside the repository, as `gemini_api_key` and `grok_api_key` (both optional).
- The launcher `%LOCALAPPDATA%\UCC\run_local_web.py`, also outside the repository,
  passes them **only to the website process**. It never passes them to migrate or
  configure steps, and never prints them.
- `tools/check_repository_safety.py` gains **key-pattern scanning** of tracked
  files. It matches the Google API key shape (the `AIza` prefix plus exactly 35
  key characters) and the xAI shape (the `xai-` prefix plus at least 40 key
  characters), so ordinary prose such as this plan does not match. Its tests build
  key-shaped strings at run time, so no tracked file contains one. It never prints
  the match itself.

## Other changes

- **Download my data** adds `ai_results` (tool, provider, question, result,
  time) and `ai_requests` (tool, provider, status, characters sent, time). They
  have limits (500 results; 20,000 requests, kept below that by retention) and the
  same 413 page with no partial file.
- The privacy-safe logging route list gets the new routes.
- Docs: a new `docs/AI_STUDY_ASSISTANT.md`; updates to `STUDY_MATERIALS.md`,
  `STUDENT_WEBSITE.md` and `DATABASE_SECURITY.md`; an AGENTS.md section.
- CSS: 906 bytes of budget remain. New pages reuse existing classes. Any budget
  change is asked for in its PR, never made silently. The new pages are added to
  the dark-mode contrast checks.

## Build stages (each its own PR and review)

1. **Records:** models, migrations, RLS, grants, startup checks, services
   (reserve under the lock, mark status, save result, list, delete), and security
   tests on real PostgreSQL, including the same-token race and the CHECK value
   lists. No provider code and no `prune_ai_ledger` (stage 3).
2. **Text:** `pypdf` added to `requirements-django-lock.txt` with hashes; the
   child-process extractor; tests with synthetic TXT and PDFs (malformed,
   encrypted, empty, oversized, very many pages, slow); pip-audit clean.
3. **Providers and pages:** the HTTP client, Gemini and Grok adapters, prompts and
   validation; the five routes; the export additions; key scanning in the safety
   check. Web tests use a fake provider.
4. **Manual check on the owner's PC** with the owner's own keys and synthetic study
   notes only. Before this, confirm each provider's current data-use terms.

## Tests that must exist

**Records and limit**
- Raw-SQL RLS tests for both tables: no context, cross-student reads and writes,
  and same-owner FKs.
- The 50th request passes and the 51st is refused, including two simultaneous
  reservations on two real connections.
- Deleting a material leaves today's count unchanged and deletes only its results.
- The count boundary at 23:59 and 00:00 Lagos time.
- The 500-result cap is refused at reservation, before any call.
- Two reservations with the same consent token hash on two real connections: one
  row is created, and the second gets the existing request (no error).
- CHECK constraints refuse unknown tool, provider, status, error category and model
  values.
- A late step 4 on a row already marked `interrupted` saves nothing.
- `prune_ai_ledger` (stage 3): asserts the old rows without results are **actually
  gone**, that newer rows and rows with results remain, that forced RLS is back on
  afterwards, and that it refuses to run with runtime settings. A test that only
  checks "no error" is not enough.
- One request in flight per student; a stale `sent` becomes `interrupted` and is
  never retried.
- No transaction is open during the provider call.
- A startup refusal for each stray grant on the two new tables.

**Consent**
- GET never sends. The confirm POST never sends or counts. A missing or invalid
  CSRF token never sends.
- An expired token for an existing request redirects to it. An expired token
  without one, a forged or a reused token never sends.
- A succeeded request whose result was deleted shows "result deleted".
- The confirm page's pages and truncation wording comes from a validated metadata
  line; a malformed line counts as unreadable.
- An expired, forged or reused consent token never sends. A refresh or double POST
  sends once. A duplicate token while the first request is still calling shows the
  in-progress page, even at 50 used. Only the token hash is stored.
- No retry and no fallback provider after a failure.
- A provider without a key is not offered, and a forged provider choice is refused.
- The session expiring during the call discards the output.

**Provider client**
- The fake provider receives exactly the capped text and the question, and nothing
  else (no username, email, matric number or file name).
- Redirects are not followed.
- The key travels in a header only, never in a URL, log line or exception text
  (checked with a synthetic key).
- A slow response hits the 60-second overall deadline, simulated without real
  waiting.
- An oversized response is abandoned at 1 MiB.
- Invalid JSON, extra keys, an out-of-range quiz index, truncated output and safety
  blocks all count as failed requests.
- Results containing HTML or script are shown escaped.

**Other**
- PDF extraction limits, lone surrogates, encrypted files and a silenced logger.
- The child process sees no `UCC_`, `PG` or `DJANGO_` variables.
- A PDF with non-Latin text (Greek and maths symbols) extracts correctly. The
  parent enforces the output byte cap and the character cap. A third simultaneous
  extraction gets the busy page.
- The safety check detects synthetic key-shaped strings without printing them.
- Export limits and 413 for the new sections.
- Dark-mode contrast and the CSS budget for the new pages.
- The network guard and the full CI-equivalent run. No historical test changes are
  expected; any that become necessary are listed and approved first.

## Known limits and risks (for the reviewer)

- Text sent to Google or xAI leaves the owner's control and cannot be recalled.
  The consent page says so.
- AI output can be wrong. Pages label it as AI-generated.
- Prompt injection inside a study file can only make that file's own output wrong.
  Only that text is sent, and the output is shape-checked and escaped.
- PDF text extraction can miss or misorder text (tables, columns, scans).
- On Windows the PDF child process has a time limit but no memory limit. (Resolved
  during stage 2: a Job Object limits memory and forbids other processes; see
  AI_STUDY_ASSISTANT.md.)
- Confirm-page extraction is not counted. It is bounded per call and per process,
  which is acceptable for a local single-user site; any deployment would need a
  separate limit.
- No site-wide daily ceiling (dropped in revision 3). Any deployment with several
  students would need one, counted by a reviewed SECURITY DEFINER function under a
  global lock.
- The ledger is pruned after 365 days only when the owner runs `prune_ai_ledger`.
- Name lookup (DNS) is outside the 60-second deadline, so a broken resolver can
  make a request take longer before it fails.
- Costs depend on the owner's provider plans. The limits bound them but do not
  prevent them.

## Review response

### Revision 2 (first review)

| Finding | Fix in this plan |
| --- | --- |
| H1 Deleting a material resets the limit | The ledger has no material link and no DELETE; only results cascade; test added |
| M2 Repeated POST sends again | One-time consent token, unique per owner, POST-redirect-GET |
| M3 Retries or fallback | "One click is one call to one provider"; tests added |
| M4 Question in a URL | Confirm is a POST to its own URL that never sends |
| M5 Gemini key in the URL | Header-only keys; whitespace and control characters refused |
| M6 `urllib` defaults | `http.client`, fixed hosts, no redirects, overall deadline, 1 MiB cap, model-name pattern |
| M7 pypdf work bounds | Child process with kill, stop at 60,000 characters, encrypted rejected, all exceptions caught, surrogates removed, logger silenced |
| M8 Order and failure states | Request sequence and outcome table; one in flight; interrupted state |
| L9 Constraints | Listed per table, including one result per request and `(id, owner)` |
| L10 Delete page version | Dedicated delete view |
| L11 Caps | 500 results per student; a site-wide ceiling (later dropped in revision 3, see M1) |
| L12 Validation details | Index range, extra keys, totals, output tokens, safety and truncation, shape version |
| L13 Consent wording | Provider-named buttons, what is and isn't sent, cannot recall, copyright warning, characters and truncation recorded |
| L14 Secrets file | Named, outside the repository, launcher passes it only to the website; key-pattern scanning |
| L15 Export | Limits and 413 for both new sections |

### Revision 3 (re-review)

| Finding | Fix in this plan |
| --- | --- |
| M1 Site-wide ceiling cannot be counted under RLS | Dropped for the local single-user site; recorded as a deployment requirement |
| M2 PDF child inherits secrets | Minimal explicit environment, `-I`, fixed arguments, no shell, neutral directory; test |
| M3 Nowhere to redirect for failed or in-flight | `/ai-requests/<id>/` page; token looked up before extraction and limit checks |
| M4 Windows output encoding | UTF-8 bytes on `stdout.buffer`; strict parent decode, re-clean, byte cap, exit codes |
| M5 "of 95,000" unknowable | Wording uses pages read of total pages |
| L6 Cascade description | Matches the stored-file pattern (`NO ACTION` plus Django cascade); raw-SQL test |
| L7 Sequence details | Result cap at reservation; update only `WHERE status = 'sent'`; failed-save fallback |
| L8 Raw token stored | Only the SHA-256 hash is stored |
| L9 Scanner false positives | Minimum lengths after prefixes; test strings built at run time |
| L10 Pattern and key nits | `re.fullmatch`; printable ASCII keys only |
| L11 Third extraction | Immediate busy page |
| L12 Decompression limits | Checked and set when pinning pypdf |
| L13 Reasoning tokens | Budget confirmed per default model at build time |
| L14 Ledger blocks export | `prune_ai_ledger` (migration role only), 365 days |
| L15 DNS outside deadline | Recorded as a known limit |

### Revision 4 (third review)

| Finding | Fix in this plan |
| --- | --- |
| M1 `prune_ai_ledger` deletes nothing under forced RLS | One transaction: `NO FORCE`, delete, `FORCE`; offline; test asserts rows gone and RLS restored; moved to stage 3 |
| L2 Same token, two simultaneous Sends | Unique violation at reservation redirects to the existing request; two-connection test (stage 1) |
| L3 No place for page facts | One validated JSON metadata line before the text |
| L4 Deleted result | "Result deleted" state on the request page |
| L5 Error categories | Exact value lists for tool, provider, status and category; model CHECK (stage 1) |
| L6 Expiry against an existing request | Lookup after signature check, before expiry rejection |
