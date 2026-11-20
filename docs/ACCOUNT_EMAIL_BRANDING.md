# Account email branding and the UC favicon

Scope: presentation only. The owner requested a favicon and selected **branded OTP
emails**, rather than SMS/WhatsApp, on 20 November 2026. Implementation source base:
`e164b39ef490f2a4cf206660d169f3f3dbff84f5`.

## Browser identity

The existing Academic Studio UC mark uses the approved primary green `#176B5B`
and white. The source is `accounts/static/accounts/brand/favicon.svg`; a two-size
16/32 px ICO fallback and 180 px Apple touch icon are exported from that vector.
No fonts, external scripts, services or new dependencies are required by the website.

The shared `accounts/base.html` links the same-origin assets, covering normal public,
authentication and workspace templates. Existing template-free security failures and
sandboxed downloads are untouched. The existing CSP and response headers are unchanged.
Link-level `referrerpolicy="no-referrer"` is best-effort: native favicon implementations
can ignore it. This feature does not claim to eliminate the pre-existing need to redact
sensitive paths/headers in operational logs. No identifier or secret is added to icon URLs.

The offline exporter uses the already locked test-only Playwright tooling:

```sh
python tools/build_brand_icons.py
```

Install browser-test dependencies and Chromium through the existing documented browser
setup first. `UCC_CHROMIUM_EXECUTABLE` explicitly selects a local browser when necessary.
Rasterisation/PNG bytes can vary with the browser version; SVG is the authoritative source.
No encoder or imaging library is added to the application. Browser favicon caches may need
a refresh/reopened tab after a separately authorized release.

## Branded account messages

`accounts.email_content.branded_html` renders one fixed, self-contained HTML template.
It has an inline-style UC header, selectable code block, original message, optional account
action and privacy reminder. It contains no remote image, stylesheet, font, tracking pixel,
script, form or attachment. User-controlled template names/markup are not accepted.

- Sign-up verification codes get the code block and existing verification-page link.
- Email-change codes get the code block; the old-address confirmation remains a separate
  notification, without the new-address code.
- Existing verification/recovery links receive the same shell and their unchanged link.
- The unrelated account-deletion email remains unchanged in this increment.

Every email retains its existing plain-text body, subject, sender and recipient. The HTML
is an additional MIME alternative, not a replacement. No student name/profile information
is added. HTTP/HTTPS action URLs are escaped; malformed/non-web schemes are not rendered
as action links. Actual URLs still come only from existing trusted account-link generation.

If HTML rendering fails with an ordinary Exception, a fixed generic warning is emitted
without exception details/payloads, and the original plain-text email is still sent.
An ordinary logger/sink failure cannot suppress that plain-text fallback either.
Existing SMTP failure handling stays generic. Process-control exceptions propagate as
before; the formatter does not catch BaseException. Presentation performs no network I/O.

## Security contracts preserved

- The same approved ReviewedSMTPBackend, host allowlist, verified STARTTLS, timeout,
  configured sender and one-recipient rule remain in force. No provider/domain/DNS change.
- Code generation, HMAC storage, expiry, attempts, retirement/replay handling, transaction
  boundaries and send-after-commit scheduling are unchanged. Sign-up remains six digits,
  one minute and five attempts; email change remains ten minutes and five attempts.
- Login, reset/change validation, sessions, generic public responses, throttles, RLS,
  privileges and academic calculations are unchanged. No login OTP or MFA is introduced.
- No new database field, migration, grant, secret, phone number or messaging credential.
- The existing subjects include OTPs. This compatibility behaviour remains; subject/lock-
  screen exposure is an existing limitation, not a claim of notification secrecy. Removing
  codes from subjects would be a separately reviewed presentation/policy change.

No new outside service/processing region, stored data or cookie is introduced, so there is
no privacy-notice/LEGAL_UPDATED change in this presentation increment. This is not a broader
privacy-compliance claim or authorization to deploy or send real test messages.

## Tests and visual evidence

Nine new database-free SimpleTestCase tests exercise MIME alternatives, exact plain-body/
subject/recipient preservation, separate new/old-address messages, leading-zero codes,
escaped text/URLs, no remote assets, renderer fallback with sentinel-safe logs, unchanged
SMTP error handling, compounded renderer/logger failure, process-control propagation,
shared-template icons and bitmap formats.

For this one DB-free module only, the ordinary Django runner can skip the project's
database-provisioning runner, with the usual synthetic auth-test settings/environment:

```sh
python server/manage.py test auth_tests.test_email_presentation --settings=config.settings.auth_test --testrunner=django.test.runner.DiscoverRunner -v 2
```

Do not use that runner override for database/security suites. Full hosted auth_tests,
web_tests and isolation tests retain their existing PostgreSQL 17 separated-role runner.
No SQLite inference or local database verification is claimed for the nine unit tests.

Two browser tests join the existing UI1 suite. Native icon decoding uses real loopback-
only static HTTP, the existing CSP and JavaScript disabled, for public/workspace shells.
It requires all three images to decode and observes no outside-origin requests. An initial
Fetch-routing fixture returned a broken ICO image because Chromium/Playwright interception
special-cases favicon loading. The same valid assets passed without interception; no
timeout was extended and image-decoding assertions were retained. Do not reuse a mocked
favicon transport as proof that the real icon cannot load.

Email previews reflow at 320/390 px with 100% and 200% text, use no page JavaScript or
external resources, and retain the visible code/expiry. Existing focus, responsive and
academic browser assertions are unchanged. Run all browser suites and existing regression,
PostgreSQL, dependency, packaging and generated-SQL checks through normal quality CI.
The implementation PR records exact-head results, actual counts, failures and skips.

Synthetic previews only; **012345 is not a valid account code**:

- [390 px email preview](design/evidence/account-branding/otp-email-390-text-100.png)
- [320 px, 200% text](design/evidence/account-branding/otp-email-320-text-200.png)

Local browser evidence used Chromium 156.0.8078.79 / Playwright 1.65.0 via the explicit
system-browser override. Hosted CI uses the existing hashed browser lock. Chromium HTML
previews do not certify Gmail/Outlook/Apple Mail, client dark-mode transformations or inbox
placement. The plain-text alternative remains usable if a client strips the HTML/styles.

## Release and rollback

No live database operation or new email-provider setup is needed. Separate independent
review, owner merge decision and release authorization remain required. No real OTP email
was sent during tests. Reverting the code/templates/static assets together removes this
presentation; no database, secret, code-expiry or session rollback is needed.
