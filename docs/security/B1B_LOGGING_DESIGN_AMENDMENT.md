# B1b logging privacy — proposed design amendment

Status: **DESIGN ONLY; D-B1-4(a–f) PENDING; no implementation authorized.**
Baseline: master `3a4fff14421d8f79422df901027213da75a7cecc` (merged B1a).
This amendment resolves B1B-1–B1B-7 and takes precedence for B1b details that
conflict with [Revision 5](STAGE_B_IMPLEMENTATION_PLAN.md), particularly §6.8,
§6.9, §6.10 D/G, §6.11, §6.12 and D-B1-4. Other B1 boundaries are preserved.
No change to authentication, sessions, response status, timers, database schema,
roles, grants, RLS, academic calculations or trusted-device dormancy is proposed.
B1c classification/routing and B1d remain separate authorizations and reviews.

## Source evidence and release gate

The merge has parents `2d811ab31b811fb5652dc4c9142a559e738ad6d0` and reviewed
`e534096c49b01cc7acd51f2d8c763610c156d701`. Its application/workflow bytes match
the reviewed PR #51 head. The actual master **push**
[run 43320264051](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43320264051)
passed all four jobs: tests, database-tests, frontend-browser and dependency-audit.
Logs show 455 regressions (113 + 33 + 46 + 172 + 91), 27 browser tests (10/5/12),
27 additional website-root executions and 15/15 B1a mutation detections.
The floating `postgres:17` service supplied **PostgreSQL 17.12**, not the earlier
17.11. No skipped/failing test summaries; audit reported no known vulnerabilities.
These are existing B1a results, **not evidence that B1b is implemented or tested**.

Current source: no application LOGGING policy; Django applies DEFAULT_LOGGING.
`auth_common` selects the console email backend. `accounts.tokens._deliver`
passes token-bearing links to send_mail. Console/file delivery bypasses Python
logging. CPython's default Handler.handleError can print raw record arguments and
tracebacks to stderr. A root logger filter does not filter propagated children.
B1a's AccountsConfig/checks only provide the timer flag and E101.

## Owner decisions — recommendations, not approvals

All six entries below are **PENDING**. Previous approval of B1a or its D-B1-5
slice does not approve this logging policy or its new hooks/email gate.

| Decision | State | Recommendation requiring explicit owner approval |
| --- | --- | --- |
| D-B1-4(a) | **PENDING** | Enforce the six protected profiles below; preserve the excluded/offline profiles. Future Stage C must explicitly opt in. |
| D-B1-4(b) | **PENDING** | Fixed-label output only, accepting lost messages, traceback detail and reduced troubleshooting information. |
| D-B1-4(c) | **PENDING** | Minimal exact-type frozen FailureEvent and plain Enum foundation; no B1c classifier or live event emission. |
| D-B1-4(d) | **PENDING** | Startup graph validation plus source audits/code review; prohibit runtime reconfiguration without claiming Python logging is immutable. |
| D-B1-4(e) | **PENDING** | Sanitized stderr output, replacement lastResort, removal of raw development request lines and admin-email handlers; tolerate safe loss of a log when its stream fails. |
| D-B1-4(f) | **PENDING** | Secure-profile E105 console/file-email rejection plus sanitized process/thread exception hooks; accept documented bypass boundaries. External logging, retention/export and deployment acceptance stay operational work. |

D-B1-6 remains a later classification decision. Existing B1a approvals are neither
rescinded nor expanded. Implementation requires independent design review and
separate owner authorization, even if this documentation PR is merged.

## B1B-1: independent email channel and proposed E105

Propose `accounts.E105`, evaluated only when `UCC_SECURE_PROFILE is True`.
Reject Django console and file-based email backend classes, including subclasses;
check class inheritance without sending mail or instantiating a connection.
A backend import/resolution failure is a safe configuration failure, not success.
A custom wrapper can conceal raw output: passing this deny-list check is **not**
backend approval, reliable delivery or a privacy attestation. Backend identity,
TLS, credentials, provider behavior and recovery tests need separate approval.

