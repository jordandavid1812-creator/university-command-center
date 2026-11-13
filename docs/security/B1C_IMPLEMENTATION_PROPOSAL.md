# Package A — B1c classification and safe rendering

**DESIGN ONLY. D-B1-6 seven principles APPROVED; implementation NOT authorized. No implementation/merge/activation authority.**
Base: `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6`. B1a and B1b are merged;
[master push run 43380783580](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/43380783580)
passed all four jobs. Inspected DB logs: PostgreSQL 17.12; 33 foundation + 46
isolation + 201 auth + 91 website, plus 27 B1a/34 B1b website-root executions;
15/15 and 14/14 mutation detections, no skipped/failing summaries. With 113 legacy
tests the current regression floor is **484**, not the historical pre-B1b 455;
browsers remain **27**. A proposal CI run preserves baseline, not B1c acceptance.

Authority and ordering: [Revision 5 §6.1–6.14](STAGE_B_IMPLEMENTATION_PLAN.md),
[approved B1b amendment](B1B_LOGGING_DESIGN_AMENDMENT.md) and
[B1b implementation evidence](B1B_IMPLEMENTATION_EVIDENCE.md). D-B1-4 approvals
are retained. This work order authorizes documentation only. Independent review,
policy reconciliation and a separate implementation work order precede code changes.

## Actual source and threats

Current `accounts/exception_chain.py` supplies walk/Chain(nodes,truncated), a
16-node allowlist and class-first **logging** SQLSTATE validation. It contains no
classifier. `accounts/logging.py` has only FAILURE/UNCLASSIFIED; safe_record prints
those constants. There is no AuthFailureMiddleware or minimal failure_response
module. Role middleware returns its existing 503; view/session exceptions otherwise
follow Django. Both URL roots include account routes; only the web root currently
registers student_web handler400/500. Its error_page path uses templates and must
not be the database-failure renderer. Existing atomic/CAS/session phases remain
as documented and tested in B1a; B1b adds no request queries.

Threats: a programming defect incorrectly returning 400; an outage reaching a
DB-dependent error template; exception messages/SQL/token URLs leaking through
response or logs; response-save exceptions bypassing view middleware; false
rollback/revocation claims; automatic retries duplicating writes; unknown/opaque
chains incorrectly treated as proven outages. A correct error status does not
prove transaction outcome or revoke any prior session.

## D-B1-6 owner decision record — APPROVED POLICY

### Original D-B1-6 approval — exact principles

