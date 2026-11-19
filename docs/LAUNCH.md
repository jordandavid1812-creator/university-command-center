# Launch: invited trial

The owner approved putting the website online for a small, invited group of classmates.
This page records the plan and what each step added. It is built one small PR at a time.

## Decisions

**Update (owner's choice):** the database moves to **Supabase** (set up with numbered SQL files in
its SQL editor, RLS on every table) and hosting to **Vercel**; big study files will go to
**Supabase Storage** with storage-only keys. The step 2 server package stays as a tested backup
option. See [SUPABASE_GUIDE.md](SUPABASE_GUIDE.md) and [VERCEL_GUIDE.md](VERCEL_GUIDE.md). Steps: Supabase
database (done), Vercel hosting (done), real email, big uploads to Supabase Storage, AI limits, account
deletion and email change, privacy page and terms, backups.

Original decisions:

- **Audience:** invited classmates first (about 5–20), then wider only after a review.
- **Budget:** about $5–15 a month: one small cloud server (DigitalOcean recommended) running
  the website, its own PostgreSQL 17 and Caddy (automatic HTTPS), plus off-server backups.
- **AI tools:** the owner's shared key with a small daily allowance per student and a
  site-wide daily cap.
- **Address:** the owner's own domain name.

## Steps

1. **Production settings** (done): `config.settings.web_production`, gunicorn, whitenoise.
2. **Server package** (done): Docker Compose for website + PostgreSQL + Caddy, and a step-by-step guide.
3. **Invite-only sign-up** (done), later replaced on the public site by **open sign-up with an
   emailed 6-digit code** (see "Open sign-up" below).
4. Real email through a reviewed SMTP backend (done: Gmail through `ReviewedSMTPBackend`, which
   lifts the `accounts.E105` gate; see "Step C: real email" below).
5. AI limits for the shared key (done: 10 per student and 200 for the site per day; see
   docs/AI_STUDY_ASSISTANT.md "Limits for the shared key").
6. Account deletion and email change (done; see "Account deletion" below and "Email change (launch step F, part 2)" in docs/AUTHENTICATION.md).
7. Privacy page and terms (NDPA) (done: `/accounts/privacy/` and `/accounts/terms/`; see "Privacy notice and terms" below).
8. Backups and a tested restore (done: daily encrypted backups through GitHub Actions; see docs/BACKUPS.md).

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


## Open sign-up with an emailed code (replaces invite-only sign-up on the public site)

The owner chose to let anyone with an email address create an account. To stop fake or
mistyped addresses, the account works only after the student types the **6-digit code** the
site emails them. Public profiles set `UCC_SIGNUP_CODE = True` and `UCC_REQUIRE_INVITE = False`;
system check **`accounts.E106`** now refuses a public profile without email codes. The local
website keeps the original email-link flow, so nothing changes there.

- **Flow:** Register → the "Enter your code" page opens with the email filled in → type the
  code from the email → "Email confirmed. You can now log in." The page has one form with two
  buttons, **Confirm email** and **Send me a new code**, so it works without JavaScript. It is
  also at `/accounts/verify/code/`, and "Resend verification" sends a new code.
- **Limits:** each code works for **1 minute** and allows **5 tries** (the database refuses a
  sixth). A new code retires the old one. Typing a code is limited to 20 per hour per address
  (`verify-code`), and new codes to 5 per hour (the existing `resend` limit); sign-up keeps its
  limit of 5 per hour.
- **Storage:** only an HMAC-SHA256 of the code, keyed with the site's secret key, is stored
  (`accounts_signupcode`, migration `accounts.0005`), so a copy of the database cannot be used
  to work codes out. Old codes are removed by `clear_auth_artifacts` a day after they expire.
- **Privacy:** every reply is the same whether or not the email has an account, is already
  confirmed, or was mistyped; duplicate sign-ups get the same page and no email.
- **Database rights:** the auth role may `SELECT`, `INSERT`, `DELETE` and `UPDATE` only
  `attempts` and `consumed_at` — never who a code belongs to, its digest or its times. The
  runtime role has no access. Any extra or missing grant stops the website
  (`accounts.boundary.INVITE_TABLES`).
- **Supabase:** `supabase/migrations/0004_schema.sql` and `0005_security.sql` add the table,
  its grants and row-level security.

Tests: `auth_tests/test_signup_codes.py` (13, real PostgreSQL with the separate roles), plus the
public-profile, Docker server and Vercel/Supabase journeys, which now sign up with a code.

## Step 3: invite-only sign-up (no longer used on the public site)

On the public site (`UCC_REQUIRE_INVITE = True` in `web_production`; system check
**`accounts.E106`** refuses a public profile without it) the Register page asks for an
**invite code**. The local website is unchanged (no code needed).

- **Codes:** `ABCD-EFGH-JKMN-PQRS-TVWX` — 20 characters from 30 easy-to-read letters and
  digits (no 0/O, 1/I/L, U), about 98 bits of randomness. Typing is forgiving about case, spaces
  and dashes. Only a SHA-256 digest is stored (`accounts_invitecode`, migration
  `accounts.0004`), so codes cannot be read back from the database. Each expires (default 14
  days, at most 60) and works once.
- **Using a code:** checked only when the rest of the form is valid, then used up in the same
  `auth` transaction as the new account, under a row lock, so a failure leaves it unused and two
  people cannot use one code. A duplicate username or email still uses the code and gets the
  same generic reply, so a code cannot be replayed to discover accounts. The existing sign-up
  limit (5 per hour per address) applies before any code is checked.
