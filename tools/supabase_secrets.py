"""Make your PRIVATE Supabase setup file, once, on your own computer.

    python tools/supabase_secrets.py

Creates, outside the repository (%LOCALAPPDATA%\\UCC\\supabase on Windows, or UCC_LOCAL_HOME):
  private-setup.sql   new random passwords for the website's two database logins and the private
                      signing key. Run it in Supabase's SQL editor AFTER the numbered files.
  secrets.json        the same values plus a Django secret key, for the Vercel settings later.
Nothing secret is printed. It refuses to overwrite existing files: if Supabase already has these
passwords, replacing the files would lock the website out.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

REPO = Path(__file__).resolve().parents[1]


def private_folder():
    base = os.environ.get('UCC_LOCAL_HOME') or (
        str(Path(os.environ['LOCALAPPDATA']) / 'UCC') if os.environ.get('LOCALAPPDATA') else str(Path.home() / '.ucc'))
    folder = Path(base) / 'supabase'
    if folder.resolve().is_relative_to(REPO.resolve()):
        sys.exit('Refusing to keep secrets inside the repository. Set UCC_LOCAL_HOME to a private folder.')
    return folder


def values():
    return {'runtime_password': secrets.token_urlsafe(32), 'auth_password': secrets.token_urlsafe(32),
            'context_signing_key': secrets.token_hex(32), 'django_secret_key': secrets.token_urlsafe(64)}


def private_sql(data):
    # token_urlsafe and token_hex use only [A-Za-z0-9_-], so the SQL literals need no escaping.
    return f'''-- PRIVATE: University Command Center passwords and signing key for Supabase.
-- Run in the SQL editor AFTER the numbered files. Never save it as a snippet, commit or share it.
BEGIN;
ALTER ROLE ucc_runtime PASSWORD '{data['runtime_password']}';
ALTER ROLE ucc_auth PASSWORD '{data['auth_password']}';
INSERT INTO ucc_security.context_key (singleton, secret) VALUES (true, decode('{data['context_signing_key']}', 'hex'))
ON CONFLICT (singleton) DO UPDATE SET secret = EXCLUDED.secret;
COMMIT;
'''


def write_private(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(text)


def main(argv=None):
    argparse.ArgumentParser(description='Make the private Supabase setup file once.').parse_args(argv)
    folder = private_folder()
    files = {'private-setup.sql': None, 'secrets.json': None}
    if any((folder / name).exists() for name in files):
        sys.exit(f'Stopped: {folder} already has Supabase secrets. Nothing was changed.')
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = values()
    write_private(folder / 'private-setup.sql', private_sql(data))
    write_private(folder / 'secrets.json', json.dumps(data, indent=2))
    print(f'Private Supabase files created in {folder}. Nothing secret was printed.')
    print(f'Next: open {folder / "private-setup.sql"} in Notepad, copy everything, and run it in the SQL editor.')


if __name__ == '__main__':
    main()
