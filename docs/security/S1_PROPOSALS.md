# Stage S1 design proposals — NOT implemented

Two items need review before any code is written:

* **S0-02** — implementation was paused by the owner after the lockout trade-off was raised (decision: "ship S0-01 only").
* **S0-03** — design requested; implementation not authorized.

---

## A. S0-02 — Per-account failed-login limiting

### A.1 The core problem

A per-username limit (10 failures in 15 minutes) slows guessing only if the
password is **not evaluated** once the limit is reached. That includes the
correct password. If the correct password were accepted, the attacker would
keep guessing and still win when a guess is right.

Refusing the correct password, however, gives a cheap denial of service:

* Usernames can be discovered (S0-04).
* About 10 requests per 15 minutes from any IP keep one student locked out indefinitely.
* A modest pool of addresses can lock out many students.

That is a significant account-lockout vulnerability, so the approved policy was
not implemented as written.

### A.2 Recommended design: account bucket plus device cookies (OWASP pattern)

| Element | Design |
| --- | --- |
| Account bucket | Key: `salted_hmac('ucc-login-account', 'login-account|' + NFKC(username).casefold())`. No plaintext username is stored. Unknown and known usernames are treated identically, with no DB lookup to choose the bucket. |
| Storage | **New table** `accounts_loginthrottle` (bucket PK, failures, expires_at). Same atomic upsert as `AuthThrottle`. A separate table is needed because a historical test asserts that login creates exactly one `AuthThrottle` row. New migration, auth-role grants in `configure_auth_role` (SELECT/INSERT/DELETE, UPDATE of failures and expires_at only), cleanup in `clear_auth_artifacts`, and no runtime grant (runtime grants are allow-listed, so new tables get none). |
| Concurrency | **Reserve before evaluating:** atomically increment, and return 429 without checking the password if the count is over the limit. On success, release the reservation (`failures - 1`, only when `expires_at` still equals the reserved window). So at most `limit` passwords are ever evaluated per window, even with parallel requests. |
| Device cookie | After a successful login, set `ucc_device` as a `django.core.signing` value (salted) containing an HMAC of the username and 16 random bytes. HttpOnly, SameSite=Lax, Secure as for the session cookie, max-age 90 days. It holds no personal data and has no DB row. |
| Trusted path | A request with a valid device cookie whose username HMAC matches the submitted username uses a per-device bucket (10 failures / 15 min) **instead of** the account bucket. A stolen cookie gives at most 10 guesses per window, and a new cookie can only be minted by a successful login. |
| Untrusted path | IP bucket (unchanged) plus account bucket. Over the limit, every attempt gets the same generic 429 and Retry-After, whether the username exists and whatever the password. |
| Responses | Identical 429 body for IP, account and device limits. No "account locked" message, and no email to the user. |
| Client data | The cookie only selects a throttle bucket. It never authenticates and never sets identity. The password is always required. |

**Behaviour of a correct password when the account limit is reached:**

* From a browser with a device cookie for that account: accepted, subject to its own device bucket.
* From any other browser: 429 until the window ends. This is deliberate, because evaluating the password would reopen guessing.

**Residual risks:**

* A student on a new or cleared browser can be locked out for as long as an attack continues.
* A shared lab computer's cookie works only for the account that logged in there.
* An attacker who steals a device cookie gets 10 guesses per 15 minutes.
* Rotating many IPs still lets an attacker cause lockouts on untrusted browsers.

Monitoring (S0-12) is needed to notice that.

### A.3 Alternatives considered

| Option | Why not preferred |
| --- | --- |
| Hard per-username limit with no device cookie | Cheap, indefinite targeted lockout (A.1) |
| Count failures but always accept the correct password | Gives no protection against guessing |
| Progressive delay with no block | Holds a worker per request, so it makes resource exhaustion worse |
| CAPTCHA | Third-party dependency or service; not allowed without approval |
| MFA | Strongest option, but a product and feature decision outside S1 |

### A.4 Tests that would accompany it

