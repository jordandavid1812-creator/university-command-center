"""Create the private settings for the server, once.

    python3 deploy/make_secrets.py --host ucc-student.com --email you@example.com

Writes deploy/secrets/{db,migrator,web,caddy}.env with new random passwords and keys, readable
only by you. Nothing secret is printed. Refuses to overwrite existing files: losing them means
losing access to the database. Keep a private copy somewhere safe (not in git or chat).
"""
import argparse
import os
import re
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDER = HERE / 'secrets'
HOST = re.compile(r'(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')
EMAIL = re.compile(r'[^@\s]{1,64}@[a-z0-9.-]{1,253}\.[a-z]{2,63}')
DATABASE = 'ucc'
ROLES = {'admin': 'ucc_dba', 'migrator': 'ucc_migrator', 'runtime': 'ucc_runtime', 'auth': 'ucc_auth'}
PROXY_NETWORK = '172.30.0.10/32'  # Caddy's fixed address in compose.yml


def files(host, tls):
    password = {name: secrets.token_urlsafe(32) for name in ROLES}
    django_key, signing_key = secrets.token_urlsafe(64), secrets.token_hex(32)
    shared = {'PGHOST': 'db', 'PGPORT': '5432', 'PGDATABASE': DATABASE, 'DJANGO_SECRET_KEY': django_key,
              'UCC_CONTEXT_SIGNING_KEY': signing_key, 'UCC_RUNTIME_ROLE': ROLES['runtime'],
              'UCC_AUTH_ROLE': ROLES['auth']}
    return {
        'db.env': {'POSTGRES_USER': ROLES['admin'], 'POSTGRES_PASSWORD': password['admin'], 'POSTGRES_DB': 'postgres',
                   'UCC_DB_NAME': DATABASE,
                   'UCC_MIGRATOR_ROLE': ROLES['migrator'], 'UCC_MIGRATOR_PASSWORD': password['migrator'],
                   'UCC_RUNTIME_ROLE': ROLES['runtime'], 'UCC_RUNTIME_PASSWORD': password['runtime'],
                   'UCC_AUTH_ROLE': ROLES['auth'], 'UCC_AUTH_PASSWORD': password['auth']},
        'migrator.env': {**shared, 'PGUSER': ROLES['migrator'], 'PGPASSWORD': password['migrator']},
        'web.env': {**shared, 'PGUSER': ROLES['runtime'], 'PGPASSWORD': password['runtime'],
                    'UCC_AUTH_PASSWORD': password['auth'], 'UCC_SITE_HOST': host,
                    'UCC_TRUSTED_PROXY': PROXY_NETWORK},
        'caddy.env': {'UCC_SITE_HOST': host, 'UCC_CADDY_TLS': tls},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Create the private server settings once.')
    parser.add_argument('--host', required=True, help='Your domain name, for example ucc-student.com')
    parser.add_argument('--email', help='Your email, for HTTPS certificate notices')
    parser.add_argument('--internal-tls', action='store_true', help=argparse.SUPPRESS)  # local tests only
    parser.add_argument('--folder', type=Path, default=FOLDER, help=argparse.SUPPRESS)
    values = parser.parse_args(argv)
    if not HOST.fullmatch(values.host):
        parser.error('--host must be your domain name in lowercase, like ucc-student.com (no https:// or /).')
    if values.internal_tls:
        tls = 'internal'
    elif values.email and EMAIL.fullmatch(values.email.lower()):
        tls = values.email.lower()
    else:
        parser.error('--email must be your email address (for HTTPS certificate notices).')
    folder = values.folder
    content = files(values.host, tls)
    if any((folder / name).exists() for name in content):
        sys.exit(f'Stopped: {folder} already has settings. Nothing was changed.')
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    for name, settings in content.items():
        path = folder / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(''.join(f'{key}={value}\n' for key, value in settings.items()))
    print(f'Private settings created in {folder} (readable only by you). Nothing secret was printed.')


if __name__ == '__main__':
    main()
