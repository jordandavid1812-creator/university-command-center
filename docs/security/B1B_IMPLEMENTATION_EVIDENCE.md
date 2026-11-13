# B1b implementation — independent-review handoff

## Scope and exact sources

Base: `a505d6b1f471a18a16e17fa3bb74461d6ad62061`, the merge of design PR #52
head `233a56b66c5f7e0ab33d24b801781dbef5058405`. Before implementation, GitHub
confirmed that merge and all four completed-success jobs of master **push**
[run 43373861533](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43373861533).
This was the required baseline gate, not substitution of old PR CI.

Authority: the project owner's separate **B1b IMPLEMENTATION WORK ORDER** in this
conversation. The merged [amendment](B1B_LOGGING_DESIGN_AMENDMENT.md), including
N1–N4 and D-B1-4(a–f), and [Revision 5](STAGE_B_IMPLEMENTATION_PLAN.md) govern scope.
Their earlier “no implementation authorized by this document” language is a
historical authorization boundary, not a denial of that later explicit work order.

B1b implements only diagnostic privacy. No B1c/B1d, new response/status/cookie or
session policy, request middleware, classifier, authentication change, schema,
migration, grants/RLS, academic change, device activation or email transport.
Existing historical tests and B1a mutation source are unchanged. No new dependency.
No deployment, staging, real student data or provider approval.

## Implementation map

| File | Purpose |
| --- | --- |
| accounts/exception_chain.py | Pure 16-node allowlisted walk; cause/suppression/cycles/opaque boundaries; exact identity labels; known-class SQLSTATE before instance data; no diagnostic fallback |
| accounts/logging.py | Fresh safe record and fixed-label sink, one write, re-entry/failure handling; exact-type plain-Enum FailureEvent; contained main/thread/unraisable hooks |
| accounts/log_privacy.py | Protected settings policy, early lastResort/hooks, exact graph/identity validation; empty backend approval tuple |
| accounts/apps.py | Preserve original E101 import; independently load privacy/secure checks; enforce startup graph |
| accounts/checks.py | E102–E105; E104/E105 ordinary secure checks, E105 exact class identity/import failure rejection |
| config/settings/auth_common.py, auth_secure.py | Early policy call and explicit secure flag; web profiles inherit; excluded profiles untouched |
| auth_tests/test_b1b_logging.py | Positive sink bytes, sentinels/types/failures, route table, source audit, bounded walker/SQLSTATE |
| auth_tests/test_b1b_profiles.py | Fresh profiles/commands, early window, R5-T2, E105, original exit semantics, all-BaseException faults and raw-output boundary evidence |
| auth_tests/test_b1b_integration.py | Existing HTTP error paths, real PG lock/statement/idle errors at the sink; no status/session changes |
| tools/b1b_negative_controls.py | Isolated production mutations, baseline/exercise/assertion/error checks and runner self-controls |
| .github/workflows/quality.yml | Additional website-root B1b/mutation execution under existing separated roles; permissions and dependency installation unchanged |
| docs/AUTHENTICATION.md | Profile/check/operational/rollback contract |

The root handler never reads getMessage/args, formats tracebacks or uses arbitrary
formatters/default handleError. Safe records retain no request/exception extras.
Each hook catches all BaseException failures from extraction through cleanup; the
normal handler still propagates process controls. Helpers import without models,
settings recursion or database access. Configuration/labeling adds no DB reads.

E105 remains intentionally blocking in secure profiles: the approved tuple is
empty. A positive test temporarily patches it with a no-network fixture; that is
not approval of locmem, SMTP or any provider. Actual backend choice/delivery needs
its own gate. Both normal check and check --deploy report E105. Checks are not an
automatic WSGI barrier. See the operational guide for preserved raw-output risks.

## Reproduction and acceptance evidence

Use Python 3.12 and all existing hashed locks. Local tooling uses the existing
venv; disposable PostgreSQL 17 has distinct migrator/auth/runtime LOGINs, no
privileged application alias, and no production or personal records. The fixture
administrator creates roles/DB only; original restricted-role runners provision
existing grants. Fresh subprocesses use private inherited synthetic settings.

```sh
python -m unittest discover -v
python server/manage.py test accounts academics --settings=config.settings.test -v2
# Existing disposable cluster bootstrap; never run against persistent data:
python tools/prepare_security_test_roles.py
# Remaining DB commands use fixture migrator + separate auth/runtime credentials.
python server/manage.py test security_tests --settings=config.settings.security_test -v2
python server/manage.py test auth_tests --settings=config.settings.auth_test -v2
python server/manage.py test web_tests --settings=config.settings.web_test -v2
PYTHONPATH=tools python server/manage.py test auth_tests.test_b1_settings auth_tests.test_b1_database auth_tests.test_b1_sessions auth_tests.test_b1_measurements b1a_negative_controls --settings=config.settings.web_test -v2
PYTHONPATH=tools python server/manage.py test auth_tests.test_b1b_logging auth_tests.test_b1b_profiles auth_tests.test_b1b_integration b1b_negative_controls --settings=config.settings.web_test -v2
python tools/test_frontend_foundation_browser.py -v
python tools/test_premium_auth_browser.py -v
python tools/test_dashboard_browser.py -v
python -m pip_audit --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt -r requirements-django-lock.txt -r requirements-browser-test-lock.txt
python -m pip check
python server/manage.py makemigrations --check --dry-run --settings=config.settings.auth_migration
python tools/check_repository_safety.py
git diff --check
```