`auth_secure`/`web_secure` currently inherit console email. Their future secure
`check --deploy` preflight therefore **must fail E105** until an approved real
email backend is configured. This is intentional, not a reason to disable E105.
Future Stage C preflight extends E101–E104 to **E101–E105**, under its exact module.
Django serving does not automatically run system checks; Stage C must enforce the
preflight. E105 is not represented as an automatic WSGI startup barrier.

Development remains compatible with console/file email and synthetic data only.
Test profiles may retain in-memory email. No transport, outbox or email-setting
change is part of B1b. Console stdout and file messages remain raw channels in
non-secure profiles; never treat logging sanitation as email redaction.
Policy requires D-B1-4(f) approval.

## B1B-2/B1B-3: protected lifecycle and raw exception hooks

Only `log_privacy.configure(namespace)` sets `UCC_LOG_PRIVACY="enforce"`.
Call it from auth_common. During **protected settings configuration**, install
safe `logging.lastResort`, `sys.excepthook` and `threading.excepthook`, before
AccountsConfig.ready. Ready validates their identities and the final logging
graph rather than waiting until then to replace lastResort. Configuration is
idempotent and must not wrap a previous hook repeatedly. Early-loaded handler/
walker modules must not import models, query the database, require a ready app
registry or recursively read partially initialized settings. Excluded profiles do
not alter these process-global objects. Use fresh subprocesses for scope tests.

The hooks use the same bounded label/safe-line machinery, directly, without
recursively calling logging or delegating to raw default hooks. Ordinary uncaught
process/thread exceptions emit at most one fixed-label line: no exception message,
traceback, thread name, source path, request, SQL parameters or secrets. The
traceback argument is never formatted. No exception/thread/traceback reference is
retained after the call. Hook formatting/write failures cannot escape as ordinary
exceptions and trigger Python's raw "error in excepthook" fallback.

Preserve interpreter semantics: an ordinary uncaught main exception still exits
non-zero (normally 1); a worker exception terminates that worker, **not** the whole
process. Worker SystemExit remains silent as in threading's default hook. An
uncaught main KeyboardInterrupt keeps the interpreter's interrupt exit semantics
(shell status 130 on supported Linux; a subprocess API may report SIGINT); only
its diagnostic text is sanitized. Do not install
catch-all execution wrappers or convert process-control exceptions to success.
SystemExit normally bypasses sys.excepthook: preserve its exit-code semantics;
non-integer exit messages remain a raw boundary. Owned code must not place secrets
in exit messages. KeyboardInterrupt/SystemExit/GeneratorExit raised inside emitter
machinery propagate; ordinary emission failures are suppressed. Subprocess tests
must verify each hook/control path rather than equate thread failure with exit 1.

The pre-settings bootstrap boundary is unavoidable here. Early lastResort protects
otherwise-unhandled logging **after** configure is called; it cannot retroactively
sanitize a pre-existing raw handler, earlier imports or startup failures. Final
Django graph validation occurs after configure_logging; no claim covers arbitrary
output during default/user logging reconfiguration. Test the early lastResort
window explicitly, before configure_logging and before ready.

Remaining bypasses: management `CommandError` formatting, `--traceback`, raw
stdout/stderr, warnings not routed through logging, console/file mail, custom
execution wrappers, sys.unraisablehook, faulthandler, native/fatal errors, os._exit,
SIGKILL, hooks replaced later and pre-settings/bootstrap tracebacks. They are not
silently declared protected. Operate only with trusted synthetic data until later
operational acceptance. New hook policy requires D-B1-4(f) approval.

## B1B-4: outer label and shared bounded walk

Separate **labeling the first exception** from **following its chain**. For valid
exc_info, always emit the outermost exception's fixed identity-table label; unknown
classes emit OTHER. An outer opaque exception (including ExceptionGroup and
BaseExceptionGroup) therefore contributes OTHER and stops: no traversal of its
members, message or hidden context. Do not flatten exception groups.