The owner's original seven approved principles are quoted below. The related
[PR #57](https://github.com/jordandavid1812-creator/university-command-center/pull/57)
at `ef661d0cd984334101944b42f16c54abfeaaa582` records the original decision;
the [owner confirmation comment #6851072382](https://github.com/jordandavid1812-creator/university-command-center/pull/54#issuecomment-6851072382),
posted by `jordandavid1812-creator` on 13 November 2026, confirms the original
approval and later B1c clarifications. It expressly limits confirmation to design
policy, without implementation, merge, PR closure, activation or deployment authority.

> 1. Preserve existing handled contracts.
> 2. Use the Revision 5 bounded SQLSTATE classification algorithm.
> 3. Return HTTP 500 for reachable programming defects except the existing role-boundary contract.
> 4. Preserve the existing Django-only `handler400` response for genuine concurrent session deletion.
> 5. Classify opaque and unknown exception chains conservatively.
> 6. Use template-free, database-independent error responses.
> 7. Include `Retry-After` only for `OUTAGE`.

Principle 3 above preserves the original owner quotation exactly; it is not
rewritten to add the word “handling”. Revision 5 §6.4 describes the underlying
exception separately: “Programming errors at the role check stay 503.” The review's
phrase “role-boundary handling contract” describes that contract but is not a
correction to the owner's quoted words. Neither wording expands the policy.

### Later explicit owner clarifications — separately approved

These are later **express owner decisions**, not inferred changes to the original
quoted approval:

- Preserve existing academic-wrapper DatabaseError-to-503 behavior during B1c as
  a compatibility exception, subject to a separate future security review.
- Preserve the current auth-root and web-root 400 handlers, including their
  existing template rendering.
- Use template-free responses for new B1c-generated 500/503 errors.

The owner also expressly approved the synthetic Retry-After rules below. None of
these design approvals authorizes implementation, merging or deployment.
Operational Retry-After values remain **PENDING Stage C measurement**.
No email backend, quota, device activation or deployment is approved.

### Retry-After validation (P6)

The owner expressly approved **5 seconds in synthetic development**, strict
integer validation within **1–300**, and exact built-in int or strictly validated
ASCII digit string inputs only. This is design approval, **not authorization to
deploy the setting**. Accept only an exact built-in int or
an exact built-in str fully matching ASCII `[0-9]+`, with numeric value **1–300**.
Bound string length before conversion (at most three digits; leading zeros within
that bound are accepted), and normalize accepted values to decimal header text.
Reject bool, float, subclasses, signs, whitespace, non-ASCII digits, units, zero,
negative, malformed and overlong input. Reject invalid configuration at startup;
never silently round or substitute a value. Test 1/300, 0/301, `'5'`, `'005'`,
Unicode digits and hostile/subclass objects. Mutate range, bool exclusion, ASCII
validation and category gating independently. No automatic retry of security writes.
Production values require later Stage C evidence and owner operational approval.

## Classifier contract and precedence

Propose frozen `Classification(category, origin, sqlstate, truncated)`:
category uses the existing plain FailureCategory Enum extended with the exact
values **OUTAGE, CONNECTION_UNAVAILABLE, CONFIGURATION, DEFECT,
DATABASE_UNPROVEN, NOT_DATABASE**. Existing UNCLASSIFIED remains event-foundation
compatibility only and is never a classifier result. origin is the literal
`database` except for NOT_DATABASE (`not_database`); sqlstate is a validated
five-character ASCII `[0-9A-Z]` string or None; truncated is an exact bool.
No I/O, request data, repr/str(exception), SQL text or database queries.

Reuse B1b's `walk`, WRAPPERS and Chain; do not fork or expand traversal. Cause
precedes context, suppression/cycles/16-node/opaque boundaries remain unchanged.
Sanitizer outer OTHER labeling does not confer database provenance. Apply:

1. Outer exception not allowlisted → NOT_DATABASE, even with a hidden DB context.
2. Across the **whole bounded walk**, first driver node with a syntactically valid
   SQLSTATE wins. OUTAGE: classes 08/53; 57P01/57P02/57P03/57014/55P03/40001/40P01/
   25P03. CONFIGURATION: 42501, class 28, 3D000, 57P04. All other valid states →
   DEFECT. An outer valid state beats an inner valid state; a deeper valid state
   beats an outer driver node lacking a state. Not “any defect anywhere wins”.
3. Only if pass 2 found no state: first driver node OperationalError/InterfaceError
   → CONNECTION_UNAVAILABLE; another psycopg.Error → DEFECT.
4. No driver reached with an allowlisted outer node → DATABASE_UNPROVEN, including
   bare Django OperationalError/InterfaceError, opaque inner stop and truncation
   before a driver. These are not proof of an outage.

### SQLSTATE source and classifier failure boundaries (P4)

Use the existing B1b bounded walker once. For each reached psycopg.Error node,
read **guarded `node.sqlstate`**, accepting only an exact str with five ASCII
`[0-9A-Z]` characters. Do not independently prefer a class attribute or read
`diag.sqlstate`, args, messages or tracebacks. psycopg normally exposes known
codes through class attributes and unknown codes through instance attributes;
normal attribute resolution supplies both. A synthetic class/instance mismatch
uses the instance-visible code, not a second class-only priority rule. Never
inspect SQLSTATE on a Django-only node. The whole-walk pass precedence above holds.

An ordinary exception raised by this narrowly guarded SQLSTATE attribute read
means no state at that node; pass 1 still checks deeper nodes before pass 2.
Malformed/missing attributes follow the same rule. This is distinct from an
unexpected walker/classifier failure: **propagate ordinary classifier failures to
the adapter**, which renders a minimal 500, never falls back to original 400 or
an invented outage category. Do not reclassify that failure recursively or log
its raw exception. Process-control BaseExceptions propagate in normal adapters.

B1b `class_sqlstate`/lookup validation remains unchanged: unknown codes are masked
as XXXXX at the sink even if the classifier knows them. Unknown valid states
outside approved outage/configuration sets are DEFECT, never false 503 outages.
Tests cover unknown codes, malformed/non-string/raising attributes, class/instance
mismatch, hostile traversal attributes, cycles and opaque boundaries. A malformed
state on a genuine no-state OperationalError may still take the approved pass-2
CONNECTION_UNAVAILABLE path; it is not proof of a particular SQLSTATE.

Read-only psycopg 3.3.8 observation: `_class_for_state` maps 08ZZZ/28ZZZ/53ZZZ to
OperationalError, XX999 to InternalError, ZZ999 to DatabaseError. Constructing
these with `info={DiagnosticField.SQLSTATE: code.encode()}` populates both
`node.sqlstate` and `node.diag.sqlstate`; the family class attribute remains None.
`Error.__init__` performs that transfer. This supports direct node access without
an extra diagnostic read. Constructed evidence is **not** real PostgreSQL fault
injection. Reproduce with the locked environment; retain real PG17 tests below.

### Unknown OperationalError-family defects (R3)

Unknown well-formed codes in psycopg OperationalError families **27, 2F, 38, 39,
3B, 40 (except 40001 and 40P01), 54, 55 (except 55P03), 57 (except the listed
OUTAGE/CONFIGURATION codes), 58, F and H** must take the valid-state DEFECT rule,
not the no-state CONNECTION_UNAVAILABLE fallback. Preserve CONFIGURATION 57P04
and OUTAGE 57P01/57P02/57P03/57014 as already specified. If guarded node.sqlstate
access is removed, unknown codes have no family-class SQLSTATE and can incorrectly
become a 503 connection failure. Class-only lookup is therefore insufficient.

Read-only psycopg 3.3.8 constructed observations confirm OperationalError mapping
and instance SQLSTATE preservation for 27ZZZ, 2FZZZ, 38ZZZ, 39ZZZ, 3BZZZ, 40ZZZ,
54ZZZ, 55ZZZ, 57ZZZ, 58ZZZ, F0ZZZ and HVZZZ. These are synthetic driver evidence,
not real PostgreSQL execution or proof of an implemented classifier.

| Future synthetic regression | Expected classification and routing |
| --- | --- |
| 55ZZZ | DEFECT / HTTP 500 |
| 54ZZZ | DEFECT / HTTP 500 |
| 58ZZZ | DEFECT / HTTP 500 |
| F0ZZZ | DEFECT / HTTP 500 |
| 40ZZZ | DEFECT / HTTP 500 |

Construct actual psycopg family errors with DiagnosticField.SQLSTATE so the code
resides on the instance, wrap them in the allowed Django/session chains, and
assert DEFECT through process_exception → handler500 and through handler400
under both roots. Preserved role/academic catches are tested separately as the
approved exceptions. Extend coverage to every family above and the approved
outage/configuration exclusions. Unknown-state sink fields remain **XXXXX**;
never weaken B1b class/lookup masking or introduce another exception walker.

Require a **production-code mutation control removing the instance SQLSTATE
read**: with a passing baseline and proven mutated-path exercise, these tests
must fail on the incorrect CONNECTION_UNAVAILABLE/503 routing (not merely a
changed internal field). A class-only replacement must also be detected. No-op,
unexercised or infrastructure-failed mutants cannot count as detections.

## Adapters, responses and typed events

- Add AuthFailureMiddleware with **process_exception**, immediately after
  AuthenticationMiddleware in auth_common; verify actual reverse exception-order
  behavior. It handles only proven OUTAGE/CONNECTION_UNAVAILABLE/CONFIGURATION
  view exceptions. Other categories return None to Django. A try/except around
  get_response is not a substitute for response-phase handlers.
- Register handler400(request,exception) and handler500(request) in **both** URL
  roots. handler500 reads the originating active exception through sys.exc_info;
  it does not assume the exception passed to process_exception survives arbitrary
  middleware. No-active-exception calls get minimal 500, without DB/template use.
- Both roots: OUTAGE/CONNECTION_UNAVAILABLE/CONFIGURATION → minimal 503. DEFECT →
  minimal 500. DATABASE_UNPROVEN → minimal 500 at handler500, original 400 at
  handler400. NOT_DATABASE delegates to the existing root's handler. A real 42703
  or 42P01 behind SessionInterrupted can **never** be classified into original 400.
- Preserve role middleware, registration IntegrityError and handled academic
  responses before B1c interception. **Academic-wrapper compatibility exception:**
  accounts.views.academic_errors returns JSON 503 for DatabaseError on
  accounts:academic/course/delete-assignment. student_web.views.protected returns
  a templated 503 on its dashboard, list, CRUD, overview/predictor/planner/settings
  routes. A 42703/42P01 raised inside the protected view body therefore stays 503;
  exceptions outside that catch scope still follow their actual Django boundary.
  This is an explicit exception to general defect-to-500, preserved for B1c.
  Follow-up independent security review of wrapper scope, defect status and
  DB-dependent error rendering is required before any separately authorized change.
  No catch-all changes to successful login,
  sessions, authentication, CSRF or ownership. No retries/compensating writes.
- Preserve existing handler400 rendering on both roots: auth delegates to Django
  defaults.bad_request (400.html when available, built-in fallback otherwise);
  web delegates to student_web.views.bad_request/error_page and
  student_web/error.html. Do not claim these preserved handlers are template-free
  or necessarily database-independent. Genuine deletion does not prove other
  database work will succeed. If an existing handler fails, Django's handler500
  boundary applies. Template-free/zero-query guarantees apply to B1c-generated
  500/503 only; tests separately assert preserved 400 behavior.
- failure_response builds constant UTF-8 bodies by category/status/allowlisted
  route group. Route selection uses an already available fixed resolver view name,
  not paths/token kwargs/headers, reverse or new URL resolution. Builder accesses
  no user/session/messages/templates/context processors or connection. Literal
  `/accounts/login/` only. B1 responses set no-store and content-type/charset.
  Retry-After is present only for OUTAGE within B1-generated responses; existing
  429 behavior is preserved. B1c uses generic category responses only; uncertain-
  outcome wording, including reset/verify/change variants, belongs exclusively to B1d.
- Builder catches Exception, retaining the selected status in a constant plain
  fallback. Never catch process controls here: B1b's all-BaseException rule applies
  to exception hooks only. If fallback fails, Django's handler500/WSGI behavior
  applies; no resource-exhaustion or post-header delivery guarantee is invented.
- A consumed process_exception failure produces exactly one `accounts.failures`
  record using exact FailureEvent/EventKind.FAILURE and classified category. Extend
  B1b's category Enum **and its current hardcoded safe category mapping** through
  fixed tables. Do not emit “UNCLASSIFIED” for every new classified event. No raw
  exception/message/path extra; unknown SQLSTATE is masked at the sink. Returned
  responses that Django logs later may produce separate framework lines; assert
  one typed consumed event, not one total logging line for the entire request.
  Event policy: exactly one accounts.failures event for each process_exception-
  consumed 503, with its classified OUTAGE/CONNECTION_UNAVAILABLE/CONFIGURATION.
  If process_exception itself encounters an ordinary classifier failure, it
  consumes a minimal 500 and emits exactly one DEFECT event with sqlstate=None
  (diagnostic mapping only, not a fabricated database Classification). This retains
  the existing proposed event type: no new classifier-failure event or enum member
  is introduced by this correction. Diagnostic limitation: this line alone cannot
  distinguish a classifier bug from other DEFECT events; more precise fixed-label
  diagnostics are a potential separately reviewed future improvement.
  Handler400/500 never emit typed events, including their classifier-error 500
  fallback; retain Django's independently emitted sanitized django.request
  response records. Nonconsumed defects/unproven/non-DB paths have no new typed
  event. Never attach raw classifier exceptions, paths or request metadata extras.
  Assert final sink bytes, category mappings, unknown-code masking and absence
  of password/token/cookie/Authorization/IP/SQL/traceback sentinels.

## Complete R5 B matrix — mandatory future execution

| Test | Required evidence, both URL roots where applicable |
| --- | --- |
| session_update_undefined_column_is_500 | N/SA UPDATE injected driver 42703 → handler400 → minimal 500; no issued key |
| session_update_undefined_table_is_500 | Same with 42P01 |
| session_insert_failure_routes_handler500 | DA/SX exists/INSERT faults 55P03, 42703, no-state → handler500 → category's 503/500; controlled not-applied case zero replacement rows |
| real_undefined_column_in_view_is_500 | Disposable migrator fixture renames session column; real driver 42703 from lazy session read; minimal 500; restore schema in finally |
| session_update_lock_timeout_is_503 | Real SA session blocker observed; 55P03, 503 + Retry-After |
| connection_loss_real_termination_is_503 | Authorized disposable fixture terminates actual auth backend; record driver class/code, accept 57P01 OUTAGE or no-state CONNECTION_UNAVAILABLE; headers follow actual category |
| connection_loss_without_sqlstate_is_503 | Local synthetic TCP relay disconnect; no-state driver provenance, 503 without Retry-After |
| genuine_concurrent_session_deletion_stays_400 | Real row removed before SA UPDATE; no driver node, DATABASE_UNPROVEN; preserve original 400 |
| non_database_bad_request_stays_400 | Genuine non-DB BadRequest, NOT_DATABASE, existing 400 |
| configuration_class_is_503_without_retry_after | 42501/28000 (and policy class/3D000/57P04 controls), 503, no Retry-After |
| classifier_synthetic_chains | Every R5 §6.4 row: mixed driver precedence, opaque outer/inner, suppression, cause/context, cycle, 16/17 nodes, malformed/new states, no-state drivers, 25P03 through InternalError; constructed chains are not real DB evidence |
| view_versus_middleware_routing | View → process_exception; response middleware → handler500; UPDATE wrapper → handler400; INSERT/exists → handler500; active exception inspected correctly |
| existing_contracts_preserved | Role-guard ProgrammingError stays existing 503; generic registration IntegrityError and handled academic responses unchanged |
| consumed_exception_emits_typed_event | Exactly one typed accounts.failures event for a consumed failure; category and validated/masked code actually appear at final B1b sink |

### Additional real PostgreSQL timeout rows (P5)

Under **both auth and web URL roots**, force real **57014** using the B1a auth
statement timer and real **25P03** using its idle-in-transaction timer on account
routes. Record actual driver class, nested state, transaction phase, fresh-observer
state and connection recovery; assert OUTAGE, minimal 503, Retry-After=5,
no-store, sink privacy and CK1–CK4 as applicable. Do not substitute constructed
exceptions or role-boundary failures for these route tests. Synchronize via backend
state/locks with bounded test deadlines, not arbitrary timing-only sleeps.

## Complete R5 C matrix — mandatory future execution

| Test | Required evidence |
| --- | --- |
| renderer_both_roots_no_db_no_templates | Zero queries on **all aliases**, no template/context processor/reverse/user/session access, positive constant-body/status/header assertions |
| renderer_last_resort_and_recursive_failure | Builder ordinary failure preserves selected status in fallback; injected fallback failure follows Django handler500; bounded observations, no fabricated resource guarantee |
| renderer_propagates_process_control | KeyboardInterrupt/SystemExit/GeneratorExit propagate from renderer, distinct from hook containment |
| handler500_without_active_exception | Direct call yields minimal plain 500 with zero DB/template access |
| debug_flags_documented_behaviour | DEBUG=True technical paths bypass handlers; DEBUG_PROPAGATE_EXCEPTIONS uncaught path re-raises; view process_exception still runs; secure E104 rejects either flag |
| body_variants_constant_and_enumeration_comparison | Same bytes within a variant across known/unknown synthetic accounts; status/timing distributions compared separately; no enumeration-proof claim from constant text |

## Nominated A2/A5 and common gates

A2: N/AN/SA/SX/DA; L1 real Student lock; L2 last_login or flush/write before COMMIT;
L3 controlled termination as COMMIT dispatched and real-COMMIT-then-error; L4u
55P03/42703 UPDATE; L4i exists/INSERT not applied; L5u/L5i response save uncertain.
Record O1–O4/CK1–CK4 each time. SA prior key/expiry survives or renews only as its
unit permits; DA A can survive L1/L2 rollback, DA L4i has zero replacements, L5i
may leave an undelivered B row. Do not require deletion headers absent. Earlier
throttle/CAS autocommit remains committed after later finalizer failure.

A5: C0 real Student lock; C1 flush DELETE error; C2 after flush/pre-COMMIT; C3 real
and injected uncertain COMMIT; C4 confirmed change/later failure. C2 must show
browser deletion **and** valid server prior key; C3 permits committed/rollback
states, no new authority. Source snapshots include old/new credential validity,
other-session hash invalidation and legitimate cookie deletion, not just status.
Use clean observer connections and actual role/lock/SQLSTATE evidence. S1/E1 rollback
is not a lost-COMMIT probe; real _commit then raise must persist in the committed
control. Stage logs/routes pass B1b sentinels, including 503 and typed events.

Regression floor 484 + all 27 browsers, 27/34 additional website-root executions,
B1a/B1b mutation controls, restricted PostgreSQL 17/forced RLS/MAINTAIN guards,
migration drift, audits and exact-head CI. Add genuine tests, report actual totals.
Mutate 42703→400, wrong pass order, hidden opaque-driver traversal, wrong UPDATE/
INSERT handler, all-503 fallback, unmasked typed extras, DB/template use, omitted
no-store, Retry-After on connection errors, wrong commit hook and added retries.
Every mutant needs passing baseline, proven exercise, assertion failure without
infrastructure error and cleanup. No source/role relaxation to obtain green.

## Scope, dependencies, rollback and review gate

Future code: failure_classification.py, failure_response.py, middleware process
exception class, both URL handler registrations, auth_common order and B1b category
serialization extension; focused tests/docs only. No migration, grant, successful
session transaction change, device wiring or quotas. Any defect in existing B1b
must be separately reviewed, not silently fixed under this package.

D-B1-6 seven principles are APPROVED; no policy approval authorizes code.
Next: independent review of these clarifications, explicit B1c work order, draft implementation PR,
PG17/negative/CI evidence, independent code review and separate exact-head merge
approval. Codex authored this proposal and B1b; request a separate reviewer and
disclose prior involvement. Documentation CI is not approval of the algorithm.

Rollback future B1c by reverting adapters/classifier/renderer/category extensions
and restarting; retain B1a/B1b, roles, sessions and data. No migration reversal or
compensating writes. Existing 400/500 behavior returns; stop serving real data.
Residuals: opaque provenance, uncertain commits/orphans/prior authority, unbounded
COMMIT/HTTP delivery, raw external output, debug pages, resource exhaustion and
account enumeration beyond body constancy. B1d and operational acceptance remain.

## Correction and reconciliation register

| Finding | Disposition in this document |
| --- | --- |
| P1 / A1 policy status | Seven principles approved; node.sqlstate rule is precise; operational values remain pending. |
| P2 / A2 wrappers | Explicit preserved academic defect-to-503 compatibility exception; later review required. |
| P3 / A6 handler400 | Both roots retain actual template behavior; B1c 500/503 guarantees are separate. |
| P4 / A4/A7 | Narrow attribute failures differ from classifier bugs; adapter minimal500; exact event ownership and sanitized framework logs specified. |
| P5 | Real PG17 57014 and 25P03 under both roots added, not claimed executed. |
| P6 / A3 | Synthetic 5 seconds, strict 1–300 validation and production mutation requirements specified. |
| A5 | No uncertain-outcome wording in B1c; B1d remains separately gated. |
| A8 | Middleware follows AuthenticationMiddleware; existing handled contracts retain precedence. |

PR #57 at the cited head contains statements **not adopted here**: class-first
plus diag fallback, a blanket “no duplicate django.request line”, and catching
classifier defects into unproven results that could preserve 400. Its “unknown
state produces false 503” example must be qualified: 08/28/53 are already approved
503 families; XX999/ZZ999 map to non-Operational families and pass 2 DEFECT. Direct
node access is necessary for correct category/header handling **and to prevent
false 503s for unknown OperationalError-family defects**, including 55ZZZ, 54ZZZ,
58ZZZ, F0ZZZ and 40ZZZ as required above. Its blanket truncated-chain prohibition also needs qualification:
visible approved driver evidence within the bounded prefix remains decisive;
truncation before proof is unproven. Request focused independent corrections to
PR #57; this work does not modify that branch.

Codex authored the original PR #54 proposal and participated in B1b; this update
is an author correction, **not independent approval of PR #54**. Request a separate
reviewer for the corrected exact head. All proposed B1c evidence remains future
acceptance work; existing hosted CI proves baseline preservation only.

### Final design-review follow-ups

| Finding | Documentation-only disposition |
| --- | --- |
| R1 | Original seven principles quoted separately from later explicit owner-approved academic-wrapper/400/rendering clarifications. |
| R2 | Express owner approval of synthetic 5 seconds and strict 1–300 integer/ASCII-string validation recorded; operational choice remains pending. |
| R3 | Unknown OperationalError-family defect matrix and instance-read-removal production routing mutation required; B1b masking and single walker unchanged. |
| R4 (informational) | No new classifier-failure event type; existing diagnostic limitation recorded for possible future review. |

Claude's **involved-author design reviews** returned **APPROVE (design only)**
for `652af3795308cb3baa643e736f0fdd6a265ef030` and the R1–R3 follow-up head
`d1ce46be8afd8fe58e1d07a12cba3fdcc8f2aeab`. Claude authored Revision 5 and PR #57
and reviewed B1a/B1b; these reviews are not independent security approval.
Focused verification of this attribution-only correction remains appropriate;
no historical design review is code approval or an implementation work order.
