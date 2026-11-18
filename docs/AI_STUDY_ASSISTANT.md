# AI study assistant

The approved design is [AI_STUDY_ASSISTANT_PLAN.md](AI_STUDY_ASSISTANT_PLAN.md)
(revision 4). This page records what is built. It is built in four stages, each
with its own PR and review.

| Stage | Status |
| --- | --- |
| 1. Records: tables, RLS, grants, startup checks, services, security tests | Built (PR #67, #68) |
| 2. Text extraction (TXT, PDF via `pypdf` in a child process) | Built (PR #69) |
| 3a. Provider client (Gemini, Grok), prompts, answer checks, key scanning | Built (PR #70) |
| 3b. Pages, consent token, export, `prune_ai_ledger`, plus owner-requested quiz, flashcards, copy/download and dashboard panel | **Built (this PR)** |
| 4. Manual check on the owner's PC with the owner's keys | Not started |

From stage 3b the website can send a file's text to Gemini or Grok, but only after the
student's Send click on the confirm page, and only when the owner has set a key and a
model (stage 4). With no key set, nothing can be sent.

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

- **TXT:** the stored bytes are already checked UTF-8; they are decoded strictly
  (as `utf-8-sig`, so a byte-order mark, which the upload check accepts, is neither
  counted nor sent), cleaned and capped. Empty or whitespace-only text is "no selectable text".
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
    1 ≤ pages read ≤ min(total, 300), total ≤ 100,000, and "not cut short" only when
    every page was read), decodes the text strictly as UTF-8, then re-cleans and
    re-caps it. Anything else means "could not be read".
  - Any setup failure becomes "could not be read" and never leaves the child running:
    the child cannot start, `sys.executable` is empty, the temporary folder cannot be
    created or removed, or a helper thread cannot start.
  - At most **two PDF extractions** run at once per website process. A third gets
    "Busy, try again in a moment" immediately. TXT files need no slot.

`pypdf` 6.21.4 is pinned with hashes in `requirements-django-lock.txt`, generated
with the same `pip-compile` command, and `pip-audit` reports no known
vulnerabilities. Only `pypdf` was added; it has no other dependencies on
Python 3.12. The newer 7.x releases were less than two weeks old when pinned.

## Stage 3a: provider client

`student_web/ai_providers.py` has no database or Django code. Stage 3b's pages call
`ask(provider, tool, text, question)` only after the confirm-page POST and a ledger
reservation.

- **Configuration.** A provider is offered (`available_providers()`) only when both
  its key and its model are set and valid:
  - keys: `UCC_GEMINI_API_KEY`, `UCC_GROK_API_KEY`, which must be printable ASCII with
    no spaces, 8–512 characters;
  - models: `UCC_GEMINI_MODEL`, `UCC_GROK_MODEL`, checked with
    `re.fullmatch(r"[a-z0-9][a-z0-9.\-]{0,63}")`.

  **There are no default model names.** The provider documentation sites were not
  reachable from the build environment, so the owner sets current model names from the
  providers' own pages in stage 4. Keys and models are read from the environment at
  call time; they are not Django settings.
- **Hosts are fixed in code:** `generativelanguage.googleapis.com` and `api.x.ai`,
  over verified HTTPS (`http.client`, default certificate checks). No proxy settings
  are read.
- **Keys only in headers:** `x-goog-api-key` for Gemini and
  `Authorization: Bearer` for Grok, never in a URL or the body.
- **One overall 60-second deadline.** The whole exchange (name lookup, connect, TLS
  handshake, headers, body) runs in a helper thread, and the caller waits only until
  the deadline. A stuck exchange is aborted (its socket is shut down) and the caller
  gets `timeout` at once, whichever step was slow. Each socket operation is also
  given only the time left. A slow name lookup can keep the helper thread alive
  briefly after the caller has moved on, but never delays the caller.
- **No redirects:** any 3xx reply is a `redirect` failure. Replies over **1 MiB** are
  abandoned before parsing (`too_large`).
- **Formats.** The plan's Gemini `generateContent` and xAI `chat/completions`.
  - Gemini: JSON output is requested with `responseMimeType`; internal "thought" parts
    are skipped; `MAX_TOKENS` means `truncated`; a prompt block reason or a content
    finish reason (`SAFETY`, `RECITATION`, `LANGUAGE`, `BLOCKLIST`,
    `PROHIBITED_CONTENT`, `SPII`, `IMAGE_SAFETY`) means `blocked`; a missing or
    unknown finish reason means `invalid_response`.
  - Grok: `response_format` json_object; `length` means `truncated`;
    `content_filter` or a refusal means `blocked`; a missing or unknown finish
    reason, or a message that is not an object, means `invalid_response`.
  - Both providers now call these endpoints legacy but supported; stage 4 confirms
    them with one real call each.
  - Maximum output: 2,048 tokens for summary and answer, 4,096 for quiz and
    flashcards. Whether reasoning models need a larger budget is also checked in
    stage 4.
- **Prompts** say the text between `<study_material>` markers is content to study,
  never instructions. A file cannot close the marker early: any spelling of either
  marker inside it (any case, spaces, `_`/`-`/space between the words, a slash
  anywhere) is replaced with `[study_material marker removed]`. The strict answer
  checks remain the main defence.
- **Answer checks** (`parse_result` and `check_result`, shape version 1):
  - strict JSON with exact keys, no extra keys;
  - lengths per field; control characters and lone surrogates refused; zero-width
    and bidirectional-control characters removed; at most 64 KiB once checked;
  - summary: 1–10 points;
  - quiz: 5–10 questions, each with exactly 4 options and an integer (not boolean)
    correct index from 0 to 3;
  - flashcards: 5–20 cards;
  - answer: text plus a boolean "not covered".

  `check_result` is also used to re-check saved results before showing them.
- **Errors** are `ProviderError` with a ledger category (`network`, `timeout`,
  `redirect`, `http_error`, `too_large`, `invalid_response`, `blocked`, `truncated`)
  and a `status_class` (`3xx`/`4xx`/`5xx` or none), which is safe to log: 4xx usually
  means a wrong key or model.
  Their message and traceback never contain the key, URL, file text, question or
  reply; underlying exceptions are suppressed. The module imports no logging and no
  other HTTP library (a source audit checks this).
- **One call to one provider:** `ask(provider, tool, text, question)` makes exactly one
  request, with no retries and no fallback. Asking for a provider that is not
  configured is a `ValueError`, and nothing is contacted. Connections are made only by
  the module's `_connect` (fixed hosts). It is not a parameter; tests replace it with
  `patch`, and application code must never change it.
- **Key scanning.** `tools/check_repository_safety.py` now also fails if any tracked
  file contains a Google-key-shaped (`AIza` + exactly 35 key characters) or
  xAI-key-shaped (`xai-` + at least 40) string. Files of any size are read in 1 MiB
  chunks that overlap by 256 bytes, so a key split across chunks is still found. It
  prints only a count, never the match or the file name.
- **Network guard.** `tests/network_guard.py` (`NoNetworkMixin`) fails any test that
  resolves or connects to a non-local address. The provider tests use it, and stage
  3b's web tests must use it too.

## Stage 3b: pages

| Route | Method | What it does |
| --- | --- | --- |
| `/materials/<id>/tools/` | GET | Three tool cards (Summary, Quiz, Flashcards), each its own small form with a "Create …" button; a separate "Ask about this file" card with its own required question box; today's usage bar; saved results. Only for the student's own material with a stored file (otherwise 404) |
| `/materials/<id>/tools/confirm/` | POST | The confirm page: what is sent (`describe()` wording), what is not, the warnings, the usage meter, and one **Send** button per configured provider (**Send** and, with two, **Send with the backup service**; no company or model names). Each button is its own small form with a hidden `provider` field: the site-wide busy script disables buttons on submit, and a disabled button's own value would not be sent (PR #71 review). **Never sends and never counts.** No Send button at 50 a day or with no provider |
| `/materials/<id>/tools/send/` | POST | The only route that can call a provider. Always redirects |
| `/ai-requests/<id>/` | GET | In progress (reloads every 5 seconds, no JavaScript needed), failed (plain reason), interrupted, "result deleted", or a redirect to the result |
| `/ai-results/<id>/` | GET | The result, re-checked with `check_result` before display, labelled "AI-generated: check it against your notes". An invalid old row shows "can no longer be displayed" |
| `/ai-results/<id>/download/` | GET | The result as a plain-text attachment (`nosniff`, sandbox CSP) |
| `/ai-results/<id>/delete/` | GET/POST | Dedicated confirmation; the ledger row stays and still counts |

Study materials shows **Study tools** for each stored file. The dashboard has an **AI
study tools** panel with today's usage meter and the five latest results, read in the
same single dashboard transaction (two extra queries). **Download my data** adds
`ai_results` and `ai_requests` (never the consent token hash), within the 413 limits.

### Send, step by step (`student_web/ai_views.py`)

1. The form is checked: exact fields, tool from the list, and a question only for "Ask
   a question" (1–500 characters, no control characters or lone surrogates).
2. The consent token (`student_web/ai_consent.py`) is checked. It must have a valid
   signature (Django signing, its own salt) and match this student, material, tool and
   question. A forged token, or one for another student, material, tool or question,
   gets a 400 and nothing is sent.
3. **The hash is looked up before the age check.** A request already made with this
   token redirects to it (a refresh, a double click, or an old tab). Only then does an
   expired token (over 10 minutes) get "Confirmation expired" and nothing is sent.
4. The provider must be configured; a forged choice gets a 400.
5. The file is read and extracted again. A failure stops here, with nothing sent and
   nothing counted. If the character count differs from the confirmed one, the send
   is refused.
6. `services.ai.reserve` runs (busy, 50 a day, 500 results); refusals get a 429 with
   a plain message. An existing request for the token redirects.
7. `ai_providers.ask` runs with **no database transaction open**. A test records
   `in_atomic_block` while connecting.
8. `succeed` saves the result, or `fail` records the category and, for an HTTP error,
   the status class (`4xx`: usually a wrong key or model or no quota; `5xx`: a provider
   problem). The request page explains which.
   - **From the reservation on, every outcome is recorded and redirected.** An
     unexpected client error counts as `network`; a database error while saving counts
     as `save`.
   - If even recording fails (database down, session ended), the row stays `sent` and
     shows as interrupted after two minutes. It is never retried.
   - If the session ended during the call, the save is refused and the output
     discarded. A late answer for an interrupted request is discarded.
   - Each failure writes one fixed-label log line (logger, level, route only). The
     details live on the ledger row, never in logs.

Every Send response is a redirect, so refreshing never posts again. The one exception
is a session that ends during the call: the student is signed out, so they get the
"Please sign in again" page (403) and the request becomes interrupted. Only the file's
extracted text and the question are sent: never the username, email, display name,
matric number, file name or material title.

### Owner-requested extras (no extra AI requests)

All of these work on a result already saved, and all work without JavaScript first.
`static/student_web/ai.js` and `ai.css` load **only on the AI pages**, so the site-wide
`site.js` and `site.css` budgets and pages are unchanged.

- **Interactive quiz.** Without JavaScript, each question lists its options with a
  "Show answer" box. With it, the options become buttons:
  - instant right/wrong colours and the reason;
  - a sticky score and progress bar;
  - a final score that counts up, with confetti for a perfect score;
  - "Try again".
- **Flip flashcards.** Without JavaScript, a list of fronts and backs. With it, a 3D
  flip deck: next/previous (also the arrow keys), shuffle, "I know it" and "Review
  again" piles, "Study review pile" and "All cards".
- **Copy and download.** "Download as text" is a normal link. "Copy" (JavaScript) uses
  the Clipboard API on secure pages such as `127.0.0.1`, otherwise a fallback.
  Printing shows every quiz answer.
- **Dashboard AI panel** (above).

`ai.js` is kept under 20,000 bytes and `ai.css` under 9,500, and a source audit checks
that `ai.js` uses no browser storage, cookies, network calls, `eval`, or HTML insertion.
AI text is only ever inserted with `textContent`, never as HTML. All motion is skipped
when the device asks for reduced motion. The waiting page and spinner work without
JavaScript. Site-wide premium animations (GSAP) are a separate, later task with its own
plan.

### Ledger status class (migration 0014)

`0014_study_ai_status_class` adds the ledger's `status_class`: `""`, or `3xx`, `4xx` or
`5xx` **only on a failed request** (CHECK constraint; database default `""`). The runtime
may update it along with `status`, `error_category` and `updated_at`, and the startup
check allows exactly those four columns.

**After migrating, re-run `configure_runtime`** (the local launcher does both). Without
the new grant, failures cannot be recorded, and every failed request would show as
interrupted.

### Page design (PR #74, after the owner's first real use)

- The tools page has no radio buttons. Each quick tool is its own form posting exactly
  `tool` and an empty `question`; the Ask card posts `tool=answer` and the question. The
  server still refuses a question with any other tool, whatever the browser sends.
- A refused question keeps its text. Its error appears in the focusable summary as a link
  to the box, and inline above the box, which has `aria-invalid` and `aria-describedby`.
- The confirm page shows a "What will be sent" summary, then the consent warnings, the
  usage bar and the Send buttons. The warnings are shown in full, in an open box, until the
  student presses **Got it, don't show again** (owner decision, November 2026; this replaces
  the earlier "never collapsible" rule). That button re-posts the same tool and question to
  the confirm page with `notes=hide`. The response sets the `ucc_ai_notes=hidden` cookie
  (HttpOnly, SameSite=Lax, one year, this browser only) and shows the same page again.
  - After that the page shows one short line ("Sent to an outside AI service · AI answers
    can be wrong.") with the full notes behind **Show details**, which works without
    JavaScript.
  - **Show these notes every time** posts `notes=show`, which deletes the cookie.
  - The cookie changes only the notes. It never changes what is sent, never sends anything
    and never counts. Any other cookie value shows the full notes.
  - Tests: `web_tests/test_ai_notes.py` and `tools/test_redesign_browser.py`.
- Pages never name the AI company or model (owner decision, November 2026). With one
  configured service the confirm page has one **Send** button; with two, **Send** (Gemini)
  and **Send with the backup service** (Grok). The buttons post the neutral codes `main` and
  `backup`, which `AiSendForm` maps back to the internal names (`ai_providers.PUBLIC_CODES`).
  The warnings say "an outside AI service", and the request status page shows only the tool.
  The student's data export leaves them out as well: AI requests list the tool, status,
  characters sent and time, but not the service or model.
- The answer page shows "You asked" above the answer.
- Study materials is highlighted in the sidebar on AI request and result pages; their
  URL prefixes come from the routes (`context.ai_prefixes`).
- Flashcards: both faces share one grid cell, so the card grows to fit the longer face
  and never scrolls. Faces over 180 characters use a smaller font, keeping a
  600-character card about 400 pixels tall on a 360-pixel phone.

### `prune_ai_ledger`

`python server/manage.py prune_ai_ledger --settings=config.settings.auth_migration`,
with the website stopped.

- It refuses unless the current role owns both AI tables, so the runtime role is
  refused.

- In one transaction it checks deferred keys immediately, lifts `FORCE` on both
  tables, deletes ledger rows older than 365 days that have no result, and restores
  `FORCE`.
- It prints only a count.

## Tests

| Suite | Covers |
| --- | --- |
| `security_tests.test_study_ai_rls` | Raw SQL as the runtime role, with positive controls (the baseline rows are accepted): forced RLS on both tables, no-context access, own-only rows, cross-student writes and links, no ledger DELETE, status-only UPDATE, no result UPDATE, no TRUNCATE, material delete refused around Django, every CHECK value list, a result whose tool differs from its request |
| `tests.test_ai_providers` (no database; a guard fails any non-local connection) | Configuration and unsafe keys or models refused; fixed verified-HTTPS hosts; request formats; only the text and question sent, the key only in a header; one call to the chosen provider even on failure; an unconfigured provider is never contacted; every outcome mapped to its category; thought parts skipped; errors and tracebacks without the key or text; every answer shape and refusal; 64 KiB limit; marker variants; lone surrogates as a provider error; invisible characters removed; odd finish reasons as `invalid_response`; status classes; `ask` has no connection parameter; against a local misbehaving server: no redirects, the overall deadline for a dripping body, dripping headers and a silent TLS handshake, the 1 MiB cap, refused connections; source audit. The overall deadline (including the helper thread), size cap, redirect refusal, marker variants, surrogate refusal, odd-reason mapping and thought skipping were each shown to fail when removed |
| `tests.test_repository_key_scan` | Key shapes found, ordinary text and near-misses ignored, a key at the end of a 6 MiB file and a key split across chunks found (shown to fail without the overlap), and the check fails on a tracked key in a temporary repository without printing the key or file name |
| `tests.test_pdf_child_memory` (no database) | **Every platform:** a slow child's real Python process is gone after the time limit, and the call returns within 20 seconds instead of waiting for the child (on Windows this checks the process behind the virtual-environment launcher). Job Object structures match the Windows 64-bit layout, the right limits are sent in the right order (fake kernel32), any failed step means no limit, the child stops before reading without a limit, a real 1 GiB allocation is refused under the limit. **Windows only** (run on the owner's PC): the child cannot start another process, and a normal PDF still reads with the limit in place |
| `web_tests.test_text_extraction` | TXT cleaning, cap and refusals; PDF text through the real child, Greek and maths text, the 60,000-character and 300-page stops and their wording, scans, encrypted and broken files, a decompression bomb stopped only by the lowered limits, no `pypdf` output on stderr; with stand-in children: no `UCC_`, `PG` or `DJANGO_` variables reach the child, the time limit, the output cap, strict metadata and UTF-8 checks, parent re-cleaning and capping, exit codes, the busy slot limit and oversized input refused before a child starts; the child runs isolated (`-I`) in a removed `ucc-pdf-` folder with stderr discarded; setup failures are refusals that stop the child; byte-order marks; metadata that contradicts itself. The bomb, stderr and environment tests were each shown to fail when their protection is removed |
| `web_tests.test_ai_pages` (NoNetworkMixin; fake provider connection) | Since the PR #71 review: every outcome after reserving recorded and redirected (unexpected client error, database error while saving); 4xx/5xx status class stored and explained; control characters in questions refused; the dashboard panel adds exactly two AI reads within one verification; the 413 path for both new export sections; `ai.js`/`ai.css` size budgets and source audit. Also: | Tools page owner-only and stored-file-only; confirm shows what is and isn't sent and never sends or counts; GET never sends; question rules; only configured providers offered and a forged one refused; one click sends once and the result is shown escaped; only the text and question sent (no username, email, display name, matric, file name or title); a refresh or double click sends once; forged, other-tool, other-material and other-student tokens refused; an expired token sends nothing but still finds a finished request; missing CSRF never sends; failures recorded without retry or fallback; the daily limit; the session ending during the call discards the answer; no transaction open during the call; request page states; each tool without JavaScript; download headers; delete; owner-only results; invalid saved results; material deletion keeps the count; dashboard panel; export sections |
| `tools/test_ai_browser.py` (Chromium) | Send posts the question for "Ask a question"; after the browser's Back button the Send buttons work again and the wait message is hidden (shown to fail without the restore); **clicking Send with `site.js` and `ai.js` loaded posts the chosen provider, token and tool** (also without JavaScript; shown to fail with the original named-button form); one Send disables both providers and shows the wait; interactive quiz (right/wrong, reason, score, final, try again), flashcard deck (flip, next, piles, review pile, keys), copy to the clipboard as plain text, everything without JavaScript, animations end visible with no script errors, light and dark contrast of every quiz state |
| `security_tests.test_prune_ai_ledger` | Rows dated from the real clock (the command uses the database's clock). Old rows without results really removed for every student, others kept, `FORCE` restored, idempotent, runtime refused (shown to fail without lifting `FORCE`) |
| `security_tests.test_study_ai_service` | Runs on a fixed clock (noon in Lagos), so no result depends on the real time of day. One request per consent token, the unique-violation fallback, the outermost-call guard, the 51st request refused whatever earlier outcomes, material deletion keeps the count, Lagos midnight boundary (23:59 and 00:00), saved-result cap, one in flight and stale requests interrupted, closing rules, invalid results, value lists, owner isolation and forged identities, result deletion keeps the ledger row, **two real connections** for the same-token race and the race at 49 (the first connection is held after its checks, just before its insert, while the second waits for the lock; locks are counted in this test database only), startup refusal of missing RLS and each stray grant |

No historical baseline tests were changed. `security_tests/test_migrations.py` already
restores the latest academics migration.

Tests from these AI stages that were later edited (all after review):

- `security_tests.test_study_ai_service` (PR #67) lists `status_class` among the
  ledger's columns (PR #72).
- `security_tests.test_prune_ai_ledger` (PR #71) dates its rows from the real clock,
  because the command uses the database's clock (PR #72).
- `web_tests.test_ai_pages` (PR #71): the session-ended case now expects exactly the
  403 sign-in page, and the failure wording follows the neutral `network` message
  (PR #72).

## Upgrade order

As before: run `migrate`, then `configure_runtime`, with the migration settings,
then start the website. A database already at stage 1 (0012) needs only `migrate`
for 0013; it adds no grants, but re-running `configure_runtime` is harmless. The website refuses to start student services until both
new tables exist with forced RLS.

## Speed (November 2026)

Answers used to take most of a minute, sometimes timing out after 60 seconds. Two causes:

1. **Gemini 3 models "think" before answering by default.** For any model whose name starts
   with `gemini-3`, requests now send `generationConfig.thinkingConfig.thinkingLevel = "low"`
   (Google's advice when speed matters). The owner may set `UCC_GEMINI_THINKING` to `minimal`,
   `low`, `medium` or `high`, or to `default` to send no setting. Other models never get a
   thinking setting, so an older model is never sent a field it would refuse. The value is read
   through the same checked `_setting` helper as the key and model.
2. **"Ask a question" sent up to 60,000 characters.** It now sends only the parts of the
   extracted text that mention the question's words, plus the text just before and after each
   match, up to 16,000 characters, in file order (`text_extraction.focus_on_question`).
   - If nothing matches, it sends the first 16,000 characters and says so.
   - Short files are sent whole.
   - The confirm page states exactly what is sent ("The 3,588 characters that best match your
     question, picked from …").
   - The pick is deterministic, so the send step picks the same text and the consent token's
     size check still holds. The ledger records `truncated = true` when less than all was sent.

Summary, quiz and flashcards still use the whole extract. The 60-second safety limit stays.

The confirm page and the Send step read the same PDF a few moments apart. The AI pages use
`text_extraction.extract_text_remembered`, which keeps the text of the last 4 PDFs for 15 minutes,
**in memory only** (never on disk). It is keyed by a SHA-256 of the exact file bytes, which the
caller has already read with its ownership checks, so Send does not read the PDF again. Text
files are never remembered, failures are never remembered, and the plain `extract_text` is
unchanged. On the owner's PC the model mattered most (see `docs/LOCAL_WEBSITE.md`, "Choosing a
fast model").
The pages now say a request usually takes 5 to 20 seconds, and the timeout message explains
what happened in plain words.
