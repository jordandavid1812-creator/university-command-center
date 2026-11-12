# UI1 browser-test dependency policy and reproducibility limits

Test tooling only; never part of the application image or request path. Python 3.12, Playwright 1.65.0. Install **both** the existing Django lock and the new browser-test lock. Do not install Playwright directly from an unpinned dependency expression.

```sh
python -m pip install --require-hashes -r requirements-django-lock.txt
python -m pip install --require-hashes --only-binary=:all: -r requirements-browser-test-lock.txt
python -m pip check
python -m playwright install --with-deps chromium
python -m playwright install --list
python tools/test_frontend_foundation_browser.py --screenshots-dir work/ui1-evidence -v
```

`requirements-browser-test.txt` is the human-maintained input. `requirements-browser-test-lock.txt` pins **Playwright and its complete resolved Python dependency set**, currently greenlet, with SHA-256 hashes generated from the package index. No runtime lock changes. The wheel-only install fails rather than running an unreviewed source build when a platform has no wheel. Hashes constrain downloaded artifacts; they do not prove upstream packages are trustworthy or free of vulnerabilities.

Regenerate with the same repository workflow: Python 3.12 and pip-tools **7.6.2**, reviewing the complete diff. Keep tool installation in a private development environment, separate from application runtime:

```sh
pip-compile --generate-hashes --no-emit-index-url --output-file=requirements-browser-test-lock.txt --strip-extras requirements-browser-test.txt
```

Re-running without an upgrade should preserve the lock; upstream dependency updates require intentional regeneration/review. **Lock changes are review-only:** regenerate only with the command above, in a pull request showing the full lock diff, with the strict hashed `dependency-audit` job passing and independent review. Never hand-edit hashes or regenerate in CI. This is a package-artifact lock, not a hermetic operating-system build. The CI `dependency-audit` job audits **all three hashed locks** (legacy runtime, Django runtime and browser-test) with strict/hash validation; there is no browser dependency audit exemption. No finding is silently ignored. The browser job uses Ubuntu **24.04**, pinned checkout/setup-python actions, the existing workflow-wide `contents: read` permission and `persist-credentials: false`; it has no application database credentials, service-account secrets or deployment authority.

## Browser binaries and OS libraries are a separate trust boundary

The hashed Playwright Python wheel includes its driver/Node runtime and a manifest of browser revisions. `python -m playwright install --with-deps chromium` runs that locked driver's installer. It downloads the matching Chromium/headless-shell and associated artifacts over HTTPS from Playwright's configured distribution endpoints, and installs required Linux packages using the runner's package manager. The package manager can use root on the disposable hosted runner. None of this runs on a deployed application or changes a student's computer.

Important limitations:

- The Python lock's hashes **do not validate browser archives**. Playwright selects package-associated revisions and uses HTTPS/download handling, but this repository supplies no independent browser archive SHA-256 lock/signature verification. CDN availability, upstream release provenance and the locked installer remain trust dependencies. We do not disable TLS validation or configure an alternate download host.
- `--with-deps` invokes apt for system libraries. Repository signatures and Ubuntu's package-management trust apply; exact `.deb` versions and repository snapshots are **not** pinned here. Ubuntu 24.04 hosted images also receive updates. This is not bit-for-bit reproducible CI.
- The existing setup-python action selects the latest available Python 3.12 patch. Local system Chromium selected with `UCC_CHROMIUM_EXECUTABLE` may differ from the Playwright-managed build used by CI. Neither a common package version nor matching image dimensions proves identical rendering.
- pip-audit checks Python advisories, **not** Chromium/Node/OS CVEs, browser provenance or sandbox strength. Keep Playwright and its managed browsers updated through reviewed lock changes; runner updates and browser/OS advisories need separate maintenance. An immutable test image plus independently verified browser digests/OS snapshots is a possible later hardening step, not claimed here.
- Tests render only synthetic HTML and permit no application data or credentials. Installing a browser is not deployment. Do not reuse the test environment as production infrastructure or treat these tests as a penetration test.

CI prints the installed browser inventory and the launched browser version. Screenshot generation additionally records `browser-metadata.json` containing actual executable choice, browser version, Playwright/Django versions and fixture type. Retain that manifest with published evidence; do not label system-Chromium screenshots with a managed-browser version or carry forward an old version by assumption.
