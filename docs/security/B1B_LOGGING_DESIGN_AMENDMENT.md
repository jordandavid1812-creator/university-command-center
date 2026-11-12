# B1b logging privacy — proposed design amendment

Status: **DESIGN ONLY; D-B1-4(a–f) PENDING; no implementation authorized.**
Baseline: master `3a4fff14421d8f79422df901027213da75a7cecc` (merged B1a).
This amendment resolves B1B-1–B1B-7 and subsequent design findings N1–N4,
and takes precedence for B1b details that
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
| D-B1-4(f) | **PENDING** | Fail-closed exact-class E105 allow-list and ordinary (not deploy-only) secure-profile E104/E105 checks; sanitized process/thread hooks with mandatory N1 containment; optional unraisable hook only if explicitly selected. Accept documented bypass boundaries. External logging, retention/export and deployment acceptance stay operational work. |

D-B1-6 remains a later classification decision. Existing B1a approvals are neither
rescinded nor expanded. Implementation requires independent design review and
separate owner authorization, even if this documentation PR is merged.

## B1B-1: independent email channel and proposed E105

**N2 proposal, pending D-B1-4(f):** `accounts.E105` uses a fail-closed
**exact-class allow-list**, initially empty. No backend class is approved by this
document. A future separately reviewed decision may authorize **one** exact
backend class; store that identity in reviewed code, not an arbitrary environment
list. Resolve the configured backend class without instantiation, sending mail or
network I/O; accept only identity equality with that single approved class.
Never use subclass acceptance. Reject console/file backends, their subclasses,
delegating wrappers, unknown classes, non-class resolutions and import failures.
A caller-supplied allow-list or a test fixture does not approve a real backend.
Checks must not expose an import exception message or backend configuration.

**Registration versus execution:** E104 and E105 are ordinary registered checks,
not `deploy=True` checks. Ensure the check module is loaded whenever
`UCC_SECURE_PROFILE is True`, independently of the logging privacy flag; an early
return for inactive logging must not skip them. Each check evaluates the explicit
secure flag; absent/False is inactive. Their registration does **not** itself run
them. Both `check` and `check --deploy` under `web_secure` must report E105 for an
empty allow-list/console configuration; --deploy also includes unrelated deployment
checks. E104 still checks both DEBUG flags. Excluded development profiles do not
acquire these errors. B1a E101 registration and behavior remain unchanged.

Management commands that request ordinary system checks may now stop on secure
E104/E105 errors before running. Commands that skip checks, use --skip-checks where
supported, or have no check requirement are not guaranteed to enforce this gate.
Use the existing auth_migration profile for authorized offline migration and
provisioning; do not create command-name exemptions or add migrator credentials to
serving profiles. `django.setup()`/WSGI app startup does not execute system checks
automatically: the graph guard in ready is separate, and E105 is **not** an automatic
WSGI startup barrier. Secure deployment must enforce the explicit preflight and
must not bypass it. No deployment is authorized here.

`auth_secure`/`web_secure` inherit console email today. With the proposed empty
allow-list, both ordinary and deployment preflight checks intentionally fail
until a real backend class has been independently reviewed, explicitly approved
and configured. Merely selecting SMTP, locmem or an unknown third-party backend
cannot make E105 pass. Future Stage C preflight runs E101–E105 under its exact
module. Backend approval alone does not prove delivery, recovery availability,
provider privacy, TLS or credential readiness; those remain separate gates.

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
retained after the call.

**N1 mandatory safety correction:** exception-hook bodies contain **every
BaseException raised by their own emission machinery**, including KeyboardInterrupt,
SystemExit, GeneratorExit and ordinary Exception. This containment covers label
extraction, re-entry setup/cleanup, serialization and stream operations. Hooks
never re-raise these failures, delegate to a raw original hook or trigger CPython's
"Error in sys.excepthook" / "Original exception was" fallback. They return safely,
with no further output if necessary. This is mandatory for any safe proposal, not
an optional diagnostic trade-off. It does not approve B1b implementation.