Use separate test DB names for concurrent suites. Cache directories may need a
private writable path in a sandbox; this does not change audit scope. No
--debug-sql, real network delivery or sensitive request/log output is published.
The draft PR records its exact commit, executed counts, versions and hosted run.
Historical run counts are not substituted for this implementation's evidence.

## Local executed results

All final local suites passed, without skips: legacy **113**, foundation **33**,
restricted-role security **46**, authentication **201**, website **91** = **484**
regressions. This preserves every one of the 455 baseline methods and adds **29**
B1b methods: 14 sink/walker, 11 profile/hook and 4 request-integration methods.
Additional executions: original B1a website-root **27** (15 mutations) and new
B1b website-root **34** (29 duplicated B1b methods plus five control-runner methods,
**14/14 production mutations detected** and three expected runner-guard rejections).
No real mutation escaped or counted an infrastructure error as detection.

Browsers: UI1 **10**, premium-auth **5**, UI2 **12** = **27**, all passed.
Audit of all three hashed locks: no known vulnerabilities. pip check, migration
drift, AST/YAML syntax, documentation links, repository safety and whitespace pass.

Local versions: Python **3.12.14**, Django **5.2.19**, psycopg **3.3.8**, cached
PostgreSQL **17.11** (server_version_num 170011), Playwright **1.65.0** and Chromium
**158.0.8127.18**. Hosted exact-head run/version evidence is recorded in the draft
PR after completion; it is distinct from these local results. No SQLite security
assertions. Browser-only synthetic fixtures are not PostgreSQL isolation evidence.

## Required negative and mutation evidence

Sink tests assert both positive non-empty fixed-label output and sentinel absence:
password/reset/verify path, encoded/query/metadata, cookie, authorization, IP,
message, exception, SQL/traceback/extras. They verify original record/request
identity/content, root/child/lastResort propagation, 400/500/403/404 routes and real
55P03/57014/25P03. Walker tests include groups, opaque boundaries, 16/17 nodes,
cycles, suppression, cause priority, subclass/str/repr traps and malformed/missing/
raising class SQLSTATE access, without instance diagnostics.

Each of main/thread/unraisable hooks has original-exception and injected
KeyboardInterrupt/SystemExit/GeneratorExit/Exception emission tests. Tests cover
stream/guard-entry/guard-cleanup failure, no original-secret/fallback traceback,
main non-zero exit, thread-only termination, original SystemExit/interrupt semantics
and finalizer weak-reference release. Known raw server/command/unittest/bootstrap
outputs are **expected bypass evidence**, never called sanitized. All data synthetic.

R5-T2 injects unsafe handler/filter/formatter through LOGGING so dictConfig cannot
erase it, or changes a hook immediately at ready's guard boundary. The test proves
object presence before rejection. Guard-removal mutation must fail that oracle.
Historical assertLogs('accounts.tokens') remains untouched; it is test-only runtime
handler installation, not permission for application reconfiguration.

Fourteen production mutations are required, not test-alias rewrites:

- Raw message copying and request retention.
- Loose typed-event acceptance and unapproved email acceptance.
- Arbitrary formatter use and missing re-entry guard.
- Startup guard removal (R5-T2) and logging helper removal.
- E104 and E105 incorrectly made deploy-only (two controls).
- Early lastResort incorrectly deferred until ready.
- Unsafe BaseException propagation from main/thread/unraisable hooks (three).

In-memory controls have hit counters and restored patches. Disposable-copy
controls require exact-once replacements and verified import origins, then discard
the copy. Every target must pass unmutated; a mutant must be exercised and cause
an assertion failure, with no infrastructure error. No-op, unexercised and error
results are explicitly rejected by the actual runner judge (expected self-control
output captured, not counted as undetected real mutations). Original B1a's 15
controls run unchanged in a separate step.

## Investigations and limits

Initial new-test fixture errors were a syntactically invalid formatter fixture and
psycopg's constructor reading an intentionally trapped property. Fixtures were
corrected without weakening assertions or production behavior. A new raw-output
boundary fixture initially passed three positional arguments to wsgiref.log_exception
instead of its single exc_info tuple; its TypeError correctly reached the safe
hook. The fixture now calls the real raw-output path and retains its raw-sentinel
expectation. An initial unsafe
thread-hook mutant was masked by another safe hook: the actual-process privacy
oracle alone did not prove direct containment. Its target now requires direct
hook return under stream/guard faults; unsafe thread/unraisable propagation is
therefore detected rather than falsely accepted. Preliminary failed runs are not
reported as acceptance. Intentional mutant leaks stay captured in synthetic child
results, not committed logs or reported as production privacy failures.

Remaining limits: snapshot graph mutable by arbitrary Python; dependency/operator
changes need review. Raw bootstrap/command/server/test/fatal/SystemExit/email and
external sink boundaries persist. Partial writes cannot be retracted; stream I/O
can block; fixed labels reduce diagnosis. B1c/B1d, safe external logging/retention,
email/recovery, backups, provider deadlines and staging remain incomplete.

Rollback: stop serving, revert B1b modules/config/check wiring, restart processes
to restore original hooks/graph. No database reversal or compensating session/
password writes. Reverting restores less-private logs; keep synthetic/local only.
Stop for independent Claude Code review (disclose that Claude authored Revision 5
and the review findings; Codex authored this implementation). No self-review is
independent approval. No merge or further milestone is authorized here.
