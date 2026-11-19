"""Make the PRIVATE password file for the read-only backup login, once, on your own computer.

    python tools/backup_password.py

Creates, outside the repository (%LOCALAPPDATA%\\UCC\\backup on Windows, or UCC_LOCAL_HOME):
  backup-password.sql   sets a new random password for ucc_backup. Run it in Supabase's SQL editor
                        AFTER supabase/backup/backup_role.sql.
  backup-password.txt   the same password, to paste into the GitHub secret UCC_BACKUP_PASSWORD.
Nothing secret is printed, and it refuses to overwrite existing files.
"""
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supabase_secrets import private_folder, write_private  # noqa: E402


def main():
    folder = private_folder().parent / 'backup'
    sql, text = folder / 'backup-password.sql', folder / 'backup-password.txt'
    if sql.exists() or text.exists():
        sys.exit(f'{folder} already has a backup password; nothing was changed.')
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        folder.chmod(0o700)
    password = secrets.token_urlsafe(32)  # only [A-Za-z0-9_-]: safe inside the SQL literal
    write_private(sql, '-- PRIVATE: password for the read-only backup login. Run once in the SQL editor.\n'
                       f"ALTER ROLE ucc_backup WITH PASSWORD '{password}';\n")
    write_private(text, password + '\n')
    print(f'Private backup password files created in {folder}. Nothing secret was printed.')


if __name__ == '__main__':
    main()
