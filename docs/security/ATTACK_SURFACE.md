# Attack surface — Stage S0 baseline

Audited commit: `fefd3cae4efeac5539bc3f02e9ffdc53bfb88766`. Website profile:
`config.settings.web_development` / `web_secure` (`ROOT_URLCONF=config.web_urls`).

## 1. HTTP routes (website profile)

`config/web_urls.py` includes BOTH `student_web.urls` and the Milestone 3
`config.auth_urls`. The legacy demonstration routes therefore stay reachable on
the website.

| Route | Methods | Auth | CSRF | Rate limit | Inputs | Handler |
| --- | --- | --- | --- | --- | --- | --- |
| `/accounts/register/` | GET, POST | none | yes | 5/h/IP (POST) | username, email, password1, password2 | `accounts/views.py:26` |
| `/accounts/login/` | GET, POST | none | yes | 10/15 min/IP (POST) | username, password; `next` is ignored | `accounts/views.py:41` |
| `/accounts/logout/` | POST | session | yes | none | — | `accounts/views.py:56` |
| `/accounts/verify/request/` | GET, POST | none | yes | 5/h/IP (POST) | email | `accounts/views.py:63` |
| `/accounts/verify/<uuid>/<secret>/` | GET, POST | token | yes (POST) | 20/h/IP (GET and POST) | selector, secret (path) | `accounts/views.py:78` |
| `/accounts/reset/` | GET, POST | none | yes | 5/h/IP (POST) | email | `accounts/views.py:63` |
| `/accounts/reset/<uuid>/<secret>/` | GET, POST | token | yes (POST) | 20/h/IP | new_password1/2; selector, secret (path) | `accounts/views.py:93` |
| `/accounts/password/change/` | GET, POST | verified session | yes | 5/15 min/IP (POST) | old_password, new_password1/2 | `accounts/views.py:134` |
| `/accounts/academic/` | GET | verified session | n/a | none | — (redirects to dashboard) | `accounts/views.py:172` |
| `/accounts/academic/courses/<uuid>/` | GET, POST | verified session | yes | none | version, actual_grade; JSON response | `accounts/views.py:185` (legacy) |
| `/accounts/academic/assignments/<uuid>/delete/` | POST | verified session | yes | none | version | `accounts/views.py:203` (legacy) |
| `/` | GET | verified session | n/a | none | semester, page | `student_web/views.py:54` |
| `/semesters/`, `/courses/`, `/assignments/` | GET | verified session | n/a | none | page (1–10000), semester, status, sort | `student_web/views.py:68-96` |
| `/{semesters,courses,assignments}/new/` | GET, POST | verified session | yes | none | model fields (StrictForm) | `student_web/views.py:123` |
| `/{kind}/<uuid>/edit/` | GET, POST | verified session | yes | none | model fields, version | `student_web/views.py:123` |
| `/{kind}/<uuid>/delete/` | GET, POST | verified session | yes | none | version, confirm | `student_web/views.py:161` |
| `/assignments/<uuid>/status/` | POST | verified session | yes | none | version, completed | `student_web/views.py:192` |
| `/performance/` | GET | verified session | n/a | none | — | `student_web/views.py:207` |
| `/predictor/` | GET, POST | verified session | yes | none | semester (GET); `grade_<hex>` up to 200 fields | `student_web/views.py:212` |
| `/planner/` | GET, POST | verified session | yes | none | target, remaining | `student_web/views.py:241` |
| `/settings/` | GET | verified session | n/a | none | — | `student_web/views.py:255` |
| `/static/<path>` | GET | none | n/a | none | path | Django `serve` with `insecure=True`; only when `UCC_LOCAL_STATIC` (dev/test profiles) |

There are no file uploads, admin site, REST API, websockets, search endpoint or
redirect parameter. Upload-specific risks are **Not applicable**.

## 2. User-controlled input inventory

