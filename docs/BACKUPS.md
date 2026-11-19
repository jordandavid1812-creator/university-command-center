# Backups (launch step H)

Supabase's free plan keeps **no backups**. This project makes its own: every day at 03:17 Lagos
time a GitHub Action copies the student tables, **encrypts the copy with your age key**, and keeps
it for 30 days as a download on the Actions page. Only your private key file can open it.

## How it works

- `supabase/backup/backup_role.sql` creates **`ucc_backup`**, a login that can only *read* the student
  tables (accounts, semesters, courses, assignments, files and their text, profiles, timetable,
  study plans, AI log, saved AI results and the site's AI counter). It can read every student's rows
  (it has `BYPASSRLS`, so the copy is complete), but every transaction is read-only, it can change
  nothing, and it cannot read sessions, sign-in tokens, security counters or the private signing key.
- `tools/backup_database.py` runs `pg_dump --data-only` for those tables only and sends the output
  straight into `age`, so an unencrypted copy is never written anywhere. It prints only the file
  size, never data.
- `.github/workflows/backup.yml` runs it daily (and on demand). It never runs on pull requests, so
  no pull request can reach the backup password. The repository is public: anyone can see that
  encrypted backup files exist and their size, but nobody can read them without your private key.
- `tools/restore_database.py` decrypts a backup and loads it into an **empty** database that already
  has the structure (the numbered SQL files and a private setup file). It refuses a database that
  already has data, and runs as one transaction, so a failed restore changes nothing.
- `tools/test_backup_restore.py` (CI job `supabase-sql`, Docker) proves the whole cycle on Supabase's
  own PostgreSQL: back up two synthetic students, restore into a fresh database with **different**
  website passwords, and check every table matches, students can sign in, each sees only their own
  data, and the backup login cannot write or read secrets.

## One-time setup (owner)

Never paste a key or password into chat, GitHub issues or the code.

### A. Your encryption key (on your PC)

1. Download **age** for Windows: open https://github.com/FiloSottile/age/releases, and under the
   newest release download the file ending in `windows-amd64.zip`. Right-click it → **Extract All**.
2. Inside the extracted folder there is a folder called `age`. Move that `age` folder to
   `C:\Users\HP\age` (so `C:\Users\HP\age\age-keygen.exe` exists).
3. In PowerShell:

   ```powershell
   New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\UCC\backup"
   ```

   ```powershell
   & "$env:USERPROFILE\age\age-keygen.exe" -o "$env:LOCALAPPDATA\UCC\backup\ucc-backup-key.txt"
   ```

   It prints `Public key: age1...`. That public key is not secret; you need it in step C.
4. **Keep a second copy of `ucc-backup-key.txt`** (USB drive or password manager). If the key is
   lost, the backups can never be opened. Never upload it anywhere.

### B. The backup login's password

1. Claude creates the `ucc_backup` login in Supabase (it has no password yet, so it cannot sign in).
2. In PowerShell, in the project folder:

   ```powershell
   .\.venv\Scripts\python.exe tools\backup_password.py
   ```

3. Open `%LOCALAPPDATA%\UCC\backup\backup-password.sql` in Notepad, copy everything, paste it into
   Supabase → **SQL Editor → New query**, press **Run**. Do not save it as a snippet.

### C. GitHub settings

Repository → **Settings → Secrets and variables → Actions**:

- **Secrets** tab → **New repository secret**: `UCC_BACKUP_PASSWORD` = the text in
  `%LOCALAPPDATA%\UCC\backup\backup-password.txt`.
- **Variables** tab → **New repository variable**, three times:
  - `UCC_BACKUP_HOST` = `aws-0-eu-west-1.pooler.supabase.com`
  - `UCC_SUPABASE_PROJECT_REF` = your project reference (the same one Vercel uses)
  - `UCC_BACKUP_AGE_RECIPIENT` = your public key (`age1...`)

### D. First backup

**Actions → Database backup → Run workflow**. When it is green, open the run and download the
file under **Artifacts**. GitHub emails you if a daily backup fails (for example if the database is
paused).

## Restoring

Restore only into an **empty** project (for example a new or the paused staging project), check
it, and only then point the website at it. Claude can walk you through it; in short:

1. Create the structure: run every numbered file in `supabase/migrations` and a NEW private setup
   file (`tools/supabase_secrets.py` with a different `UCC_LOCAL_HOME`).
2. Run `tools/restore_database.py --backup <file> --key <your key file>` with the target's address
   in `UCC_RESTORE_HOST` and its `postgres` password in `PGPASSWORD`.
3. Update the website's Vercel settings to the new database and passwords, and redeploy.

Practise a restore into the staging project about once a month, so you know it works.
