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

1. **Production settings** (this step): `config.settings.web_production`, gunicorn, whitenoise.
2. Server package: Docker Compose for website + PostgreSQL + Caddy, and a step-by-step guide.
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

Notes for step 2: Caddy must answer only for `UCC_SITE_HOST`, set `X-Forwarded-Proto`, replace
any client-sent `X-Forwarded-For`, cap request bodies to match the 10 MiB upload limit, and the
website container must publish no port.
