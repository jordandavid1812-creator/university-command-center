# AI study assistant: plan for review

Status: **plan only, nothing built.** AGENTS.md says AI provider calls and file
content leaving the server need a new reviewed task. This document is that task's
plan. Code starts only after it is reviewed and the owner approves.

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

## What stays the same

- Local, single-user website only. No deployment.
- The CLI and Streamlit apps are unchanged.
- Stored study files are never changed. Results are separate records.
- No other student's data is ever sent or shown. Only the one chosen file's text,
  plus the student's typed question for "Ask a question", is sent.
- Automated tests and CI never contact Gemini or Grok. They use a fake provider.

## User flow

1. **Study materials** gets a **Study tools** link for each stored file.
2. The tools page for that file shows four buttons: Summary, Quiz, Flashcards and
   Ask a question (with a question box, 500 characters max). It also shows the
   student's earlier saved results for that file and today's usage (for example
   "7 of 50 used today").
3. Choosing a tool opens a **confirm page**. Nothing has been sent yet. It shows:
   - the file name, the tool and the question;
   - a provider choice (Gemini or Grok; only providers with keys);
   - how much text will be sent ("All 12,400 characters" or "The first 60,000 of
     95,000 characters", so a partial file is never presented as the whole);
   - the warning: "This file's text will be sent to Google (Gemini) or xAI (Grok)
     over the internet. Their own terms apply, and some plans may keep or use
     what you send. Don't send private or personal information."
   - a **Send** button (POST with CSRF) and a Cancel link.
4. After Send, the result page shows the output. The result is saved and listed on
   the tools page. Each saved result can be deleted.
5. Every page works without JavaScript. A request can take up to 60 seconds; the
   page explains this.

## Database (one new migration set; same patterns as study materials)

| Table | Holds | Protection |
| --- | --- | --- |
| `academics_studyairequest` | One row per sent request: owner, material, tool, provider, model, status (`sent`/`succeeded`/`failed`), created time | Forced RLS `student_owner`; same-owner FK to the material; runtime SELECT, INSERT and UPDATE of `status` only; no DELETE (the daily count cannot be reset by deleting) |
| `academics_studyairesult` | Saved output: owner, material, request, tool, question, result as checked JSON, created time | Forced RLS; same-owner FKs to the material and the request; runtime SELECT, INSERT, DELETE; **no UPDATE** |

- Deleting a material deletes its results and requests (cascade on the same-owner
  FKs), because the material is the student's own data.
- `require_runtime_role` grows to eight forced-RLS tables and refuses stray grants:
  UPDATE on results; DELETE on requests; any UPDATE on requests beyond `status`.
- The auth role cannot read either table (`accounts/boundary.py`).
- After `migrate`, re-run `configure_runtime` as usual.

## Usage limit

- 50 rows in `studyairequest` per student per **local day** (Africa/Lagos). Every
  sent request counts, including failed ones, because a failed call may still cost
  money.
- The check and the new row happen under the per-student `pg_advisory_xact_lock`
  pattern, so two quick clicks cannot both pass at 50. That transaction commits
  **before** the network call, so no database transaction is open while waiting
  up to 60 seconds.
- When the limit is reached the confirm page says so and has no Send button.

## Text extraction

- **TXT:** the stored bytes are already checked UTF-8.
- **PDF:** `pypdf` extracts text page by page, at most 300 pages. A malformed PDF,
  an encrypted one or one with no text (a scan) gets a clear message, and nothing
  is sent or counted.
- Text is cleaned (null and control characters removed), then capped at 60,000
  characters. The confirm page states the cap.
- Extraction happens in memory only, from the owner-only `read_file` (which keeps
  the fingerprint check).

## Provider calls

- **No SDKs.** Calls use Python's standard `urllib.request` over HTTPS with
  certificate checks and a 60-second timeout. The only new library is `pypdf`.
- Gemini: the `generateContent` REST endpoint with JSON output requested.
- Grok: xAI's OpenAI-compatible chat completions endpoint with JSON output requested.
- Model names are settings (`UCC_GEMINI_MODEL`, `UCC_GROK_MODEL`). Each has a
  default, confirmed against the provider's current docs at build time.
- **API keys** come only from environment variables (`UCC_GEMINI_API_KEY`,
  `UCC_GROK_API_KEY`) in the website process. They are never stored in the
  database, written to logs, shown on pages or committed. The PC launcher reads
  them from its private secrets file.
- The prompt marks the file text as material to study, not instructions to follow.
  It asks for a fixed JSON shape per tool:
  - summary: up to 10 points;
  - quiz: 5–10 questions, each with 4 options, the correct option and a short reason;
  - flashcards: 5–20 front/back pairs;
  - answer: an answer plus a "not covered by this file" flag.
- **Every response is validated** against that shape, with length limits. Anything
  else is a failed request; nothing is saved and nothing raw is shown.
- Output is shown with Django's normal escaping. It is never rendered as HTML or
  Markdown, and links in it are not clickable.
- Errors (network, timeout, provider error, invalid response) show a friendly
  page. Logs keep only the provider, status and error category. They never include
  the key, the file text, the question or the response.

## Other changes

- **Download my data** adds `ai_results` (tool, provider, question, result, time)
  and `ai_requests` (tool, provider, status, time).
- Privacy-safe logging route list gets the new routes.
- Docs: a new `docs/AI_STUDY_ASSISTANT.md`; updates to `STUDY_MATERIALS.md`,
  `STUDENT_WEBSITE.md` and `DATABASE_SECURITY.md`; an AGENTS.md section.
- CSS: the budget has 906 bytes left. New styles reuse existing classes. If more
  room is needed, the PR will ask the owner to approve a budget change; it will
  never be changed silently.

## Build stages (each its own PR and review)

1. **Records:** models, migrations, RLS, grants, startup checks, services
   (create request under the limit, set status, save result, list, delete), and
   security tests on real PostgreSQL. No provider code.
2. **Text:** `pypdf` added to `requirements-django-lock.txt` with hashes;
   extraction with limits; unit tests with synthetic PDFs and TXT, including
   malformed, encrypted, empty and oversized files. pip-audit clean.
3. **Providers and pages:** the Gemini and Grok clients, prompts and response
   validation; tools, confirm, result and delete pages; export additions. Web
   tests use a fake provider, including invalid JSON, timeouts and oversized
   output.
4. **Manual check on the owner's PC** with the owner's own keys and synthetic study
   notes only.

## Tests that must exist

- Raw-SQL RLS tests for both tables: no context, cross-student reads and writes,
  and same-owner FKs.
- The 50th request passes and the 51st is refused, including two simultaneous
  requests on two real connections. The count resets on the next local day.
- No transaction is open during the provider call.
- Nothing is sent without the POST from the confirm page: GET never sends, and a
  missing or invalid CSRF token never sends.
- Another student's material gives a 404 on every new page.
- A provider without a key is not offered, and a forged choice is refused.
- Keys never appear in responses, logs or exceptions (checked with a synthetic key).
- Results with HTML or script content are shown escaped.
- The full CI-equivalent run passes. No historical test changes are expected; any
  that become necessary will be listed and approved first.

## Known limits and risks (for the reviewer)

- Text sent to Google or xAI leaves the owner's control. Free API plans may use
  submitted data to improve their products. The consent page says this, and the
  owner should check the plan they sign up for.
- AI output can be wrong. Pages label it "AI-generated; check against your notes."
- Prompt injection inside a study file can make the output wrong. It cannot reach
  other data, because only that one file's text is sent and output is
  shape-checked and escaped.
- PDF text extraction can miss or misorder text (tables, columns, scans).
- Costs depend on the owner's provider plans. The 50-per-day limit bounds them
  but does not prevent them.