- **Database rights:** the auth role may only `SELECT` codes and `UPDATE (used_at)` — no insert,
  delete or other columns. The academic runtime role has no access. Both are enforced by the
  existing exact-allowlist checks (`accounts.boundary.INVITE_TABLES`): any extra or missing
  grant stops the website (503) before it serves a request.
- **Owner command** (migrator login only, in the one-off `migrate` container):

  ```bash
  docker compose -f deploy/compose.yml run --rm migrate python manage.py invites create --count 3 --note "Class rep"
  docker compose -f deploy/compose.yml run --rm migrate python manage.py invites list
  docker compose -f deploy/compose.yml run --rm migrate python manage.py invites cancel 4
  ```

  `create` shows the codes once (1–50 at a time, optional note of up to 60 characters); `list`
  shows number, status (unused until / used / expired) and note, never codes; `cancel` ends an
  unused code. No personal details are stored with a code beyond the owner's optional note.

Tests: `auth_tests/test_invites.py` (18, real PostgreSQL with the separate roles): code shape,
randomness and digest-only storage; the form field; missing, wrong, malformed, expired and
cancelled codes create nothing; a code works exactly once; forgiving input; other form errors
and a failed account creation leave the code unused; a duplicate username uses the code with
the generic reply; the sign-up limit still applies; the local site asks for no code; E106;
the auth role can only read and mark used; the runtime role cannot read; six kinds of grant
drift stop the website; and the owner command creates, lists (never showing codes), cancels and
refuses bad values. `tools/test_server_package.py` now signs up on the real server with a code
made by the owner command, after a missing and a wrong code are refused.


## Step C: real email

Sign-up and password-reset emails are sent through the website's **own** Gmail account (never a
personal one), using a Google **app password**.

- `accounts.email_backend.ReviewedSMTPBackend` is the one approved backend (check E105 refuses
  every other, including Django's own SMTP backend): only `smtp.gmail.com` or
  `smtp-relay.brevo.com`, port 587 with STARTTLS, verified certificate and host name, TLS 1.2 or
  newer, a 10-second limit, exactly one recipient per message, sent only from the configured
  address. It takes nothing from callers except the empty values `send_mail` passes.
- `public_site.configure_email` (used by `web_production` and `web_vercel`) needs
  `UCC_EMAIL_ADDRESS` (a `@gmail.com` address) and `UCC_EMAIL_APP_PASSWORD` (16 letters; spaces
  as Google shows them are fine). Missing or malformed values stop the website before it starts.
- A delivery failure is logged as one generic line (no address, link or server reply), and the
  visitor still sees the same generic message (no account enumeration).
- With email set, `check --deploy` passes with **no issues**, so the public site can start.
- The owner's helpers ask for the app password hidden: `tools/vercel_env.py --email-address ...`
  (Vercel) or two lines added to `deploy/secrets/web.env` (server package).

Tests: `web_tests/test_email_backend.py` (5, no network: verified STARTTLS before login, one
recipient, refusals, E105 identity, private failure logging); the profile tests now require a
clean deploy check and refuse bad email values; `tools/test_server_package.py` shows the real
start command refusing without email settings and booting after the full preflight with them;
`tools/test_vercel_stack.py` shows `vercel_app.py` starting with email settings and refusing
without; `tests/test_vercel_env.py` covers the hidden app-password prompt.

## Privacy notice and terms (step G)

Two public pages, linked from every page's footer and from the sign-up form ("By creating an
account you agree to the Terms of use and confirm you have read the Privacy notice"):

- `/accounts/privacy/` (`accounts/templates/accounts/privacy.html`): what is kept (account, records,
  files and their text, AI ledger and saved results, hashed security counters), the cookies, why,
  who else handles it (Vercel in Dublin, Supabase in Ireland, Gmail, Google Gemini: only the chosen
  file text up to 60,000 characters and the question, never name, username, email, matric, file
  name or title; free tier may be kept, used and read by Google), retention, NDPA 2023 rights
  (access with Export my data, correction, deletion by email until step F, objection, complaint to
  the NDPC), security, age (under 18 with permission) and changes.
- `/accounts/terms/`: account, content, fair use, estimates and AI accuracy, the free trial "as is",
  ending, Nigerian law.
- Contact and date: `LEGAL_CONTACT` and `LEGAL_UPDATED` in `accounts/views.py`. Change the date
  whenever the wording changes.
- **Keep them true:** any change to what the site stores, its cookies, its providers or where they
  run must update the privacy notice in the same pull request.
- Tests: `web_tests.test_legal_pages`.

## Account deletion (step F, part 1)

**Settings → Delete account** (`/settings/delete-account/`) permanently deletes the signed-in
student's account. The student types their current password and the word `DELETE`; the form works
without JavaScript and is rate-limited (`delete-account`, 5 per hour).

- `ucc_security.delete_my_account()` (migration `academics.0024`, Supabase `0008`/`0009`) takes **no
  arguments**: it deletes only the student proven by the signed transaction context and refuses
  without one. In one transaction it removes that student's rows from every table that refers to
  `accounts_student` (12 academic, 4 sign-in tables), children first, then the account. Explicit
  `WHERE` clauses keep it correct where the owner bypasses row-level security (Supabase).
- Only the website login may call it (`configure_runtime`); it runs with `search_path=pg_catalog`.
  The AI ledger still cannot be deleted directly.
- Afterwards the student is signed out and emailed a confirmation. Encrypted backups keep a copy for
  up to 30 days (privacy notice).
- Tests: `security_tests.test_account_deletion` (including a check that every foreign key to
  `accounts_student` is handled, so a new table cannot be forgotten) and
  `web_tests.test_account_delete`.
