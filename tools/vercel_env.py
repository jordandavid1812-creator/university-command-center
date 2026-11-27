"""Make your PRIVATE Vercel settings file from your Supabase secrets, on your own computer.

    python tools/vercel_env.py --site-host university-command-center.vercel.app \
        --project-ref abcdefghijklmnopqrst --pooler-host aws-0-eu-west-1.pooler.supabase.com \
        --email-address your.site.address@gmail.com

It then asks (hidden) for that Gmail account's 16-character app password.

Reads secrets.json (made by tools/supabase_secrets.py) and writes vercel.env next to it, in
%LOCALAPPDATA%\\UCC\\supabase (or UCC_LOCAL_HOME). In Vercel: Settings > Environment Variables >
Import .env, choose ONLY the Production environment. Nothing secret is printed; it refuses to
overwrite an existing vercel.env.
"""
import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supabase_secrets import private_folder  # noqa: E402

HOST = re.compile(r'(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')
REF = re.compile(r'[a-z0-9]{20}')
POOLER = re.compile(r'aws-[0-9]+-[a-z]{2}-[a-z]+-[0-9]+\.pooler\.supabase\.com')
GMAIL = re.compile(r'[a-z0-9._%+-]{1,64}@gmail\.com')
APP_PASSWORD = re.compile(r'[A-Za-z0-9]{16}')


def settings(secrets, site_host, project_ref, pooler_host, email_address, app_password):
    return {
        'UCC_SITE_HOST': site_host,
        'UCC_SUPABASE_PROJECT_REF': project_ref,
        'PGHOST': pooler_host,
        'PGPORT': '6543',
        'PGDATABASE': 'postgres',
        'PGUSER': 'ucc_runtime',
        'PGPASSWORD': secrets['runtime_password'],
        'UCC_RUNTIME_ROLE': 'ucc_runtime',
        'UCC_AUTH_ROLE': 'ucc_auth',
        'UCC_AUTH_PASSWORD': secrets['auth_password'],
        'UCC_CONTEXT_SIGNING_KEY': secrets['context_signing_key'],
        'DJANGO_SECRET_KEY': secrets['django_secret_key'],
        'UCC_EMAIL_ADDRESS': email_address,
        'UCC_EMAIL_APP_PASSWORD': app_password,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Make the private Vercel settings file.')
    parser.add_argument('--site-host', required=True, help='Your Vercel address, e.g. university-command-center.vercel.app')
    parser.add_argument('--project-ref', required=True, help='Your Supabase project reference (20 letters and digits)')
    parser.add_argument('--pooler-host', required=True, help="Supabase's transaction pooler host from the Connect dialog")
    parser.add_argument('--email-address', required=True, help="The website's own Gmail address (not your personal one)")
    values = parser.parse_args(argv)
    if not HOST.fullmatch(values.site_host):
        parser.error('--site-host must be the address only, like university-command-center.vercel.app (no https://).')
    if not REF.fullmatch(values.project_ref):
        parser.error('--project-ref must be the 20-character Supabase project reference.')
    if not POOLER.fullmatch(values.pooler_host):
        parser.error('--pooler-host must look like aws-0-eu-west-1.pooler.supabase.com.')
    email_address = values.email_address.strip().lower()
    if not GMAIL.fullmatch(email_address):
        parser.error("--email-address must be the website's own Gmail address, like ucc.notifications@gmail.com.")
    folder = private_folder()
    source = folder / 'secrets.json'
    if not source.exists():
        sys.exit('Run tools/supabase_secrets.py first (and its private-setup.sql in Supabase).')
    target = folder / 'vercel.env'
    if target.exists():
        sys.exit(f'Stopped: {target} already exists. Nothing was changed.')
    app_password = ''.join(getpass.getpass('Gmail app password (16 letters; it will not be shown): ').split())
    if not APP_PASSWORD.fullmatch(app_password):
        sys.exit('Nothing written: a Google app password is 16 letters (spaces are fine).')
    data = settings(json.loads(source.read_text()), values.site_host, values.project_ref, values.pooler_host,
                    email_address, app_password)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(''.join(f'{key}={value}\n' for key, value in data.items()))
    print(f'Private Vercel settings written to {target}. Nothing secret was printed.')


if __name__ == '__main__':
    main()
