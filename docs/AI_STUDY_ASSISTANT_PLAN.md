# AI study assistant: plan for review

Status: **plan only, nothing built.** AGENTS.md says AI provider calls and file
content leaving the server need a new reviewed task. This document is that task's
plan. Code starts only after the owner approves it. Revision 2 answers the first
review; the [review response](#review-response-revision-2) table maps each
finding to its fix.

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

Proposed defaults the owner can change in settings: at most **500 saved results
per student** and a **site-wide ceiling of 200 requests per day**.

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
| `/materials/<id>/tools/send/` | POST | The only route that can call a provider |
| `/ai-results/<id>/` | GET | One saved result |
| `/ai-results/<id>/delete/` | GET/POST | Dedicated delete confirmation (results have no version; see Database) |

The confirm page shows:

- the file, the tool and the question;
- a provider choice (Gemini or Grok; only providers with keys);
- how much text will be sent, counted in characters (Unicode code points after
  cleaning): "All 12,400 characters" or "The first 60,000 of 95,000 characters".
  A partial file is never presented as the whole.
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
count, and expires after 10 minutes. The Send POST stores the token in the
request row under a unique `(owner, consent_token)` constraint. A refresh or
double click therefore finds the existing request and redirects to its result or
error page instead of sending again. Every Send response is a redirect
(POST-redirect-GET), so refreshing the result page never posts.

**One click is one call to one provider.** There are no automatic retries and no
fallback to the other provider. A failure shows an error page; trying again needs
a new confirm and a new click.

## Request sequence (the order matters)

1. Read the stored file with the owner-only `read_file` (fingerprint checked) and
   extract text (see Text extraction). A bad PDF stops here: **nothing is sent and
   nothing is counted.**
2. **Reserve** in one short transaction under the per-student
   `pg_advisory_xact_lock`:
   - check today's count (below 50);
   - check the site-wide ceiling;
   - check there is no request in flight for this student. A partial unique
     index allows only one `sent` row per owner; a `sent` row older than 2 minutes
     is first changed to `interrupted`.
   - insert the request row (`sent`, with tool, provider, model, characters sent
     and truncation flag, consent token).

   Commit.
3. **Call** the provider with **no database transaction open**. The protected
   profiles' 15-second idle-in-transaction timeout would kill one held across the
   call, and a test proves none is.
4. **Save** in a new short transaction: validate the response, insert the result,
   set the request to `succeeded`; or set it to `failed` with an error category.
   Redirect.

Outcomes:

| Case | Result |
| --- | --- |
| Server crash or restart after step 2 | The request stays `sent`. It is shown as "interrupted" (and changed to `interrupted` at the next reservation). Never retried. Still counted. |
| The session ends during the call | The live-session capability check refuses step 4, so the output is discarded. The request becomes `interrupted` later. Counted. |
| The save fails after a successful call | The request is `failed` with category `save`. Counted. |

## Database (one migration set; same patterns as study materials)

| Table | Holds | Protection |
| --- | --- | --- |
| `academics_studyairequest` (the **ledger**) | owner, tool, provider, model, status, characters sent, truncated flag, consent token, error category, created and updated time. **No link to the material.** | Forced RLS `student_owner`; `(id, owner)` unique; `(owner, consent_token)` unique; partial unique index on owner where status = `sent`; CHECKs for tool, provider, status and category values and characters sent 1–60,000. Runtime: SELECT, INSERT, UPDATE of `status`, `error_category`, `updated_at` only; **no DELETE**. |
| `academics_studyairesult` | owner, material, request, tool, question, result JSON, shape version, created time | Forced RLS; same-owner FKs `(material_id, owner_id)` → material with database-level `ON DELETE CASCADE` (as for stored files), and `(request_id, owner_id)` → request; **one result per request** (unique `request_id`); CHECKs for tool, question length 0–500 and result size ≤ 64 KiB. Runtime: SELECT, INSERT, DELETE; **no UPDATE**. |

- The ledger has no material link, so **deleting a material deletes its results
  but never the counted requests**. Today's count cannot be reset. The ledger keeps
  no file name or text.
- Results are never edited, so they have no `record_version`. They use a dedicated
  delete view (confirmation, owner-only, 404 if already gone) instead of the shared
  versioned delete page.
- A student can keep at most 500 results; Send is refused with a clear message at
  the cap.
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
- The confirm page shows "N of 50 used today". At 50, or at the site-wide ceiling,
  it explains why and shows no Send button.

## Text extraction

- **TXT:** the stored bytes are already checked UTF-8.
- **PDF:** `pypdf` runs in a **separate child process** (`python -I`, file bytes
  through stdin, text through stdout), with a hard 20-second limit. The child is
  killed on timeout. On Linux it also gets a memory limit; Windows has no
  equivalent, which is recorded as a known limit. Inside the child:
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
  Send. Both are bounded by the child-process limit, and at most two extractions
  run at once per website process. The confirm extraction is not counted against
  the daily limit; see Known limits.

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
  environment variables `UCC_GEMINI_API_KEY` and `UCC_GROK_API_KEY`. A key
  containing whitespace or control characters is refused at startup, and that
  provider is not offered. Error messages and exceptions are rebuilt without
  headers or URLs, so a key cannot leak through them. Keys are never stored in the
  database, logged, shown or committed.
- Model names are settings (`UCC_GEMINI_MODEL`, `UCC_GROK_MODEL`) checked against
  `^[a-z0-9][a-z0-9.\-]{0,63}$`, because the Gemini model name goes into the URL
  path. Defaults are confirmed against each provider's current docs at build time.
- **Maximum output** is set per tool: 2,048 tokens for summary and answer, 4,096
  for quiz and flashcards. A response cut off at the limit (finish reason not a
  normal stop) or blocked by the provider's safety filter is a failed request.
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
  files: Google API key shape (`AIza` + 35 characters) and xAI key shape (`xai-`
  prefix). The scan has tests and never prints the match itself.

## Other changes

- **Download my data** adds `ai_results` (tool, provider, question, result,
  time) and `ai_requests` (tool, provider, status, characters sent, time). They
  have limits (500 results; 20,000 requests) and the same 413 page with no partial
  file.
- The privacy-safe logging route list gets the new routes.
- Docs: a new `docs/AI_STUDY_ASSISTANT.md`; updates to `STUDY_MATERIALS.md`,
  `STUDENT_WEBSITE.md` and `DATABASE_SECURITY.md`; an AGENTS.md section.
- CSS: 906 bytes of budget remain. New pages reuse existing classes. Any budget
  change is asked for in its PR, never made silently. The new pages are added to
  the dark-mode contrast checks.

## Build stages (each its own PR and review)

1. **Records:** models, migrations, RLS, grants, startup checks, services
   (reserve under the lock, mark status, save result, list, delete), and security
   tests on real PostgreSQL. No provider code.
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
- The site-wide ceiling and the 500-result cap.
- One request in flight per student; a stale `sent` becomes `interrupted` and is
  never retried.
- No transaction is open during the provider call.
- A startup refusal for each stray grant on the two new tables.

**Consent**
- GET never sends. The confirm POST never sends or counts. A missing or invalid
  CSRF token never sends.
- An expired, forged or reused consent token never sends. A refresh or double POST
  sends once.
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
- On Windows the PDF child process has a time limit but no memory limit.
- Confirm-page extraction is not counted. It is bounded per call and per process,
  which is acceptable for a local single-user site; any deployment would need a
  separate limit.
- The ledger grows by up to 50 rows per student per day and has no cleanup. The
  export refuses with 413 beyond 20,000 rows, which is about a year of maximum use.
  Retention needs its own decision later.
- Costs depend on the owner's provider plans. The limits bound them but do not
  prevent them.

## Review response (revision 2)

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
| L11 Caps | 500 results per student; site-wide daily ceiling |
| L12 Validation details | Index range, extra keys, totals, output tokens, safety and truncation, shape version |
| L13 Consent wording | Provider-named buttons, what is and isn't sent, cannot recall, copyright warning, characters and truncation recorded |
| L14 Secrets file | Named, outside the repository, launcher passes it only to the website; key-pattern scanning |
| L15 Export | Limits and 413 for both new sections |
