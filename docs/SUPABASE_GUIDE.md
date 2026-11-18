# Supabase guide: the database

The website's database runs on Supabase (free plan). Vercel hosting comes in a later step; this
page only sets up the database. Claude will walk you through it; this is the reference.

## What is in `supabase/migrations/`

Numbered SQL files made from the Django migrations by `tools/export_supabase_sql.py`. Never edit
them by hand. Run them **in number order** in the SQL editor:

| File | What it does |
| --- | --- |
| `0001_schema.sql` | Every table, constraint and row-level security policy (all 40 Django migrations), and Django's list of applied migrations. |
| `0002_security.sql` | The website's two restricted logins (`ucc_runtime`, `ucc_auth`), removes Supabase's automatic Data API access from every table and private function (also for tables made later), keeps Supabase's own services able to connect, the exact website grants, row-level security on **every** table, and a self-check that stops with an error if anything is still open. |

Later updates come as a new schema file and a new security file. Run both, in order. Running a
security file again is always safe.

## Set up (once)

1. **Create the project.** supabase.com → New project. Choose a strong database password and keep
   it private. Region: the one closest to Nigeria that is offered (for example London).
2. **Turn off automatic API exposure.** Project → **Integrations → Data API → Settings**: switch
   off **Automatically expose new tables**. If you will not use the Data API at all (this website
   does not), switch the Data API off too.
3. **Run the numbered files.** SQL Editor → **New query**. Open `supabase/migrations/0001_schema.sql`
   on GitHub, select **Raw**, copy everything, paste, press **Run**. Then the same for
   `0002_security.sql`. Each should finish with *Success. No rows returned*. Do not save them as
   snippets.
4. **Make your private file** (on your own computer, in the project folder):

   ```powershell
   & $py tools/supabase_secrets.py
   ```

   It writes `private-setup.sql` and `secrets.json` to `%LOCALAPPDATA%\UCC\supabase`. They hold
   new random passwords for the two website logins and the private signing key. Nothing is
   printed, and the tool refuses to overwrite them.
5. **Run the private file.** Open `private-setup.sql` in Notepad, copy everything, run it in a
   new SQL editor query. Then **delete that query** from the SQL editor's history. Keep
   `secrets.json` private: Vercel needs its values later, and only you should ever see them.

## Why this is safe

- The SQL editor runs as Supabase's `postgres` login, which is **not** a superuser. Every file was
  tested on Supabase's own database image (`supabase/postgres` 17.6) running exactly like that.
- Supabase normally gives its Data API logins (`anon`, `authenticated`, `service_role`) full
  rights on every new table. That would have exposed password hashes and sign-in sessions. The
  security file removes all of it, and **the website now refuses to start** (503) if any of
  those logins can reach a table or private function again; re-running the newest security file
  repairs it.
- Every table has row-level security. Student tables force it (each student sees only their own
  rows, through the signed transaction context). Account and sign-in tables allow only the
  `ucc_auth` login. Django's bookkeeping tables allow no other login.
- The website logins are `LOGIN NOINHERIT` with no superuser, bypass-RLS, create-database or
  create-role rights, cannot create temporary objects, and hold exactly the same grants as the
  locally tested website.
- Supabase installs `pgcrypto` in its own `extensions` schema (it can only exist once), so on
  Supabase `ucc_crypto.hmac` is a small private wrapper around it instead of a second copy.
- Passwords and the signing key never appear in the repository or in the numbered files.

## Limits of the free plan

- 500 MB database. Projects **pause after a week without activity** (nothing is deleted; resume
  from the dashboard).
- **No automatic backups** on the free plan. Launch step H adds our own.

## Tests

- `tools/test_supabase_sql.py` (CI job `supabase-sql`, Docker): the committed files match the
  migrations (checked on a plain PostgreSQL 17), every file runs cleanly as the non-superuser
  `postgres` login and the security file can be re-run, Django sees every migration applied,
  the Data API logins reach nothing (also for tables made later) and are refused even as
  `SET ROLE`, every table has RLS and student tables force it, the website logins are restricted
  and cannot create temporary objects, Supabase's own logins can still connect, a full journey
  works with two students who cannot see each other's courses, and five ways of reopening the
  Data API make the website refuse to start until the security file is re-run.
- `tests/test_supabase_secrets.py`: the private files are complete, private (0600), never
  overwritten, never inside the repository, and nothing secret is printed.
