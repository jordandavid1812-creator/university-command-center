# GP2 proposal: versioned grading-policy catalogue

Status: DESIGN ONLY — requires independent review and owner approval before schema work.
No policy, institution, programme, publisher privilege or activation is approved by this document.

## Verified baseline and purpose

Master: `70576145910bbe92344bc12699b4fc60343ab412`.
PR #106 introduced the pure policy core; PR #108 closed four regression-test gaps.
Master push [run 44598505368](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/44598505368)
completed successfully in all six quality jobs, including PostgreSQL 17.
This is historical baseline evidence, not evidence that this proposed schema exists.

The owner wants eventual coverage of all Nigerian universities and programmes.
Coverage must grow through verified official sources, not a universal default scale.
A university listing does not verify its programmes, accreditation or grading rules.
A student's free-text institution/programme is not proof of affiliation or applicability.

See [the GP1 API and limitations](POLICY_CORE.md). This document proposes the next
reviewable boundaries; it does not authorize changing calculations, existing saved
records, academic services, authentication or live database configuration.

## Current source constraints

| Existing source | Consequence for the design |
| --- | --- |
| `grading_policy.py` | Pure immutable rules: one uppercase letter per grade, exact points, zero and maximum endpoints. No institutional verification or persisted identity. |
| `academic_logic.py` | All existing callers default to legacy five-point calculations. Policy-aware helpers support one policy per call, not mixed-policy transcripts. |
| `server/academics/models.py` | StudentProfile institution/programme are free text. Course has a fixed A–F CHECK, unique normalized code per student and no score or policy binding. |
| `server/academics/ownership.py` | Signed student/session context and forced RLS protect student tables. The runtime boundary has explicit table and privilege checks; new tables are not automatically covered. |
| `server/accounts/boundary.py` | Separate auth-role allowlists and Supabase API-role denial must remain intact. |
| `tools/export_supabase_sql.py` | SQL is generated from migrations/provisioning; do not hand-edit numbered SQL files or grant Data API roles access. |
| `tools/backup_database.py`, `docs/BACKUPS.md` | Backup/restore is allowlisted and encrypted; new reference data needs an explicit restore/export design. |
| `AGENTS.md` account-deletion rule | Any future FK to Student requires updating the deletion function and its ownership tests in the same implementation PR. |

GP2 must not insert an institution into an existing student's profile, relax Course
constraints, reinterpret past grades, or pass a four-point definition into existing
legacy-only forms/class bands. No extra website database reads are proposed now.

## Proposed records and constraints

Suggested future Django app: `server/grading_catalogue/`, separate from student-owned
academics. This name and all objects below are proposals, not existing implementation.
UUIDs identify records; display names do not establish relationships or chronology.

| Record | Proposed information | Required enforcement |
| --- | --- | --- |
| University | UUID, stable internal code, official name, evidence reference, catalogue timestamps | Unique internal code; renames preserve UUID. A listing is separate from grading verification. |
| Programme | UUID, university FK, stable local code, title and award descriptor | Unique `(university, code)`; protected parent deletion. Distinct campuses/modes/award variants need explicit identity when rules differ. |
| PolicyRevision | UUID, stable policy identifier, revision, schema version, explicit maximum, content hash | Unique `(identifier, revision)`; no published payload mutation. Hash is integrity/provenance, not authority. |
| GradeRule | revision FK, grade letter, exact points | Unique `(revision, grade)`; ASCII A–Z; finite points from 0 to maximum; at most four decimal places. Release requires both scale endpoints. |
| PolicyApplicability | revision FK, explicit programme FK, admission-cohort range and academic-session range | Cohort and session are independent dimensions. No implicit university-wide inheritance or name-based matching. |
| SourceEvidence | UUID, official URL, retrieval/publication dates when known, artifact SHA-256, bounded citation/excerpt and locator | Missing/unknown dates stay unknown. URL alone or a mutable link is insufficient release evidence. Safe plain text; no executable HTML. |
| RevisionEvidence | revision/evidence links and exact rule/applicability citations | Release requires traceability for the full supported rule subset, not merely an A/B example. |
| ReviewDecision | exact revision content hash, reviewer reference, decision, rationale, time | Append-only; stale hashes cannot approve modified content. No student credentials or tokens. |
| PublicationEvent | revision, approved content hash, release/withdrawal/supersession event, actor reference, time | Append-only history; validity is not a freely editable Boolean. |

