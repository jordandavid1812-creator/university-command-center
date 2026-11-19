"""Make one encrypted backup of the student tables (launch step H). Prints no data.

    python tools/backup_database.py --output ucc-backup-2026-11-19.dump.age

Reads the connection from the environment (never from arguments, so nothing secret shows in logs):
  UCC_BACKUP_HOST        database or pooler host (Supabase: the session pooler host, port 5432)
  UCC_BACKUP_PORT        default 5432
  UCC_BACKUP_USER        default ucc_backup, plus ".<UCC_SUPABASE_PROJECT_REF>" when that is set
  UCC_BACKUP_SSLMODE     default require
  PGPASSWORD             the ucc_backup password
  UCC_BACKUP_RECIPIENT   the owner's age PUBLIC key (age1...); only the matching private key can open it
  UCC_PG_DUMP            optional command for pg_dump, e.g. "docker run --rm -i -e PGPASSWORD postgres:17 pg_dump"

The copy holds only the tables in BACKUP_TABLES (accounts, records, files, AI results). It never holds
sessions, sign-in tokens, security counters or the signing key. pg_dump's output goes straight into
age, so an unencrypted copy is never written to disk.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys

BACKUP_TABLES = (
    'accounts_student',
    'academics_semester', 'academics_course', 'academics_assignment',
    'academics_studymaterial', 'academics_materialfile', 'academics_materialtext',
    'academics_studentprofile', 'academics_studyairequest', 'academics_studyairesult',
    'academics_classsession', 'academics_studyplan', 'academics_studytopic',
    'academics_aisiteusage',
)
AGE_HEADER = b'age-encryption.org/v1'
RECIPIENT = re.compile(r'age1[02-9ac-hj-np-z]{58}')


def connection_string(environ):
    host = environ.get('UCC_BACKUP_HOST', '')
    port = environ.get('UCC_BACKUP_PORT', '5432')
    user = environ.get('UCC_BACKUP_USER', 'ucc_backup')
    ref = environ.get('UCC_SUPABASE_PROJECT_REF', '')
    sslmode = environ.get('UCC_BACKUP_SSLMODE', 'require')
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host) or not port.isdigit():
        sys.exit('Set UCC_BACKUP_HOST (and UCC_BACKUP_PORT) to the database address.')
    if ref:
        if not re.fullmatch(r'[a-z0-9]{20}', ref):
            sys.exit('UCC_SUPABASE_PROJECT_REF must be the 20-character project reference.')
        user = f'{user}.{ref}'
    if sslmode not in ('require', 'verify-full', 'disable'):
        sys.exit('UCC_BACKUP_SSLMODE must be require, verify-full or disable (local tests only).')
    return f'host={host} port={port} user={user} dbname=postgres sslmode={sslmode} application_name=ucc-backup'


def dump_command(environ):
    prefix = shlex.split(environ.get('UCC_PG_DUMP', 'pg_dump'))
    tables = [argument for table in BACKUP_TABLES for argument in ('--table', f'public.{table}')]
    return prefix + ['--data-only', '--format=custom', '--compress=6', '--no-owner', '--no-privileges',
                     '--no-password', *tables, '--dbname', connection_string(environ)]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Make one encrypted backup of the student tables.')
    parser.add_argument('--output', required=True, help='The encrypted file to write (ends in .dump.age)')
    output = parser.parse_args(argv).output
    recipient = os.environ.get('UCC_BACKUP_RECIPIENT', '')
    if not RECIPIENT.fullmatch(recipient):
        sys.exit('Set UCC_BACKUP_RECIPIENT to your age public key (it starts with age1).')
    if not os.environ.get('PGPASSWORD'):
        sys.exit('Set PGPASSWORD to the ucc_backup password.')
    if os.path.exists(output):
        sys.exit('The output file already exists; nothing was written.')
    with open(output, 'xb') as target:
        dump = subprocess.Popen(dump_command(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        encrypt = subprocess.run(['age', '--encrypt', '--recipient', recipient], stdin=dump.stdout, stdout=target,
                                 stderr=subprocess.PIPE)
        dump.stdout.close()
        dump_errors = dump.stderr.read()
        dump.wait()
    if dump.returncode != 0 or encrypt.returncode != 0:
        os.remove(output)
        # pg_dump messages name tables or connection problems, never row data; age's never include keys.
        print((dump_errors or encrypt.stderr).decode('utf-8', 'replace')[-800:], file=sys.stderr)
        sys.exit('Backup failed; no file was kept.')
    with open(output, 'rb') as written:
        if written.read(len(AGE_HEADER)) != AGE_HEADER:
            os.remove(output)
            sys.exit('The backup was not encrypted as expected; no file was kept.')
    print(f'Encrypted backup written: {os.path.basename(output)} ({os.path.getsize(output)} bytes). '
          'No data was printed.')


if __name__ == '__main__':
    main()
