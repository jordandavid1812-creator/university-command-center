# Launch: invited trial

The owner approved putting the website online for a small, invited group of classmates.
This page records the plan and what each step added. It is built one small PR at a time.

## Decisions

- **Audience:** invited classmates first (about 5–20), then wider only after a review.
- **Budget:** about $5–15 a month: one small cloud server (DigitalOcean recommended) running
  the website, its own PostgreSQL 17 and Caddy (automatic HTTPS), plus off-server backups.
- **AI tools:** the owner's shared key with a small daily allowance per student and a
  site-wide daily cap.
- **Address:** the owner's own domain name.

## Steps

1. **Production settings** (done): `config.settings.web_production`, gunicorn, whitenoise.
2. **Server package** (this step): Docker Compose for website + PostgreSQL + Caddy, and a step-by-step guide.
3. Invite-only sign-up.
4. Real email through a reviewed SMTP backend (lifts the `accounts.E105` gate).
5. AI limits for the shared key.
6. Account deletion and email change.
7. Privacy page and terms (NDPA).
8. Backups and a tested restore.

Then: put it online, an independent security test, and the first invitations.

## Step 1: production settings

`server/config/settings/web_production.py` builds on the existing `web_secure` profile:

| Setting | Value | Why |
| --- | --- | --- |
| `UCC_SITE_HOST` (required) | one public domain, e.g. `ucc-student.com` | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and email links use only this exact `https://` address. Wildcards, ports, schemes, IPs and `localhost`/`.test`/`.invalid` are refused. |
| `UCC_TRUSTED_PROXY` (required) | the server's private Docker network, e.g. `172.30.0.0/24` | Only Caddy can reach the website, so its `X-Forwarded-Proto` (HTTPS) and `X-Forwarded-For` (sign-in limits) are trusted from this network only. Public, loopback, host-bit and wider-than-/16 networks are refused. |
| HTTPS | `SECURE_SSL_REDIRECT`, HSTS for 1 year with subdomains | Plain HTTP is redirected; browsers remember to use HTTPS. Preload is deliberately off (hard to undo), so `security.W021` is silenced on purpose. |
| Cookies | `__Host-ucc_session`, `__Host-ucc_csrf` | Browsers accept `__Host-` cookies only over HTTPS, for this exact host and path `/`, so no subdomain can set or replace them. HttpOnly, SameSite=Lax and the 30-minute session stay. |
| Static files | WhiteNoise after `SecurityMiddleware`, `CompressedStaticFilesStorage` | CSS/JS are served (with gzip copies) before any database work. Not the manifest storage: `site.js` loads `app.js` and `reminders.js` by name. |
| `UCC_STATIC_ROOT` (optional) | where `collectstatic` writes | Set by the server image in step 2. |

Run it with gunicorn: `gunicorn config.wsgi:application` with
`DJANGO_SETTINGS_MODULE=config.settings.web_production`, after running `collectstatic`.

`manage.py check --deploy --settings=config.settings.web_production` reports exactly one issue:
**`accounts.E105`**. That is intended: without a reviewed real-email backend, sign-up and
password-reset links would only reach the server log, so the profile cannot start until step 4.

Packages: `gunicorn==26.2.0` (the stable line; 27.0 was a week old) and `whitenoise==6.12.0`,
locked with hashes in `requirements-django-lock.txt`. Neither adds other packages.
`pip-audit` reports no known vulnerabilities.

Tests: `server/web_tests/test_production_profile.py` checks, in fresh processes, the deploy
check (only E105), every HTTPS/cookie/host/proxy value and the middleware order; that unsafe
`UCC_SITE_HOST`/`UCC_TRUSTED_PROXY` values stop startup without printing details; that HTTP is
redirected and unknown hosts are refused before any database work; that static files are
served with HSTS and `nosniff` without the database; that sign-in limits read the visitor's
address only through the trusted proxy; that gunicorn loads the app; and that the local
starter still refuses this profile.

## Step 2: server package

Everything lives in `deploy/`; the owner's steps are in [SERVER_GUIDE.md](SERVER_GUIDE.md).

| File | What it does |
| --- | --- |
| `compose.yml` | Four services. `db`: PostgreSQL 17.12 on an internal network with no internet and no published port. `migrate`: a one-off container with the migrator login only (`docker compose run --rm migrate`). `web`: the website (no published port, read-only file system, unprivileged user, no Linux capabilities, `no-new-privileges`). `caddy`: Caddy 2.11.9, the only service with ports (80/443), at the fixed address `172.30.0.10`. |
| `Dockerfile` | Python 3.12.16, `pip install --require-hashes --only-binary=:all:` from `requirements-django-lock.txt`, `academic_logic.py` and `server/` (tests excluded), `collectstatic` at build time with placeholder values used for that command only. `/.dockerignore` allows only these files, so secrets and data never enter the image. |
| `start-web.sh` | Preflight `manage.py check --deploy --fail-level WARNING` (so `accounts.E105` and every other check must pass), then gunicorn with threaded workers (AI answers can take up to 60 s) and **no access log** (request lines can contain one-time tokens). |
| `provision.sh` | `migrate`, `configure_auth_role` and `configure_runtime` with the offline migration settings. |
| `postgres-init.sh` | On first start only: the migrator, runtime and auth roles (`LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`) and the `ucc` database owned by the migrator, like the local setup. |
| `Caddyfile` | Answers only for `UCC_SITE_HOST`, automatic HTTPS and `http://` redirect, `admin off`, 11 MB request limit, removes the `Server` header, and replaces visitor-sent `X-Forwarded-For`. |
| `make_secrets.py` | Creates `deploy/secrets/{db,migrator,web,caddy}.env` once (folder 0700, files 0600, created exclusively, nothing printed). The website file has only the runtime and auth logins; the migrator file has only the migrator login. `UCC_TRUSTED_PROXY` is Caddy's exact address, `172.30.0.10/32`. |

Image versions are pinned (`postgres:17.12`, `caddy:2.11.9`, `python:3.12.16-slim-bookworm`);
update them deliberately, one PR at a time.

Tests:
- `tests/test_make_secrets.py`: four private files, separate logins per service, all passwords
  different and long, nothing secret printed, never overwrites, bad host/email refused.
- `tools/test_server_package.py` (CI job `server-package`; needs Docker and ports 80/443): builds
  the image, starts the database, runs `migrate`, confirms the real start command **refuses**
  with `accounts.E105`, then (smoke run without the preflight only) checks through Caddy with an
  internal test certificate: a full student journey (register, confirm the email link, sign in,
  add a semester and course, see the 5.00 GPA) on the restricted logins; the three roles have
  no superuser/bypass rights and the migrator owns the database; containers are locked down,
  only Caddy has ports, the database network is internal and Caddy cannot even resolve `db`,
  the website has no migrator or admin login; HTTP redirects to HTTPS; HSTS, CSP, frame,
  `nosniff` headers, no `Server` header and `__Host-` cookies; compressed static files; other
  host names get nothing; 12 MiB uploads get 413; and forged `X-Forwarded-For` values cannot
  dodge the sign-in limit.