GP2a proposes University, Programme, draft PolicyRevision, GradeRule,
PolicyApplicability, SourceEvidence and RevisionEvidence only. ReviewDecision and
PublicationEvent belong to GP3. GP2a constrains revision state to DRAFT at the
database level; changing that constraint requires the separately reviewed release
guard. No synthetic fixture is advertised as released or institutionally verified.

Academic session is represented by a validated starting year with an explicit label
(e.g. a synthetic `2026/2027` fixture), not Semester.label. Admission cohort has its
own starting year. Proposed ranges are lower-inclusive/upper-exclusive; an absent
bound is allowed only if the official evidence explicitly supports an open bound.
Unknown scope is not a wildcard. Entry route, campus or mode differences not captured
by a reviewed applicability dimension make a case unsupported, not broadly covered.

Initially applicability names programmes explicitly. An official university-wide
rule may supply evidence for several explicit programme links; it must not create
an automatic rule for every current/future programme. Accreditation/course catalogue
completeness is a separate claim that this system does not make.

Numeric columns must not silently round unsupported inputs: use unconstrained
PostgreSQL NUMERIC plus finite/range/four-decimal checks, following the existing
exact-credit approach. A scaled NUMERIC column alone rounds before a CHECK sees the
original input. Python validation and direct-SQL PostgreSQL tests are both required.
Cross-row scale endpoints, maximum agreement and publication completeness need a
reviewed database release guard; an ordinary CHECK or FK cannot enforce them alone.

Foreign keys use PROTECT/RESTRICT for referenced universities, programmes, revisions
and evidence. A future deletion/retention operation must be explicitly designed;
no general cascading removal of policy history is proposed. Actor references should
be opaque operational identifiers, not new Student FKs or raw personal log fields.
Their governance/retention remains an owner decision before publication tooling.

## State transitions, immutability and historical meaning

Proposed lifecycle: `DRAFT -> REVIEW_READY -> RELEASED`.
A rejected review returns a draft to editing and invalidates approval of its old hash.
Released payload, grade rules, applicability and evidence links become immutable.
Amendments create a new revision; changing a child row must be guarded as strictly as
changing its parent. No direct status UPDATE may bypass the release guard.

Withdrawal and supersession are new events, not edits to history or deletion of rules.
A later revision does not invalidate an older cohort's rule automatically. A withdrawn
revision is ineligible for new bindings; a future student-facing flow must flag affected
existing bindings and follow an approved correction process, rather than silently
switching scales. No binding/correction workflow is implemented in GP2.

Content hashing needs a versioned canonical representation: sorted grade rules and
applicability links, exact canonical decimal strings, explicit null/open-bound meaning,
source artifact hashes and evidence links. Review signs off on that complete snapshot.
A hash collision/implementation error is not treated as proof of authority; review and
privilege boundaries remain required. Canonicalization golden tests precede release work.

Immutability guards constrain ordinary publisher privileges, not the DBA or migrator,
which can alter triggers/policies. Do not claim protection from privileged operators.

## Publication races and ambiguity

Draft applicability may overlap while evidence is evaluated. Released/eligible revisions
must not offer conflicting rules for the same programme, cohort, session and any approved
additional dimensions. Dates must not choose a winner by "latest row" ordering.

Before a future release, a database-controlled operation must serialize releases for all
affected programme UUIDs in a fixed lock order, re-read conflicts after acquiring locks,
verify the expected draft version/hash and evidence, and commit the publication event
atomically. Competing/stale publication fails without partial release. Actual PostgreSQL
concurrency tests must prove this; application-only prechecks are insufficient.

Direct publication-table writes are denied to ordinary callers; only an independently
reviewed release operation could acquire publication authority. No new extension such
as btree_gist is implicitly approved. Exact SQL/locking implementation and permitted
publication role require a later reviewed GP3 proposal. No retries after ambiguous COMMIT.

A future resolver must return exactly one eligible revision or a typed missing/ambiguous/
unsupported outcome. It must never fall back to another university or rescale a transcript.
GP2 introduces no resolver into live calculations; existing legacy workflows remain as-is.

## Privilege and RLS proposal

Reference policies are global institutional data, not records owned by a particular student.
Do not manufacture an owner UUID or weaken signed student policies to make them readable.