Distinguish the **original uncaught exception** from a failure **inside the hook**.
An ordinary original uncaught main exception still exits non-zero (normally 1),
regardless of an internally suppressed hook failure. Original worker exceptions
terminate that worker, not the entire process. Original worker SystemExit remains
silent. An original uncaught main KeyboardInterrupt retains interpreter interrupt
exit semantics (shell 130 on supported Linux; subprocess APIs may report SIGINT).
SystemExit normally bypasses sys.excepthook; preserve its exit code, with non-integer
exit messages remaining a raw boundary. Do not install execution wrappers, change
exit status based on hook failure, or turn the original main failure into success.
Owned code must not put secrets in exit messages.

**Normal logging-handler path:** process-control exceptions raised by its emission
machinery still propagate. **Exception-hook bodies:** catch all BaseException
failures from that same shared machinery. These are separate caller boundaries;
a shared helper's propagation rule cannot override the hook containment boundary.
Subprocess tests must distinguish original exception types from injected emission
failures and assert both output privacy and exit/thread behavior.

**N3 optional defense in depth, PENDING D-B1-4(f):** a sanitized
`sys.unraisablehook` may additionally cover unraisable errors (for example finalizer
failures). It is not approved or automatically included. If selected, install it
at the same protected configuration phase and apply the **same all-BaseException
containment**. Never print err_msg, repr(object), traceback or exception message;
retain no object/exception reference. Return without altering program exit/lifetime
semantics. Require sentinel and injected-hook-failure subprocess tests. It does
not cover native/fatal errors, bootstrap failures or arbitrary direct output.
Excluded profiles retain their original unraisable hook. Until explicitly approved
and implemented, unraisable output remains outside the proposed minimum policy.

The pre-settings bootstrap boundary is unavoidable here. Early lastResort protects
otherwise-unhandled logging **after** configure is called; it cannot retroactively
sanitize a pre-existing raw handler, earlier imports or startup failures. Final
Django graph validation occurs after configure_logging; no claim covers arbitrary
output during default/user logging reconfiguration. Test the early lastResort
window explicitly, before configure_logging and before ready.

**N3 raw-output boundaries:** --traceback is **not inherently a hook bypass**.
When a command re-raises an exception and it reaches the installed sys.excepthook,
that exception remains sanitized, including applicable --traceback paths. Other
paths can still print directly. Name and test the actual output mechanism:

- CommandError text printed directly by command handling, and errors a command
  catches and prints itself.
- runserver's `socketserver.handle_error` and `wsgiref` `log_exception`, which can
  print handled tracebacks without invoking sys.excepthook.
- unittest failure/error reporting, including test-runner tracebacks.
- Pre-settings/bootstrap failures; native/fatal interpreter errors, faulthandler,
  os._exit, SIGKILL and custom wrappers that print exceptions themselves.
- Raw stdout/stderr, uncaptured warnings, non-integer SystemExit messages and
  external web-server/proxy/email-backend output.
- Later replaced hooks/handlers and unraisable output unless the optional sanitized
  unraisable hook is explicitly approved and implemented.

Hooks cannot retroactively sanitize any of these writes. Keep trusted synthetic
operation only until operational acceptance. N1 containment is a safety requirement;
new hook/activation policies still require D-B1-4(f) approval.

## B1B-4: outer label and shared bounded walk

Separate **labeling the first exception** from **following its chain**. For valid
exc_info, always emit the outermost exception's fixed identity-table label; unknown
classes emit OTHER. An outer opaque exception (including ExceptionGroup and
BaseExceptionGroup) therefore contributes OTHER and stops: no traversal of its
members, message or hidden context. Do not flatten exception groups.

Only allowlisted nodes from Revision 5 §6.4 may be traversed: Django session
wrappers, Django DB errors and psycopg errors. At each node use cause if present;
otherwise context unless suppressed. Stop at an opaque node, on repeated object
identity, or at 16 examined nodes. An opaque inner node stops traversal without
inspecting its children; it is not added to the allowlisted walk. The first outer node is always labeled before this
stop check, and the cap counts examined nodes including that first outer node.
A depth/cycle stop is reported with a fixed truncated marker. Unknown subclasses may be traversable by
allowlisted ancestry but receive OTHER unless an exact identity is recognized.
Recognized psycopg error classes/SQLSTATEs use fixed known mappings, not an
exception-supplied class name. Never call str/repr on exception instances or read
exception args for output. Malformed attributes safely suppress the diagnostic.