| Input | Server validation | Sink |
| --- | --- | --- |
| username (register) | Regex `[A-Za-z0-9][A-Za-z0-9_.-]{2,29}` | ORM insert |
| username (login) | ≤150 chars in backend | ORM `get(username=)` |
| email | `EmailField` ≤254, ASCII only, lowercased; DB CHECK for normalized form | ORM; email recipient |
| passwords | 12–128 chars; Django validators | PBKDF2 hasher |
| token selector / secret | URL `uuid` converter; secret is 43 ASCII chars; SHA-256 digest compared in constant time | ORM |
| semester label | ≤120; DB CHECK non-blank | ORM; template (escaped) |
| display_order | 0–2147483647 | ORM |
| course code | Regex `^[ A-Za-z0-9_./-]+$` ≤64; normalized; DB unique per owner | ORM; template |
| course name | ≤200; DB CHECK non-blank | ORM; template; predictor form label (escaped) |
| credit_units | Decimal, 0.0001–1000000, ≤4 dp (`checked_credits`); DB CHECK range and scale | Decimal arithmetic |
| actual_grade | Choice A–F or blank (`checked_grade`); DB CHECK | ORM |
| assignment title | ≤240; DB CHECK non-blank | ORM; template |
| due_date | `%Y-%m-%d` only | ORM |
| semester_id / course_id (parent) | Choice limited to the owner's records; services re-check owner; composite FK | ORM |
| record UUIDs (path) | URL `uuid` converter, then owner-scoped `get` | ORM |
| version | 1 to 2^63−2 (forms); service `expected_version` | Optimistic lock compare |
| page | 1–10000 | Paginator |
| status, sort filters | Fixed choice lists, re-checked in `queries.page` | ORM filter |
| predictor grades | Choice per course; max 200 courses | Pure calculation, not stored |
| planner target, remaining | `checked_target` (0–5, 4 dp), `checked_credits` | Pure calculation, not stored |
| Unknown POST fields | `StrictForm` rejects them; legacy views use explicit allow-lists | — |
| Host header | `ALLOWED_HOSTS` localhost only | — |
| REMOTE_ADDR | Trusted as is; truncated to 128 chars, HMAC-ed | Throttle bucket |

## 3. Raw SQL inventory (all reviewed)

| Location | User data? | Parameterization |
| --- | --- | --- |
| `accounts/throttling.py:19` | HMAC bucket (derived) | `%s` parameters |
| `accounts/boundary.py:9`, `academics/ownership.py:94,108` | none | static SQL |
| `academics/ownership.py:143-148` | owner UUID, signature (server-generated) | `%s` parameters |
| `academics/migrations/0004_student_rls.py:61` | none | f-string over constant table names only |
| `academics/migrations/0002_owner_relationships.py:8` | none | static |
| `configure_runtime.py`, `configure_auth_role.py`, `tools/prepare_security_test_roles.py` | role names and key from operator env | `psycopg.sql.Identifier` / `sql.Literal` / `%s` |

No raw SQL builds statements from request data.

## 4. Database principals

| Role | Intended | Observed on disposable cluster (P09) |
| --- | --- | --- |
| runtime | DML on 3 academic tables under forced RLS; EXECUTE verifier | Matches. Also can CONNECT and use TEMP in the `postgres` database, and can create large objects (cluster PUBLIC defaults; S0-10) |
| auth | Account, token, throttle and session tables; column-limited UPDATE | Matches. INSERT on `accounts_student` covers all columns, including `is_active` and `email_verified_at` (S0-09) |
| migrator | Owner of the schema; offline only | Has CREATEDB in the test helper only |

## 5. Secrets and configuration surface

* Settings read secrets only from the environment (`config/settings/base.py:6-13`). No defaults and no SQLite fallback.
* `.env.example` contains names only. It is not loaded automatically.
* CI generates ephemeral secrets per run and masks them (`.github/workflows/quality.yml`).
* `DEBUG=False` in every profile except `development.py`, where it needs explicit `DJANGO_DEBUG=1` and the profile has no web URLs. `production.py` refuses to load.

## 6. Legacy CLI and Streamlit

These are local programs with fixed JSON filenames. There is no path input from
users and Streamlit is bound to `127.0.0.1` (`.streamlit/config.toml`). They are
not a network attack surface unless someone rebinds them. AGENTS.md forbids
public deployment of them.
