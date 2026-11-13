# B1c implementation and evidence

## Scope and implementation plan

Owner work order: proceed with B1c after the approved PR #54 design at
`5a8429a456a0fe7d8be25c51dfc16fd5f6eb3753`. Base master:
`e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6`.

1. Reuse the B1b bounded walker, classify guarded instance SQLSTATEs, preserve
   handled role/academic contracts and classify adapter failures as minimal500.
2. Add constant responses, strict synthetic Retry-After5 configuration and both
   URL roots' view/response exception adapters. Preserve original400 handlers.
3. Extend exact typed-event category mapping without loosening B1b output.
4. Execute B/C, A2/A5 and A3/A4 reset/verify gates on restricted PostgreSQL17;
   preserve regression, browser, migration, audit and B1a/B1b mutation evidence.
5. Publish a draft implementation PR; stop for separate independent code review.

This is B1c only, not B1 complete. B1d uncertain-outcome wording, retries, session
lifecycle changes, quotas/devices, email approval, grants/RLS and deployment are
excluded. Synthetic data only. Evidence below will distinguish execution from plan.

## Delivered code

- `failure_classification.py`: frozen six-category results, whole-bounded-walk
  SQLSTATE precedence, guarded psycopg instance reads, no duplicate walker.
- `failure_response.py`: constant UTF-8 plain text, no template/request/DB access,
  no-store, category-specific Retry-After and strict synthetic 5-second setting.
  Ordinary builder failure retains status, charset and headers. Failure of the
  fallback follows Django's existing exception path; process controls propagate.
- `failure_handlers.py` and both URL roots: active-exception500 and explicit400
  adapters. Django-only400 and non-database existing handlers are preserved.
- `AuthFailureMiddleware`: immediately after AuthenticationMiddleware, view
  exceptions only. Proven availability/configuration errors get503. Exactly one
  fixed typed event per consumed failure; ordinary classifier failures get500 and
  a DEFECT event without raw details. Handlers emit no additional typed events.
- `logging.py`: explicit exact-enum category serialization; B1b SQLSTATE output
  masking, single-write/re-entry behavior and exception walker remain unchanged.

Successful authentication/session code, academic wrappers/formulas, role checks,
models, migrations, grants and RLS are unchanged. The synthetic Retry-After setting
is validated during `auth_common.configure`; an operator may supply it in a future
reviewed settings module before calling configure. No environment-driven production
policy, retry mechanism or new security activation flag is introduced.

## Acceptance coverage and reproduction

Use Python3.12 and `requirements-django-lock.txt` with `--require-hashes`. Follow
[authentication test role setup](../AUTHENTICATION.md) and the exact commands in
[quality.yml](../../.github/workflows/quality.yml). Set only disposable synthetic
secrets. All application requests execute with separate auth/runtime logins.
The test migrator provisions schema/context/grants as before. The historical
33 model tests retain CI's disposable DBA fixture arrangement; they do not prove
RLS. The46 security tests use restricted roles and forced RLS.

The test-only `UCC_TEST_DBA_USER` is used exclusively to terminate an actual auth
backend in explicitly disposable `test_*` databases. No DBA credentials are added
to application settings and no privileged production SQL is added. CI already uses
runner-local trust for the disposable DBA; production provisioning is not covered.

```sh
python server/manage.py test auth_tests --settings=config.settings.auth_test -v 2
python server/manage.py test auth_tests.test_b1c_classification auth_tests.test_b1c_database auth_tests.test_b1c_transactions b1c_negative_controls --settings=config.settings.web_test -v 2
```

Set `PYTHONPATH=tools` for the mutation module. The workflow keeps all four jobs
and existing restricted-role steps, and adds the B1c website-root step. Its existing
15-minute database timeout and read-only GitHub permissions are unchanged.