| Principal | GP2a proposed access | Future access, subject to separate review |
| --- | --- | --- |
| Academic runtime | None on new catalogue tables/functions | Read only an approved released projection; no drafts, evidence-review notes or writes. Existing student-table privileges remain unchanged. |
| Authentication role | None | None; login and sessions do not need grading-policy authoring. |
| Supabase anon/authenticated/service_role, PUBLIC | None | None; no browser Data API access. |
| Existing migrator | DDL and approved fixture setup in disposable tests | Privileged maintenance only; never website request credentials. |
| Publisher | No role created or granted by GP2a | Separate least-privilege offline capability, explicit release operation; never website credentials or student-table access. Requires approval. |
| Extraction/monitor worker | Not introduced | Proposal/evidence creation only, never publication or student data. Separate later design. |
| Backup role | Existing privileges unchanged initially | Explicit reviewed reference export/restore access, never broad table SELECT defaults. |

GP2a enables and forces RLS on new catalogue tables, with no website policies/grants;
normal runtime/auth/API reads and writes fail closed. Proposed draft maintenance
uses an explicit owner-only RLS policy targeting the configured migration role,
with no role membership or SET ROLE path from web logins. FORCE RLS does not itself
give even the table owner row access; tests must prove fixtures work through that
explicit policy rather than bypassing RLS. The migration role remains privileged
and unavailable to the web process. Test missing-policy and grant drift
explicitly. The privileged migrator may alter schema; test fixtures must not pretend it
is a safe publisher. Before any future runtime read projection, review base-table grants,
view ownership/security_invoker behaviour and forced-RLS policies against real restricted
logins. A definer view must not become an unintended draft-data or student-data bypass.

If a future release operation needs SECURITY DEFINER, require a fixed safe search_path,
fully qualified objects, trusted owner, PUBLIC EXECUTE revoked, exact argument validation,
no dynamic client identifiers, and no runtime ability to invoke it or change its owner.
No definer function or new grant is approved by this design draft.

Provisioning and startup checks must reject unauthorized catalogue writes, memberships,
object ownership, BYPASSRLS and PostgreSQL 17 MAINTAIN. Preserve current role checks rather
than simply adding a new table to the student-owned table count. Runtime connections must
continue to fail closed on drift. Test direct SQL with actual LOGIN roles, not a superuser
SET ROLE shortcut. Transaction-pooler reuse must not carry unpublished access or identity.

## Evidence ingestion, privacy and operations

GP2a has no source-fetching code, AI requests or real institutional seeds. Only synthetic
fixtures are allowed until manual evidence handling and publication authority are reviewed.
Source rows are data, not instructions: URLs cannot trigger a fetch or supply credentials.
Later retrieval needs allowlisted official sources, SSRF/redirect/DNS protection, isolated
parsing, bounded artifacts and prompt-injection controls; it cannot reuse student consent
or silently consume the study-assistant budget. AI can propose, never approve.

Before storing real artifacts, decide permitted source licensing, document retention and
PII handling. Public university documents can contain names or identifiers. Avoid copying
unrelated personal data into excerpts. Never upload student records, grades or identifiers
to a policy-monitoring provider. External services/regions or processing changes require
updating privacy.html and LEGAL_UPDATED together under AGENTS.md.

A catalogue backup/restore requirement belongs in GP2a's implementation acceptance, before
persistent use. Choose explicit reference-data export/restore support (the existing student
backup allowlist does not automatically include it). Restore policies/evidence/reviews in
FK order and prove hashes, access rules and references survive. No new backup grant is
implied by this proposal; if restoring student-linked policies later, restore the exact
referenced revisions as well. Missing historical revisions must fail closed, not default.

Generated Supabase SQL must remain in sync with migrations/provisioning and pass the existing
SQL/pooler tests. Never apply numbered SQL to a live database as part of this design work.
Before a separately authorized deployment: inspect actual migration history, rehearse upgrade,
plan maintenance/provisioning/rollback, and verify website/runtime and auth permissions before
returning to operation. Do not fake migrations or reverse a populated migration casually.

## Small implementation gates