**N4 SQLSTATE source (sanitizer only):** for a recognized exact
`psycopg.errors` class, prefer its class `sqlstate` attribute, validate exact str
shape (five ASCII uppercase letters/digits) and require `psycopg.errors.lookup`
validation against the recognized class. An instance attribute must not override a
valid class code. Missing, malformed, unknown or unexpectedly raising attributes
produce the fixed placeholder; no message, SQL detail, traceback text or exception
str/repr is read. Initial B1b omits diagnostic-instance fallback. Such access is
optional only: any later approved fallback must be guarded, used only if a trusted
class code is unavailable, validate the same shape/lookup and never export other
diagnostic fields. Normal-handler failures follow its existing control rules;
hooks contain every failure as N1 requires. No B1c routing change is implied.

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
logger, fallback stderr traceback or exception repr. Process controls propagate
only from the normal logging-handler path; all exception-hook bodies contain
them under N1, including any guard-cleanup failure.
No flush-based retry or unbounded queue is introduced; blocking sinks remain an
operational availability risk.

Startup/E103 validation requires exactly one safe root sink, a safe lastResort,
expected hook identities, no unsafe handlers/filters/formatters on the covered
tree, and cleared django/django.server handlers with propagation. NullHandler is
allowed only where it does not replace the required root sink. E102 keeps ADMINS
empty; removing AdminEmailHandler is the actual control. Preserve AccountsConfig's
name/label and E101. E102/E103 logging checks are scoped to enforce mode;
E104 checks DEBUG and DEBUG_PROPAGATE_EXCEPTIONS under the secure flag. E104/E105
are ordinary checks, loaded independently of logging enforcement whenever the
secure flag is enabled, not deploy-only checks; execution follows N2 above.

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
The --traceback flag does not imply a bypass: uncaught exceptions that reach an
installed sanitized hook stay sanitized. Directly printed command/test/server
errors remain separate raw-output boundaries as specified in N3.

## Required acceptance matrix — future implementation, not executed here

All assertions inspect **final sink bytes** and captured subprocess stdout/stderr,
not just assertLogs. Seed distinct synthetic sentinels and assert none escape.

