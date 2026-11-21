# B1c failure classification — D-B1-6 decision record

Status: **DESIGN RECORD ONLY. D-B1-6 OWNER-APPROVED. B1c and B1d are NOT authorized for implementation.**

* **Baseline:** master `e4bbf8b51bd0ea5a3173c2f4e2b4f4b7b1974cd6` (B1b merged through PR #53; B1a through PR #51).
* **Authority for the algorithm:** [Stage B Revision 5](STAGE_B_IMPLEMENTATION_PLAN.md) §6.4 (classification), §6.5 (catch points), §6.7 (rendering), §6.8.3 (typed events), §6.10 B/C/D (tests), §6.11 (B1c gate) and §6.14 (residual risks).
* **Precedence:** this record adds no new policy. Where it is more specific than Revision 5, it only resolves wording. It lists open ambiguities in §5 **without deciding them**.
* **Authorship:** prepared by Claude, the author of Revision 5. It needs **independent review** (for example by Codex) before the owner considers merging it.

## 1. Owner decision

**Recorded 13 November 2026 (Africa/Lagos).** The source is the project owner's instruction "UCC — RECORD APPROVED D-B1-6 POLICY", which states **"D-B1-6 is APPROVED"**. A durable confirmation (an owner comment on this PR) is requested so that the record does not rely on a private session.

The approved classification policy, in the owner's words:

1. Preserve existing handled contracts.
2. Use the Revision 5 bounded SQLSTATE classification algorithm.
3. Return HTTP 500 for reachable programming defects, except the existing role-boundary handling contract.
4. Preserve the existing Django-only `handler400` response for genuine concurrent session deletion.
5. Classify opaque and unknown exception chains conservatively.
6. Use template-free, database-independent error responses.
7. Include `Retry-After` only for `OUTAGE`.

**What the approval does not do:**

* It authorizes no B1c or B1d code, middleware, handler, renderer, enum change or test.
* It changes nothing in B1a (database timers, E101) or B1b (sanitizer, hooks, E102–E105).
* It approves no email backend, trusted-device activation, account enforcement, staging or deployment.
* A B1c implementation needs a separate owner work order, then independent code review, then exact-head PostgreSQL 17 CI.

**Mapping to Revision 5 §6.14 D-B1-6.** The four Revision 5 sub-items are covered as follows:

* "preserved handled contracts" → owner item 1;
* "a reachable defect gives 500 at every boundary" → item 3, with the role-boundary exception Revision 5 already documents;
* "the documented Django-only handler400 exception" → item 4;
* "the opaque-chain limits (RB-10)" → item 5.

Items 2, 6 and 7 restate §6.4 and §6.7.

## 2. Invariants this policy must keep

These come from B1a, B1b and Revision 5, and B1c must not weaken any of them:

* **Never a false 503.** A 503 requires a proven database outage, connection or configuration category (§2 below). An unknown, opaque or truncated chain never becomes 503.
* **Existing contracts run first** and are unchanged (the table in §3.3).
* **Session lifecycle unchanged:**
  * no new authenticated key is delivered;
  * a prior session may be kept or renewed (D-B1-1);
  * a cookie may be deleted while the server copy stays valid (D-B1-2);
  * no retries and no compensating writes.
* **The B1b walker is the only traversal.** It lives in `server/accounts/exception_chain.py`, and the classifier must not walk chains a second time.
* **The classifier is pure.** It does no I/O, reads no request data, and never calls `str()`, `repr()` or `args` on exceptions.
* **B1b privacy holds.** Output goes only through the fixed-label sink; consumed exceptions emit exactly one typed `accounts.failures` event; the sink never prints message text, SQL, paths, tokens or headers.
* **B1a timers unchanged:** connect 5 s, lock 3 s, statement 5 s (auth) and 10 s (runtime), idle 15 s.

## 3. Classification and routing specification (Revision 5, restated for implementation)

### 3.1 Algorithm (§6.4)

`classify_database_failure(exc) -> Classification(category, origin, sqlstate, truncated)` runs over the B1b walk:

| Pass | Rule | Result |
| --- | --- | --- |
| 0 Outer gate | `exc` itself is not an allowlisted wrapper (`SessionInterrupted`, `UpdateError`, `CreateError`, `django.db.utils.Error` family, `psycopg.Error` family) | `NOT_DATABASE` |
| 1 SQLSTATE | The first driver node in walk order with a well-formed SQLSTATE (`[0-9A-Z]{5}`; source rule: ambiguity A1). Codes: class `08`, class `53`, `57P01`, `57P02`, `57P03`, `57014`, `55P03`, `40001`, `40P01`, `25P03` → `OUTAGE`. `42501`, class `28`, `3D000`, `57P04` → `CONFIGURATION`. Any other well-formed code → `DEFECT` | as listed |
| 2 Driver, no SQLSTATE | The first driver node: `psycopg.OperationalError` or `psycopg.InterfaceError` (including `ConnectionTimeout`) → `CONNECTION_UNAVAILABLE`; any other `psycopg.Error` → `DEFECT` | as listed |
| 3 Django only | No driver node reached: a bare Django database error, a chain truncated (16 nodes or a cycle) before any driver node, or a walk ended at a non-allowlisted node | `DATABASE_UNPROVEN` |

* **Owner item 5:** pass 0 and pass 3 are the "conservative" rules. An opaque outer exception is never a database failure; an unproven database chain is never 503.
* `origin` is `database` for every category except `NOT_DATABASE`.

### 3.2 Status by category and catch point (owner items 3, 4 and 7)

| Category | View `process_exception` (`AuthFailureMiddleware`) | `handler500` | `handler400` | `Retry-After` |
| --- | --- | --- | --- | --- |
| `OUTAGE` | 503 minimal | 503 minimal | 503 minimal | **Yes** (value: A3) |
| `CONNECTION_UNAVAILABLE` | 503 minimal | 503 minimal | 503 minimal | No |
| `CONFIGURATION` | 503 minimal ("not configured safely") | Same | Same | No |
| `DEFECT` | Not consumed → `handler500` | **500 minimal** | **500 minimal** | No |
| `DATABASE_UNPROVEN` | Not consumed → `handler500` | **500 minimal** | **Existing 400** (genuine concurrent deletion; owner item 4; see A6) | No |
| `NOT_DATABASE` | Not consumed | Existing handler (auth root: Django default; web root: `student_web.views.server_error`) | Existing 400 handling | No |

Every response produced by B1c carries `Cache-Control: no-store`.

### 3.3 Preserved handled contracts (owner item 1; unchanged, and run before B1c)

| Site (current master) | Existing behaviour |
| --- | --- |
| `server/accounts/middleware.py` `DatabaseRoleBoundaryMiddleware` | Any `DatabaseError` or `ImproperlyConfigured` during the role check → 503 "The service is not configured safely." Defects here stay 503: this is the role-boundary exception named in owner item 3. |
| `server/accounts/views.py` `academic_errors` | `DatabaseError` → JSON 503; service errors → 400/404/409 (see A2) |
| `server/student_web/views.py` `protected` | `DatabaseError` → templated 503 page; service errors → 400/403/404/413 (see A2) |
| `server/accounts/tokens.py` registration | A handled `IntegrityError` gives the generic success page |
| Django `SuspiciousOperation`, CSRF 403, 404 | Existing handling, with B1b-sanitized logging |

### 3.4 Catch points (§6.5)

* **View exceptions** reach `process_exception`.
* **The session UPDATE** in `SessionMiddleware.process_response` (initial states N, AN, SA) becomes `UpdateError` → `SessionInterrupted` → `handler400`.
* **Session creation** in `process_response` (DA, SX) raises a raw `DatabaseError` → `handler500`.
* **Other middleware responses** go to `handler500`.
* **If `handler400` itself raises**, Django's path takes over and calls `handler500`.
* **After the WSGI header handoff**, nothing can change the response (RB-2).

## 4. Matrices for a future implementation (not executed by this record)

All database rows run on **real PostgreSQL 17** with separate migrator, auth and runtime logins, forced RLS, `DEBUG=False` and `DEBUG_PROPAGATE_EXCEPTIONS=False` (unless a row says otherwise), under **both** URL roots. Each row's fault kind is labelled **real**, **injected-driver**, **injected-commit** or **injected-post-execute** (R5-T1). Rollback or commit is never inferred from the HTTP status.

### 4.1 Classification matrix (pure unit tests; constructed chains prove traversal only)

| Chain (outer → inner) | Expected category / SQLSTATE |
| --- | --- |
| `SessionInterrupted → UpdateError → OperationalError → LockNotAvailable(55P03)` | `OUTAGE` / 55P03 |
| `SessionInterrupted → UpdateError → ProgrammingError → UndefinedColumn(42703)` | `DEFECT` / 42703 |
| `SessionInterrupted → UpdateError → DatabaseError` (no driver) | `DATABASE_UNPROVEN` |
| `OperationalError → psycopg.OperationalError` (no SQLSTATE) | `CONNECTION_UNAVAILABLE` |
| …the same, with context `AdminShutdown(57P01)` | `OUTAGE` / 57P01 (pass 1 beats pass 2) |
| Django `InterfaceError`, or bare `OperationalError`, with no driver | `DATABASE_UNPROVEN` |
| `TemplateDoesNotExist` with context `OperationalError(55P03)` | `NOT_DATABASE` (outer gate) |
| `ExceptionGroup` / `BaseExceptionGroup` containing a driver error | `NOT_DATABASE` (opaque outer) |
| `UpdateError` with context `KeyError` | `DATABASE_UNPROVEN` |
| Cyclic context between two Django errors | `DATABASE_UNPROVEN`, `truncated=True` |
| 17 nested Django wrappers, driver node at depth 17 | `DATABASE_UNPROVEN`, `truncated=True` |
| `raise … from None` hiding a driver context | Decided by the nodes before it |
| Explicit `__cause__` alongside a different `__context__` | Cause followed |
| `InsufficientPrivilege(42501)`, `InvalidAuthorizationSpecification(28000)`, `InvalidCatalogName(3D000)`, `DatabaseDropped(57P04)` | `CONFIGURATION` |
| `IdleInTransactionSessionTimeout(25P03)` inside Django `InternalError` | `OUTAGE` |
| `QueryCanceled(57014)`, `SerializationFailure(40001)`, `DeadlockDetected(40P01)`, `TooManyConnections(53300)`, `CannotConnectNow(57P03)` | `OUTAGE` |
| `UniqueViolation(23505)` that was not handled; `NumericValueOutOfRange(22003)` | `DEFECT` |
| Malformed or missing SQLSTATE on a driver node | No SQLSTATE → pass 2 |
| **Unknown server SQLSTATE** raised by psycopg as a family base class (verified mapping: `08ZZZ`, `28ZZZ` and `53ZZZ` → `psycopg.OperationalError`; `XX999` → `psycopg.InternalError`; `ZZ999` → `psycopg.DatabaseError`) | Depends on A1: `08ZZZ` and `53ZZZ` → `OUTAGE`; `28ZZZ` → `CONFIGURATION`; `XX999` and `ZZ999` → `DEFECT` |
| Hostile attributes (a raising `__cause__`/`__suppress_context__`, a spoofed `__class__`, a metaclass whose hash raises), as in the B1b probes | No exception leaks from the classifier; result is `NOT_DATABASE` or `DATABASE_UNPROVEN`, never 503 (A7) |

### 4.2 Routing and status matrix (Revision 5 §6.10 B; real PostgreSQL 17)

| Test | Required evidence |
| --- | --- |
| Session UPDATE `UndefinedColumn(42703)` / `UndefinedTable(42P01)` (injected-driver) | `handler400` → **500 minimal** |
| DA session INSERT or `exists()` failure (55P03, 42703, no SQLSTATE) | `handler500` → 503 or 500 by category; 0 B rows |
| Real 42703 in a view (migrator renames a `django_session` column in setup, restored in teardown) | 500 minimal through `handler500` |
| Real 55P03 on the SA session row | 503 **with** `Retry-After` |
| Real `pg_terminate_backend` before the session UPDATE | 503; category in {`OUTAGE` 57P01, `CONNECTION_UNAVAILABLE`}; driver class recorded |
| A local TCP relay that closes mid-request | `CONNECTION_UNAVAILABLE` → 503 **without** `Retry-After` |
| Genuine concurrent deletion (row deleted before the SA save) | `DATABASE_UNPROVEN` → **existing 400** |
| A synthetic `BadRequest` | `NOT_DATABASE` → existing 400 |
| Injected 42501 and 28000 | 503, no `Retry-After` |
| Real 57014 (B1a statement timer) and real 25P03 (B1a idle timer) on account routes | 503 with `Retry-After` |
| View versus middleware routing | View → `process_exception`; middleware or response → `handler500`; session UPDATE → `handler400` |
| Existing contracts | Role middleware 503 for `ProgrammingError`; registration `IntegrityError`; academic wrappers unchanged (A2) |
| A2 and A5 rows that change status (L1, L2, L3, L4u 55P03/42703, L4i, L5u, L5i; C0–C3), and A3/A4 S1/E1–E3 | CK1–CK4, allowed deletion, no new non-empty key, prior-key validity and expiry as in §6.3 |

### 4.3 Rendering matrix (Revision 5 §6.7 and §6.10 C)

| Variant | Status | Body | Headers |
| --- | --- | --- | --- |
| Outage | 503 | Constant UTF-8 | `no-store`, `Retry-After`, charset |
| Connection unavailable | 503 | Constant | `no-store`, charset |
| Configuration | 503 | Constant ("not configured safely") | `no-store`, charset |
| Minimal defect | 500 | Constant | `no-store`, charset |
| Uncertain outcome (reset, verify, change) | 503 | **B1d wording**; B1c uses the generic 503 variants (A5) | As for its category |

Required tests:

* **Database- and template-independent:** `CaptureQueriesContext` counts 0 queries on every alias; the template loader, `reverse()`, `request.user`, the session and messages are never touched; both roots.
* **Fallback:** the builder raising `RuntimeError` gives a fixed plain-text body with the already-chosen status. If the fallback also raises, Django's `handler500` path runs.
* **Process control:** `KeyboardInterrupt`, `SystemExit` and `GeneratorExit` propagate from the renderer.
* **`handler500` with no active exception** (direct call) gives a minimal plain 500.
* **Debug flags:**
  * with `DEBUG=True`, `handler400` and `handler500` are not called, but `process_exception` 503s still apply;
  * with `DEBUG_PROPAGATE_EXCEPTIONS=True`, uncaught exceptions are re-raised;
  * E104 fires in secure profiles.
* **Constant bodies:** identical bytes within a variant for known and unknown accounts. This is not a claim of enumeration resistance.

### 4.4 Logging matrix (Revision 5 §6.10 D, extended; assertions on the sink bytes)

| Path | Required sink evidence |
| --- | --- |
| `process_exception` consumes 503 | Exactly **one** `accounts.failures` line with typed `event`, `category` and validated `sqlstate`, plus the route label. No duplicate `django.request` line for the same exception. |
| `handler500` / `handler400` minimal responses | Django's existing `log_response` line, sanitized by B1b (`exc=` labels only). Plus at most one typed event if the implementation emits one: specify which (A4). |
| Every new route (503, minimal 500, preserved 400) | No sentinel from the reset/verify secret, encoded paths, query strings, `Cookie`, `Authorization`, the client IP, User-Agent, exception messages or SQL fragments |
| `FailureEvent` extension | New plain-Enum members, exact-type checks, and a **member-specific** fixed constant mapping in the sanitizer (A4). Unknown or invalid members print `-`. SQLSTATE printed only after `psycopg.errors.lookup` validation, otherwise `XXXXX`. |

### 4.5 Mutation controls (production behaviour only; B1a/B1b runner rules)

Each must be detected with a passing unmutated baseline, proof it was exercised, an assertion failure and no infrastructure error:

* the outer gate removed;
* pass 1 run after pass 2;
* a wrapper added to or removed from the allowlist;
* the 16-node or cycle bound removed (run with a timeout);
* 25P03, 57014 or 55P03 moved out of `OUTAGE`;
* a configuration code reclassified;
* `DATABASE_UNPROVEN` → 503;
* the `handler400` defect → 500 rule removed;
* `Retry-After` added to a non-`OUTAGE` category;
* the renderer using templates or `reverse()`;
* the renderer catching `BaseException`;
* the renderer's last resort removed;
* a consumed exception logged twice, or not at all;
* the typed-event mapping loosened to accept a subclass or a string;
* a deletion header stripped (must fail A5 C2).

### 4.6 Gate (Revision 5 §6.11 B1c)

* **Tests:** B and C in full; the status-changing A2/A5 rows; A3/A4 S1/E1–E3; D extended; F (all 484 current regression tests unchanged) and all 27 browser tests.
* **Earlier controls:** the B1a (15) and B1b (14) mutation controls must still pass.
* **CI:** hosted CI at the exact head, including PostgreSQL 17 and the dependency audit.
* **Claims:** no "B1 complete" and no uncertain-outcome wording (that is B1d).

## 5. Ambiguities and risks for review (the approved policy is not changed)

| ID | Item | Why it matters | Recommended resolution, for owner or review confirmation |
| --- | --- | --- | --- |
| **A1** | **Where pass 1 reads the SQLSTATE.** B1b's `class_sqlstate` reads only the class attribute, which is what the sanitizer's output needs (N4). psycopg raises an **unknown** server SQLSTATE as a family base class, such as `psycopg.OperationalError` for classes `08`, `28` and `53`, `psycopg.InternalError` for `XX`, or `psycopg.DatabaseError`, with the code only on the instance's diagnostics (`psycopg/errors.py` `_class_for_state`). With class-only reading, such an error falls to pass 2 and becomes a **503 `CONNECTION_UNAVAILABLE`** even when it is a defect. That breaks "never a false 503". | Revision 5 says "a well-formed `sqlstate`" without naming the source. | For **classification only**: use the class code first; otherwise read the instance's `diag.sqlstate` inside an all-`Exception` guard and require the `[0-9A-Z]{5}` shape. Unknown codes decide by class prefix (`08`/`53` → `OUTAGE`; `28` → `CONFIGURATION`; otherwise `DEFECT`). The sanitizer's output rule stays class-first with `XXXXX` for unknowns. Needs unit and mutation tests. |
| **A2** | **Academic wrappers turn every `DatabaseError` into 503**, including real defects such as 42703 in a service query. | Owner item 1 preserves handled contracts, while item 3 names only the role boundary as an exception to "defects → 500". Revision 5 §6.4 lists these wrappers as preserved contracts. | B1c leaves them unchanged, and the defect-→-503 behaviour inside them is recorded as a preserved contract. **The owner should confirm** this reading, or ask for a separate, later change to the academic wrappers (out of B1c scope). |
| **A3** | **The `Retry-After` value** is unspecified ("configurable candidate", Revision 5). | It's needed for the `OUTAGE` rows. | A validated integer-seconds setting with a synthetic test value. The final value comes from Stage C measurement, not this record. |
| **A4** | **Typed events.** B1b's sanitizer prints the constants `FAILURE`/`UNCLASSIFIED` whatever member it receives (`server/accounts/logging.py`, `safe_record`). B1c needs new category members and a member-specific mapping, which changes B1b code. It's also unspecified whether `handler500`/`handler400` minimal responses emit a typed event alongside Django's `log_response` line. | Risk of mislabelled or duplicated events. | Extend the enums and an exact-type, member-specific mapping, under B1b mutation rules. Recommend that only `process_exception`-consumed exceptions emit `accounts.failures`, since the handler paths already produce one sanitized `django.request` line. Test for exactly one line per failure. |
| **A5** | **Uncertain-outcome variant.** Revision 5 §6.7 lists a "503 uncertain outcome" body, but §6.11 assigns that wording to B1d. | Scope boundary. | B1c renders the generic category variants; B1d replaces the reset/verify/change wording. |
| **A6** | **Existing 400 response in the web root.** `config/web_urls.py` currently routes `handler400` to `student_web.views.bad_request`, which renders a template. Owner item 4 says *preserve the existing* response, while item 6 asks for template-free responses. | Possible conflict between items 4 and 6. | Items 6 and 7 apply to B1c-generated 503/500 responses. For `DATABASE_UNPROVEN` and `NOT_DATABASE` at `handler400`, delegate to the existing handler (Django's default in the auth root, `student_web.views.bad_request` in the web root) so the response is unchanged. The database is reachable in that case, because a genuine deletion is not an outage. Needs owner or review confirmation. |
| **A7** | **The classifier's own failures.** If a hostile chain makes the walk raise, the classifier must still answer without leaking or giving a false 503. | Conservative behaviour (item 5). | Catch `Exception` inside the classifier and return `NOT_DATABASE` (outer not provably a database error) or `DATABASE_UNPROVEN` (outer allowlisted), never 503. `BaseException` subclasses propagate, consistent with the normal-path rule. |
| **A8** | **Middleware placement.** Revision 5 says only "middleware order (B1c)" in `auth_common`. | `process_exception` must see view exceptions without changing `DatabaseRoleBoundaryMiddleware`, which has no `process_exception`. | Specify the exact position in the implementation PR, with a test proving the role-boundary 503 still runs first and view exceptions reach `AuthFailureMiddleware`. |
| R | **Residual risks** (unchanged: RB-1 to RB-13; B1b raw-output boundaries) | — | Orphaned undelivered sessions; the delivery gap after headers; no request or COMMIT bound; classifier dependence on Django and psycopg internals (RB-10, mitigated by pinned versions and chain tests); raw bootstrap, command and server output; development email; external logs and retention. |

## 6. Next gates

1. Independent review of this record. A finding about the approved policy goes back to the owner; it is not edited here.
2. Owner confirmation of the record (a PR comment) and of the A2 and A6 readings. A1, A3, A4, A7 and A8 can be settled by the implementation work order and its review.
3. A separate owner work order for B1c implementation.
4. Then independent code review and exact-head PostgreSQL 17 CI.

B1d, email, trusted devices, staging and deployment keep their own gates.