* Ten failures for one username from ten distinct IPs, then 429 for an untrusted browser, including with the correct password.
* A device-cookie browser can still log in during that time.
* An unknown username gets identical status codes, bodies and row behaviour.
* Concurrent attempts (threads with a barrier) never evaluate more than `limit` passwords.
* Expiry restores access.
* Another account is unaffected.
* A forged, tampered or other-account device cookie is ignored.
* No plaintext username is stored in throttle rows.
* The auth role grants on the new table are least-privilege, and runtime has none.
* All historical tests stay unchanged.

**Decision requested:** approve A.2 (with or without the device cookie skipping
the IP bucket for returning students behind a shared NAT), or choose another
option.

---

## B. S0-03 — Per-student record quotas (design only)

Initial caps: **200 semesters, 1,000 courses, 5,000 assignments** per student.

### B.1 Where to enforce

Enforce in `academics.services.StudentRecords.create`, inside the existing
`student_transaction(identity)`:

* The owner comes from the signed capability, never from the client.
* The count runs as the restricted runtime role through the existing owner filter **and** forced RLS: `Model.objects.filter(owner_id=owner).count()`. It only ever sees that student's rows.
* No access to `accounts_student` is needed. Runtime keeps zero account privileges, and the RLS policies, verifier and grants are unchanged.
* Updates and deletes are not capped. A student who is over a cap (none exist today) can still edit and remove records.

### B.2 Concurrency

Count-then-insert is racy: two simultaneous creates at 199 would both see 199
and both insert, ending at 201. To serialize creates per owner without touching
the Student table:

* Call `pg_advisory_xact_lock(<64-bit key derived from owner UUID and record kind>)` at the start of the create, inside the student transaction.
* PostgreSQL releases the lock automatically at commit or rollback, so it cannot leak across requests or pooled connections.
* Runtime can already call it (default PUBLIC EXECUTE). No new grant is needed.
* The key comes from the trusted owner UUID. A hash collision with another student only adds a brief wait; it never affects correctness or visibility.

Locking a parent row was rejected: semesters have no accessible parent row, and
a course cap applies across all semesters.

`SERIALIZABLE` isolation was rejected because it would need retry logic in every
caller.

A later defence-in-depth step could add a DB-side BEFORE INSERT trigger that
enforces the same caps against direct SQL by runtime. That needs a migration and
a security review of a `SECURITY DEFINER` count function. Not proposed for the
first change.

### B.3 Legitimate needs

| Kind | Cap | Typical need | Notes |
| --- | --- | --- | --- |
| Semesters | 200 | 8–16 over a degree | Matches the existing analysis limit (`MAX_SEMESTERS`) |
| Courses | 1,000 | 40–80 over a degree | Matches the existing analysis limit (`MAX_COURSES`). Above it, GPA pages already refuse to show a partial GPA, so a create cap stops students making data their own pages cannot analyse. |
| Assignments | 5,000 | Hundreds | About 5 per course at the course cap. Lists are paginated, so there is no read-side cap today. |

The caps leave GPA formulas, grading, credit validation and semester ordering
unchanged.

### B.4 Behaviour and response

* A new `QuotaExceeded(InvalidRecord)` exception.
* The website shows a friendly HTTP 409 page: "You have reached the limit of N <kind>s. No records were changed."
* The legacy JSON surface has no create route.

### B.5 Limits of quotas alone

* Quotas bound storage per account, not write *rate*. Repeated updates are still unlimited, so a separate per-session or per-account write throttle is the second half of S0-03.
* Total storage still grows with the number of accounts. Registration is limited to 5 per hour per IP and needs email verification, so this is bounded but not fixed. Monitoring is needed.

### B.6 Tests that would accompany it

* At the cap, the next create fails and stores nothing. Delete one, and a create succeeds again.
* Twenty concurrent creates at cap−1 (threads, barrier, separate connections) give exactly one success.
* Another student's quota is independent.
* `require_runtime_role` still passes, the runtime role still has no account privileges, and forced RLS is still present.
* All calculation tests are unchanged.
