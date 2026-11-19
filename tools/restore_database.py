"""Put an encrypted backup back into an EMPTY database (launch step H). Prints no data.

    python tools/restore_database.py --backup ucc-backup-2026-11-19.dump.age --key ucc-backup-key.txt

First set up the target the normal way: run the numbered files in supabase/migrations and a private
setup file (docs/BACKUPS.md). Then this loads the student tables. It refuses to run if any of them
already has rows, so it can never mix a backup into live data.

Connection from the environment, as the postgres (owner) login of the TARGET database:
  UCC_RESTORE_HOST, UCC_RESTORE_PORT (default 5432), UCC_RESTORE_USER (default postgres, plus
  ".<UCC_SUPABASE_PROJECT_REF>" when that is set), UCC_RESTORE_SSLMODE (default require), PGPASSWORD.
  UCC_PG_RESTORE optionally replaces the pg_restore command, like UCC_PG_DUMP in backup_database.py.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys

import psycopg
from backup_database import AGE_HEADER, BACKUP_TABLES


def connection_string(environ):
    host = environ.get('UCC_RESTORE_HOST', '')
    port = environ.get('UCC_RESTORE_PORT', '5432')
    user = environ.get('UCC_RESTORE_USER', 'postgres')
    ref = environ.get('UCC_SUPABASE_PROJECT_REF', '')
    sslmode = environ.get('UCC_RESTORE_SSLMODE', 'require')
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host) or not port.isdigit():
        sys.exit('Set UCC_RESTORE_HOST (and UCC_RESTORE_PORT) to the target database address.')
    if ref:
        user = f'{user}.{ref}'
    return f'host={host} port={port} user={user} dbname=postgres sslmode={sslmode} application_name=ucc-restore'


def rows_present(dsn):
    with psycopg.connect(dsn, connect_timeout=15) as connection:
        for table in BACKUP_TABLES:
            if connection.execute(f'SELECT EXISTS (SELECT 1 FROM public.{table})').fetchone()[0]:  # nosec B608
                return table
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description='Restore an encrypted backup into an empty database.')
    parser.add_argument('--backup', required=True)
    parser.add_argument('--key', required=True, help='Your age private key file (from age-keygen)')
    options = parser.parse_args(argv)
    if not os.environ.get('PGPASSWORD'):
        sys.exit('Set PGPASSWORD to the target database password.')
    with open(options.backup, 'rb') as backup:
        if backup.read(len(AGE_HEADER)) != AGE_HEADER:
            sys.exit('That file is not an encrypted backup.')
    dsn = connection_string(os.environ)
    busy = rows_present(dsn)
    if busy:
        sys.exit(f'The target already has rows in {busy}; nothing was restored. Use an empty database.')
    restore = shlex.split(os.environ.get('UCC_PG_RESTORE', 'pg_restore')) + [
        '--data-only', '--no-owner', '--no-privileges', '--single-transaction', '--exit-on-error',
        '--no-password', '--dbname', dsn]
    decrypt = subprocess.Popen(['age', '--decrypt', '--identity', options.key, options.backup],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    loaded = subprocess.run(restore, stdin=decrypt.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    decrypt.stdout.close()
    decrypt_errors = decrypt.stderr.read()
    decrypt.wait()
    if decrypt.returncode != 0 or loaded.returncode != 0:
        print((decrypt_errors or loaded.stderr).decode('utf-8', 'replace')[-800:], file=sys.stderr)
        sys.exit('Restore failed and was rolled back; the target is unchanged.')
    print('Backup restored into the empty target. No data was printed.')


if __name__ == '__main__':
    main()
