# Milestone 3 plan and threat model

Starting master: 35aeb45432c8bff6ff00abb572d32f03bce2212d (PR #21 verified merged).

1. Keep CLI/Streamlit/calculations and all 192 existing tests intact. Add opt-in
   authentication settings/routes so historical foundation tests stay isolated.
2. Add required registration email/verification state (nullable for existing
   internal fixture accounts), hashed single-use email/reset tokens and shared
   PostgreSQL throttle buckets. No existing account is silently verified.
3. Keep application default DB credentials restricted academic runtime. Route
   accounts/sessions/tokens/throttles to a separate narrow auth LOGIN; never put
   DBA/migrator credentials in the web process. Provision roles only offline.
4. Use Django password validators/hashers, authentication/session machinery,
   CSRF middleware and forms. Case-sensitive ASCII usernames, unique normalized
   email, verified active accounts only. No social login or email changes.
5. Harden the capability factory: a persisted Student or is_authenticated flag
   alone is insufficient. Bind capabilities to a revalidated server-side Django
   session/current password hash. Preserve old 2B fixture minting only in its
   explicit non-web test settings; never in auth application settings.
6. Add registration/verification/resend, login/POST logout, password reset/change
   and minimal authenticated course/assignment demonstration routes. All academic
   operations use existing services/RLS; client owner fields are rejected.
7. Use transactionally consumed token digests, expiring DB sessions, session-key
   rotation, generic account lookup responses, database-backed bounded throttles,
   fixed local email link origin and safe redirects. Tests send no real email.
8. Test on actual PostgreSQL with separate migrator/academic/auth LOGIN roles.
   Cover forged instances/sessions, role denials, concurrent users, token expiry/
   reuse, CSRF, fixation, password/session revocation and existing RLS behavior.
9. Run all suites/audits/migration/safety checks, extend CI, document limits, push
   feature/student-authentication and open a master PR. No deploy/merge/Milestone 4.

Threat model: unauthenticated users, malformed forms, credential guessing,
CSRF, fixation, guessed/modified session or record UUIDs, replayed/expired email
links, deactivated accounts and SQL that bypasses academic services. Request
owner IDs/model instances must never authenticate anyone. Shared DB throttles
bound single-source guessing but are not a production distributed-abuse system.
The trusted Python process holds session/signing secrets and two narrow role
credentials; arbitrary Python execution, DBA/migrator compromise, email inbox
compromise and endpoint/device compromise are outside this boundary. Auth DB
compromise exposes sensitive account/session metadata and remains a material
risk. Keep secrets/SQL parameters/email-link logs private. Deployment, operational
email delivery, backup/restore, external pools and production abuse controls need
separate review. Only synthetic data is used for verification.
