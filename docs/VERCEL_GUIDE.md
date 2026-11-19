# Vercel guide: hosting the website

The website runs on Vercel and uses the Supabase database (see SUPABASE_GUIDE.md). Claude will
give you the exact values; this page is the reference. `vercel_app.py` runs every safety check
before serving anything; without the email settings below the site refuses to start.

## Email account (once)

1. Create a **new Gmail account just for the website** (for example `ucc.notifications@gmail.com`).
2. In that account: **Manage your Google Account → Security → 2-Step Verification**: turn it on.
3. Then search **App passwords** in the account settings, create one named `University Command
   Center`, and keep the 16 letters Google shows. Never paste them into chat.

## What Vercel uses

| File | What it does |
| --- | --- |
| `pyproject.toml` | Names the start file (`[tool.vercel] entrypoint = "vercel_app:app"`), Python 3.12, and the four packages. |
| `uv.lock` | The exact package versions with SHA-256 fingerprints. Vercel installs exactly these (`uv sync --frozen`). They match `requirements-django-lock.txt` (checked by `tests/test_vercel_config.py`). |
| `vercel_app.py` | Always uses `config.settings.web_vercel`, runs `manage.py check --deploy` with warnings treated as errors, then starts Django. |
| `.vercelignore` | Vercel receives only `vercel_app.py`, `pyproject.toml`, `uv.lock`, `.python-version`, `academic_logic.py` and `server/` without its tests. |
| `server/config/settings/web_vercel.py` | The public-site rules shared with the server package (`public_site.py`: one https address, HSTS, `__Host-` cookies, invite-only sign-up, WhiteNoise), plus Supabase's transaction pooler (port 6543, users `ucc_runtime.<ref>` / `ucc_auth.<ref>`, TLS required, no server-side cursors). |

## Set up (once)

1. **Make your private Vercel file** on your computer (after `tools/supabase_secrets.py` and its
   `private-setup.sql` are done):

   ```powershell
   & $py tools/vercel_env.py --site-host YOUR-VERCEL-ADDRESS --project-ref YOUR-PROJECT-REF --pooler-host YOUR-POOLER-HOST --email-address YOUR-SITE-GMAIL
   ```

   It asks for the app password (hidden) and writes `vercel.env` to `%LOCALAPPDATA%\UCC\supabase`.
   Nothing secret is printed.
2. **Import it into Vercel:** Project → **Settings → Environment Variables → Import .env**,
   choose that file, and tick **Production only** (not Preview or Development). Preview builds
   then have no settings and cannot start, so they can never show real data.
3. **Builds:** if you set *Ignored Build Step* to *Don't build anything*, set it back to
   **Automatic**. Framework preset: **Other** (or Python). Root directory: `./`.
4. **Redeploy** the latest Production deployment.

## Upload size on Vercel

Vercel Functions refuse request bodies over 4.5 MB, so on Vercel students can upload study
files up to **4 MB** (4,000,000 bytes). The upload page says so, and a bigger file gets a
clear message. Files already stored are not affected.

## How it is protected

- Vercel's edge handles HTTPS and sets the visitor's address (`REMOTE_ADDR`) and the scheme
  itself, so no forwarded header from a visitor is trusted.
- Every request still runs the database role checks; the website refuses to serve (503) if a
  login has extra rights or Supabase's Data API can reach a table.
- The PDF reader still runs in an isolated child process. On Vercel, packages live in a separate
  `_vendor` folder, so the website tells the child where pypdf is (found without importing it);
  the child adds that folder after the standard library only if it really holds pypdf.
- Uploads above Vercel's request limit (about 4.5 MB) are refused by Vercel until launch step D
  moves big study files to Supabase Storage.

## Tests

- `server/web_tests/test_vercel_profile.py`: the deploy check fails only on E105; every public-site,
  pooler and database value; unsafe project reference, pooler host, port, database and site
  address values stop the website; the visitor address is `REMOTE_ADDR`, never a forwarded header;
  static files, HTTPS redirect and unknown hosts are handled before any database work.
- `tools/test_vercel_stack.py` (CI job `supabase-sql`, Docker): Supabase's own PostgreSQL with all
  SQL files and a private test file, behind two PgBouncer transaction-mode poolers that, like
  Supabase's, ignore connection options and keep no session state. A two-student journey with
  invite codes, email links on the https address, interleaved requests sharing pooled
  connections (row-level security holds), GPA and data export; the login time limits apply; and
  the real `vercel_app.py` refuses to start without approved email.
- `tests/test_vercel_config.py`, `tests/test_vercel_env.py`, `tests/test_pdf_child_vendor.py`.