Only allowlisted nodes from Revision 5 §6.4 may be traversed: Django session
wrappers, Django DB errors and psycopg errors. At each node use cause if present;
otherwise context unless suppressed. Stop at an opaque node, on repeated object
identity, or at 16 examined nodes. An opaque inner node stops traversal without inspecting its children; it is not
added to the allowlisted walk. The first outer node is always labeled before this
stop check, and the cap counts examined nodes including that first outer node. A depth/cycle stop is
reported with a fixed truncated marker. Unknown subclasses may be traversable by
allowlisted ancestry but receive OTHER unless an exact identity is recognized.
Recognized psycopg error classes/SQLSTATEs use fixed known mappings, not an
exception-supplied class name. Never call str/repr on exception instances or read
exception args for output. Malformed attributes safely suppress the diagnostic.

This walker has no SQLSTATE classification, HTTP policy or request I/O. B1c will
reuse it with its separately reviewed outer gate/decision rules. An opaque outer
exception remains NOT_DATABASE in that future classifier; logging OTHER does not
make it a database failure.

## B1B-5: safe emission and handler graph

Retain Revision 5's field allowlist, new safe record, immutable source record,
root propagation and no raw message/extra/traceback copying. Build a complete,
bounded line including newline in memory, then make **one stream.write per line**.
Do not use getMessage(), Handler.format(), arbitrary formatters or default
handleError. Do not write fragments or retry partial writes. A short/failed write
cannot be retracted; no additional write or raw fallback is attempted.

Use a per-thread guard shared by the handler, lastResort and hooks. Nested entry
returns without output; clear the guard in finally. This prevents a custom stream
or failing serializer from recursively re-entering the sink. On ordinary
serialization/label/emission preparation error, attempt only the constant line
`ucc-log record suppressed (sanitizer error)\n`. If **the stream itself fails**,
write nothing further and return. No record-derived handleError output, recursive
logger, fallback stderr traceback or exception repr. Process controls propagate.
No flush-based retry or unbounded queue is introduced; blocking sinks remain an
operational availability risk.

Startup/E103 validation requires exactly one safe root sink, a safe lastResort,
expected hook identities, no unsafe handlers/filters/formatters on the covered
tree, and cleared django/django.server handlers with propagation. NullHandler is
allowed only where it does not replace the required root sink. E102 keeps ADMINS
empty; removing AdminEmailHandler is the actual control. Preserve AccountsConfig's
name/label and E101. Registration/checks for logging are scoped to enforce mode;
E104 checks DEBUG and DEBUG_PROPAGATE_EXCEPTIONS only under the secure flag.

No guaranteed runtime immutability: graph/hooks can be changed by arbitrary Python
code. Audit handler/configuration APIs, hook assignment, level/propagation/filter/
formatter changes and equivalent direct attribute mutation in controlled packages.
Allow only reviewed initialization sites; historical assertLogs fixtures are a
test-only exception. Dependency/operator additions require graph review and fresh
startup tests. Do not add per-request graph middleware in B1b. RB-12 remains open.

## B1B-6: minimal event foundation

Propose a frozen FailureEvent with **plain Enum** fields (not IntEnum/StrEnum),
initially EventKind.FAILURE and FailureCategory.UNCLASSIFIED only. Validate exact
types of the dataclass, both enum fields and SQLSTATE at emission, not just at
construction. Reject duck types, subclasses, integers, strings, bools and mutable
lookalikes. Emit constants from the fixed tables, never object formatting.
Only a known SQLSTATE string or None is accepted; unknown codes become the fixed
invalid placeholder. B1c enum additions need separate review. B1b tests inject
synthetic typed events only: no classifier, routing or live event emission.

## B1B-7: raw SQL diagnostic boundary

`manage.py test --debug-sql` can print SQL and parameters independently of the
sanitized application sink. Permit it **only** on disposable synthetic databases
with ephemeral restricted roles and private output. Never run it against real
student data or treat its output as redacted. Normal CI must not enable it.
Likewise `--traceback` does not become safe because hooks are installed.

## Required acceptance matrix — future implementation, not executed here

All assertions inspect **final sink bytes** and captured subprocess stdout/stderr,
not just assertLogs. Seed distinct synthetic sentinels and assert none escape.