| Gate | Concrete evidence |
| --- | --- |
| B: classification and routes | `test_b1c_classification` covers all six categories, exact valid states, every nominated unknown OperationalError family, no-state drivers, precedence, mismatches, opaque/groups/suppression/cycles/16-node bounds and hostile attributes. `test_b1c_database` drives real account and response-save paths. |
| B: PostgreSQL faults | Real55P03 session row lock, real42703 renamed session column with finally restoration, real57014/25P03 configured timers and reconnect, actual auth backend termination, local TCP relay loss with no state; both roots. |
| B: preserved contracts | Real concurrent session deletion remains400; BadRequest, role-guard ProgrammingError503, academic API503 and registration generic success remain handled. No-state Django errors remain unproven rather than false outages. |
| C | All aliases captured at zero renderer queries; forbidden identity/template/reverse access; fallback status/no-store/charset/category-header assertions; recursive failures through Django, direct handler500, debug behavior and process-control propagation. |
| A2 | All N/AN/SA/SX/DA response UPDATE/exists/INSERT faults, last_login fault, pre-COMMIT rollback, real-COMMIT-then-error, real-save-then-error; fresh auth observers assert rows, authority and expiry. Existing B1a L0/L1 throttle/Student locks and CAS/autocommit persistence remain. Real termination synchronized before finalizer COMMIT uses SA. |
| A5 | Existing real Student lock plus flush DELETE fault, pre-COMMIT cookie deletion with prior server key valid, real-COMMIT-then-error with password/session deletion persisted. No compensating writes. |
| A3/A4 S1/E1–E3 | Reset N/SA and verify N, Student-write/token-write faults, real Student and AccountToken locks, pre-COMMIT rollback versus real-COMMIT acknowledgement loss. Token consumption/password or verification updates are checked together; same-plaintext reset separately proves that password validity is not unchanged encoded-hash/session authority. |
| D | Final sink bytes omit token/password/header/cookie/IP/SQL/traceback sentinels; typed event count/category/unknown-code masking and separate Django response records asserted. B1b tests retained. |
| Negative controls |18 B1c production mutants: instance-read removal fails actual routing; wrong pass order/outage/config sets/bound/opaque gate; missing cache/charset, incorrect Retry-After/coercion, template access/process-control swallowing; defect400, unproven503, missing/duplicate typed events/category serialization/log-mask leakage. Runner self-tests reject no-op/unexercised/error/skipped/bad-baseline results. Existing15 B1a and14 B1b controls retained. |

Mutation results require a passing baseline, proven production-path exercise,
assertion failure, and no errors/skips. A missing-header mutant initially caused a
KeyError: it was correctly rejected as an invalid detection. New tests now assert
header values explicitly. No test is skipped to obtain a pass.

## Intentional historical assertion updates

B1a/B1b request tests previously asserted the pre-B1c400/500 for real55P03/57014.
Only those status expectations become503. A consumed view outage no longer fires
Django's `got_request_exception`; its historical signal expectation becomes empty,
while the actual failing statement/55P03 assertion remains. New sink tests prove
typed outage emission. Prior-key/expiry, no-new-cookie, password/CAS/throttle
persistence, rollback, RLS and privilege assertions are retained. Bare Django
no-driver failures still keep their original unproven400/500 expectations.

## Local execution and limits

Disposable localhost PostgreSQL17, fresh separated roles and no real student data.
Legacy113, foundation33, isolation46, website91 and browsers10+5+12 passed locally;
dependency audit found no known vulnerabilities; migration drift found no changes.
Final B1c focused runs and baseline controls are recorded in the draft PR alongside
hosted exact-head job/log evidence. The completed implementation adds39 auth tests
to the existing201 (240 total;523 regressions across all suites), plus the separate
website-root executions and mutation runner cases. Actual CI totals take precedence
if discovery differs; no planned test is claimed executed before a completed run.

Exploratory failures were test-fixture defects: auth-only templates unavailable for
web rendering, anonymous rows incorrectly assumed absent, committed logout wrongly
assumed to preserve its prior row, protected token fixture deletion ordering, and
recursive-renderer assertions incorrectly assuming the minimal variant. They were
investigated against Django/session source and corrected with explicit state/route
assertions. Initial browser/audit launches used unwritable/missing default cache
locations; reruns used existing Playwright assets and a writable audit cache.

### Residual risk and independent review

No B1-complete or production-readiness claim. Connection timers do not bound HTTP
or COMMIT. Statuses do not prove rollback: writes may persist after an undelivered
response, an old session may remain valid, and logout deletion headers are allowed.
Termination synchronized before COMMIT proves that observed rollback case; the
separate real-COMMIT-then-error controls prove persistence. This does not reproduce
every network/COMMIT race in a production topology. Same-secret and prior-session
outcomes must not be inferred from plaintext password changes alone.

Opaque provenance, resource exhaustion, fallback/server output, preserved academic
503/template behavior and existing400 templates remain documented risks. Timing
samples are evidence only, not an enumeration-resistance or latency-SLA proof.
Stage C tuning/operational logging, B1d wording/full remaining matrix, email recovery,
backups/restoration and security activation remain separate gates.

Codex authored this implementation and the PR #54 proposal and participated in
B1b. Request Claude's independent **code** review, with its prior design involvement
disclosed; neither self-review nor green CI is independent approval. Review must
compare the actual phase/state coverage above against the approved gate before
owner merge authorization.

Rollback: revert this B1c code/settings/URL/category delta and restart trusted
synthetic development, retaining B1a/B1b, schema, roles and stored sessions/data.
No migration reversal, credential rewrite, retry or compensating data operation.