| Area | Positive, negative and mutation evidence required |
| --- | --- |
| Sensitive routes/data | Reset/verify token paths (including encoded/malformed paths), passwords, cookies, authorization headers, IPs, query strings, SQL parameters, exception messages and traceback text across real 400/500, CSRF 403, 404, SuspiciousSession and B1a timeout paths in both URL roots; no status/session change. |
| Labels/records | Malformed logger/level/route/status, unknown exception identities/SQLSTATEs, extras, cached exc_text, stack_info, wrong event/enum types; source record and request unchanged; no getMessage/formatter invocation; valid normal records must produce one non-empty fixed-label line (absence-only checks cannot prove sanitation). |
| Walker | Explicit cause versus context, suppression, cycles, 16/17 nodes, opaque outer/inner wrappers, recognized/unrecognized subclasses, ExceptionGroup/BaseExceptionGroup, str/repr traps and malformed attributes; N4 class-code precedence over instance data, missing/malformed/raising class SQLSTATE attributes, lookup mismatch and raising diagnostics with placeholder output. |
| Emission | One write per safe line; re-entry through a stream or serializer; constant fallback only for preparation failure; failed/short stream writes produce no second write; no raw default handleError; process controls propagate in the normal handler only, never out of exception-hook bodies. |
| Early/uncaught | Fresh process logs after protected configure but before configure_logging/ready. For **each main and thread hook**, inject KeyboardInterrupt, SystemExit, GeneratorExit and ordinary Exception from emission. A sentinel-bearing original exception must never appear on stderr, nor raw `Original exception was`/`Exception ignored` sensitive details. Original main failure stays non-zero; original worker failure terminates only its worker and main continues normally. Test original process controls separately. Mutation restoring unsafe hook propagation must be exercised and make these assertions fail. |
| Optional unraisable hook | If owner selects it: synthetic finalizer/unraisable sentinel, object repr/err_msg traps, all four injected emission failures, no raw `Exception ignored` details, no retained references and unchanged exit behavior. Otherwise assert it remains unchanged and document the gap. |
| Profiles/email | Exact protected graph/hooks/lastResort. Both `check` **and** `check --deploy --settings=config.settings.web_secure` report E105 with an empty allow-list, console/file, subclasses, delegating wrappers, unknown/unimportable backend classes; E104 catches either DEBUG flag without --deploy. Use no-network test-only exact-class approval fixture for a positive case, never production approval. Reject a subclass of that fixture. Development/locmem compatibility retained; excluded profiles get no E104/E105 errors; registration cannot be skipped by missing logging policy. |
| Direct-output boundaries | Capture and distinguish --traceback re-raise reaching the hook from CommandError/command-caught print output; socketserver.handle_error, wsgiref log_exception, unittest output and pre-settings failures. Use synthetic data only; do not falsely count these channels as sanitized or change server/command behavior in B1b. |
| Exclusions | Fresh subprocess per auth_migration/development/runtime/test/security_test: original logging/hooks retained, no E102/E103/E105 leakage; check and migration plan plus disposable provisioning work. Protected clear_auth_artifacts keeps B1a timers; no invented exemption. |
| R5-T2 | Unsafe child handler/filter is in test LOGGING or injected after configure_logging but before ready. Assert its identity/presence **at the guard boundary**. Startup must fail; disabling the guard must make the regression assertion fail. A handler attached earlier and erased by dictConfig is not evidence. |
| Production mutations | Remove helper/early lastResort, raw handler or hook output, copied msg/request/args, formatter use, missing re-entry guard, permissive enum or exact-class E105 checks, unsafe BaseException propagation from hooks and disabled startup guard. Require passing baseline, exercised production mutation, assertion failure (not infrastructure error), restored/discarded mutations and failure on no-op/unexercised escapes. |
| Compatibility | Preserve assertLogs('accounts.tokens') and every historical assertion. Run all 455 regressions unchanged, all 27 browsers (all three suites), B1a additional website-root/mutation executions and new B1b tests; PostgreSQL 17 restricted LOGINs/forced RLS, migration drift, audit, repository safety and exact-head hosted CI. Report actual additions and zero skips; never guess future totals. |

R5-T2 source: [independent Revision 5 review, PR #42](https://github.com/jordandavid1812-creator/university-command-center/blob/642df7909afc882e5ed61a62f232113c560a5e08/docs/security/B1_REVISION_5_INDEPENDENT_REVIEW.md).

## Implementation boundary, acceptance and rollback

Future B1b changes: exception_chain, logging and log_privacy modules; minimal
AccountsConfig/check/config wiring, secure flags, ordinary E104/E105 checks and contained exception-hook setup
(optional unraisable only if owner selects it);
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
console/file mail outside secure profiles, raw output inside an approved backend
if its behavior later changes (exact identity is not a sandbox), external log
sinks, later graph/hook mutation, partial/blocked stream writes, diagnostic loss,
retention/access/export and Stage C provider readiness. No claim of B1 completion,
accepted staging or public readiness. Stop for separate design review.


## N1–N4 correction disposition

| Finding | Design disposition |
| --- | --- |
| N1 | Mandatory all-BaseException containment at hook boundaries; normal handler propagation kept separate. Main/thread failure and unsafe-propagation mutation requirements added. |
| N2 | Empty-or-one reviewed exact-class allow-list; ordinary secure E104/E105 checks with registration/execution, command and WSGI boundaries explicit. Policy pending owner approval. |
| N3 | --traceback paths classified by their real output mechanism; named raw server/command/test/bootstrap/external channels; optional contained unraisable hook remains pending. |
| N4 | Validated recognized-class SQLSTATE first; no diagnostic-instance fallback in the initial proposal; malformed/missing/raising attribute tests and safe placeholders required. |

No N1–N4 policy is implemented here. D-B1-4(a–f) remain PENDING. Before an
implementation work order, the owner must approve the E105 identity/activation
policy and explicitly include or exclude the optional unraisable hook. If the
allow-list remains empty, secure checks are intentionally blocked; there is no
implicitly approved email provider/backend. Remaining raw-output boundaries and
runtime mutability are not removed by these corrections.