| Area | Positive, negative and mutation evidence required |
| --- | --- |
| Sensitive routes/data | Reset/verify token paths (including encoded/malformed paths), passwords, cookies, authorization headers, IPs, query strings, SQL parameters, exception messages and traceback text across real 400/500, CSRF 403, 404, SuspiciousSession and B1a timeout paths in both URL roots; no status/session change. |
| Labels/records | Malformed logger/level/route/status, unknown exception identities/SQLSTATEs, extras, cached exc_text, stack_info, wrong event/enum types; source record and request unchanged; no getMessage/formatter invocation. |
| Walker | Explicit cause versus context, suppression, cycles, 16/17 nodes, opaque outer/inner wrappers, recognized/unrecognized subclasses, ExceptionGroup/BaseExceptionGroup, str/repr traps and malformed attributes. |
| Emission | One write per safe line; re-entry through a stream or serializer; constant fallback only for preparation failure; failed/short stream writes produce no second write; no raw default handleError; process controls propagate. |
| Early/uncaught | Fresh process logs after protected settings configure but before configure_logging/ready; sanitized ordinary main/thread exception sentinels; main non-zero status, thread-only termination, SystemExit and KeyboardInterrupt behavior; hook self-failure cannot invoke raw fallback. Demonstrate rather than conceal documented bootstrap/command/fatal bypasses. |
| Profiles/email | Six protected profiles have exact graph/hooks/lastResort; secure E105 rejects console/file classes and subclasses, handles import failures; approved-backend synthetic fixture passes without network; development and locmem compatibility; missing secure flags/helper are detected. |
| Exclusions | Fresh subprocess per auth_migration/development/runtime/test/security_test: original logging/hooks retained, no E102/E103/E105 leakage; check and migration plan plus disposable provisioning work. Protected clear_auth_artifacts keeps B1a timers; no invented exemption. |
| R5-T2 | Unsafe child handler/filter is in test LOGGING or injected after configure_logging but before ready. Assert its identity/presence **at the guard boundary**. Startup must fail; disabling the guard must make the regression assertion fail. A handler attached earlier and erased by dictConfig is not evidence. |
| Production mutations | Remove helper/early lastResort, raw handler or hook output, copied msg/request/args, formatter use, missing re-entry guard, permissive enum or E105 checks and disabled startup guard. Require passing baseline, exercised production mutation, assertion failure (not infrastructure error), restored/discarded mutations and failure on no-op/unexercised escapes. |
| Compatibility | Preserve assertLogs('accounts.tokens') and every historical assertion. Run all 455 regressions unchanged, all 27 browsers (all three suites), B1a additional website-root/mutation executions and new B1b tests; PostgreSQL 17 restricted LOGINs/forced RLS, migration drift, audit, repository safety and exact-head hosted CI. Report actual additions and zero skips; never guess future totals. |

R5-T2 source: [independent Revision 5 review, PR #42](https://github.com/jordandavid1812-creator/university-command-center/blob/642df7909afc882e5ed61a62f232113c560a5e08/docs/security/B1_REVISION_5_INDEPENDENT_REVIEW.md).

## Implementation boundary, acceptance and rollback

Future B1b changes: exception_chain, logging and log_privacy modules; minimal
AccountsConfig/check/config wiring, secure flags, E105 and exception-hook setup;
focused tests and documentation. No database queries in configuration/sanitizer,
no new credentials, dependencies, backend transport or exception-routing changes.
Stage C's eventual preflight must run E101–E105 under its exact profile. Logging
retention/export, Gunicorn/Caddy redaction and reliable recovery remain separate.

Accept only after owner decisions, separate implementation authorization,
independent code review, full D/G/F gates, R5-T2, negative controls and exact-head
hosted evidence. Any secret at a covered sink, unsafe graph, missing exercise,
profile leakage or historical regression blocks acceptance; do not weaken tests.
Rollback reverts B1b wiring/modules and restarts the process (global hooks/handlers
must not be hot-unwound); no migration reversal. It restores less-private logging:
stop serving and remain synthetic, not "production-safe after rollback".

Remaining risks: bootstrap/raw command/fatal output, non-integer SystemExit text,
console/file mail outside secure profiles, wrappers bypassing E105, external log
sinks, later graph/hook mutation, partial/blocked stream writes, diagnostic loss,
retention/access/export and Stage C provider readiness. No claim of B1 completion,
accepted staging or public readiness. Stop for separate design review.