| Increment | Deliverable | Required gate |
| --- | --- | --- |
| GP2a | Schema for draft catalogue, exact constraints, forced RLS and denied website access; synthetic fixtures; migration/provisioning/startup/SQL-export and catalogue backup/restore compatibility | Approve this revised schema/role design first. Separate draft implementation PR. No Student bindings, publisher role, source fetch, real seeds or website reads. |
| GP2b | Pure canonical snapshot/adapter validation and offline draft inspection using synthetic data | Review supported rule subset and deterministic hash contract. Does not release or select policies. |
| GP3 | Manual evidence verification, restricted publication operation and append-only review/release history | Approve publisher identity/authority, evidence handling, transaction algorithm and operational access. No AI authority. |
| GP4 | Student-owned programme/policy bindings, owner FKs/RLS, historical pinning and labelled selection | Separate schema/security/privacy/export/deletion review; resolve mixed-policy and compatibility limits before activating calculations. |
| GP5+ | Official-source retrieval, AI-assisted change proposals, then scheduling | Separate provider, source, privacy, cost and job-execution approvals; never automatic publication. |

GP2a is the smallest proposed implementation slice. If complete review/history tables or
reference backup support make it too large, split those into separate dormant schema PRs
with independent gates; do not expose an incomplete catalogue to website requests.

## Required implementation test matrix

| Area | Required evidence before its respective gate |
| --- | --- |
| Legacy compatibility | Existing core/CLI/Streamlit, website, auth and browser suites; seven GP1 mutation controls remain effective. No new website query or result change in GP2a. |
| PostgreSQL precision | Raw SQL rejects nonfinite/negative/out-of-range/overprecision points without silent scale rounding; Python validators agree. |
| Integrity | Unique references/grade rules, protected FKs, mismatched maximum, missing endpoints; parent/child mutation after release rejected by later publication guard. |
| Applicability | Cohort/session boundary fixtures, unknown scope, campus/mode exceptions, overlap/ambiguity and no automatic university inheritance. |
| Role boundary | Actual runtime/auth/API/PUBLIC direct-SQL denials on drafts and writes; forced RLS, memberships, ownership, column grants, default privileges and MAINTAIN drift. |
| Migrations | Fresh PostgreSQL 17, upgrade from exact master history, reverse/reapply only on disposable data, grants re-provisioned, generated Supabase SQL unchanged by re-export. |
| Concurrency (GP3) | Two independent connections release overlapping scopes, stale review hashes, child edits during approval, rollback and ambiguous COMMIT. No partial publication. |
| Publication visibility (GP3+) | Draft/rejected/withdrawn definitions unavailable for new bindings; no privileged-view bypass or stale process cache. Pooler tests use real separate logins. |
| Backup/restore | Synthetic catalogue/reference data restores with exact hashes and denies unauthorized access; existing encrypted student backup and account deletion suites remain intact. |
| Privacy/security | Source strings rendered safely, no credential/identifier/sensitive query-string leakage, bounded resources; no external network in tests/CI. |

Negative controls must deliberately remove precision validation, forced RLS, an access-denial
check, publication immutability or ambiguity guards when those features exist. Require green
controls and specific failing assertions, not no-op edits/import errors. This document does
not claim those future controls or PostgreSQL experiments have been implemented or run.

## Owner decisions still required

1. Approve the initial programme-specific applicability representation and GP1-compatible
   letter/point subset. Medical/pass-fail/exclusion/repeat/rounding/classification rules
   outside it remain unsupported; numerical score conversion is not inferred.
2. Approve GP2a's dormant schema and role-denial scope before implementation. No new publisher
   or worker credential is authorized by the general national-coverage goal.
3. Select publication accountability: initially an owner-controlled offline operation is
   recommended; whether independent second-person sign-off is mandatory remains pending.
4. Approve the first official-source batches and artifact licensing/retention/privacy policy
   before real data is ingested. An official institution registry is not grading evidence.
5. Approve catalogue backup/restore support and any precise additional read grant before
   persistent reference data exists. Do not widen the student backup role implicitly.

This document recommends defaults; none of these choices is recorded as owner-approved.
The next safe action is independent review of this proposal, then explicit authorization
of an exact GP2a implementation scope. Do not start GP2a simply because this document merges.

## Documentation-only acceptance and rollback

This PR may change only this proposal file. Check Markdown links, whitespace, references,
no conflict markers and repository safety; request exact-head hosted CI. Passing design CI
proves repository compatibility, not correctness of the proposed unimplemented schema.

No schema, application, academic math, auth, tests, grants, migration, SQL export, secrets,
source download, AI call or deployment is changed. Rollback is removing this document.
