# GP2 proposal: versioned grading-policy catalogue

Status: DESIGN ONLY — requires independent review and owner approval before schema work.
No policy, institution, programme, publisher privilege or activation is approved by this document.

## Verified baseline and purpose

Historical design-source baseline: `70576145910bbe92344bc12699b4fc60343ab412`.
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
| Programme | UUID, university FK, stable local code, award/campus/mode/entry-route identifiers and display title | Immutable identity tuple from creation; unique `(university, code)`; protected parent deletion. Identity changes require a new row/UUID with explicit lineage. Display renames cannot change applicability. |
| PolicyRevision | UUID, stable policy identifier, revision, schema version, explicit maximum, draft record_version and content hash | Unique `(identifier, revision)`; monotonic draft version includes child changes; no published payload mutation. A draft hash may remain unset until GP2b canonicalization exists; no release without a verified canonical hash. |
| GradeRule | revision FK, grade letter, exact points | Unique `(revision, grade)`; ASCII A–Z; finite points from 0 to maximum; at most four decimal places. Release requires both scale endpoints. |
| PolicyApplicability | revision FK, explicit programme FK, admission-cohort range and academic-session range | Cohort and session are independent dimensions. No implicit university-wide inheritance or name-based matching. |
| SourceEvidence | Immutable snapshot UUID, official origin, retrieval/publication dates when known, artifact SHA-256 and logical artifact reference, bounded citation/excerpt and locator | Append-only from creation, including draft evidence. Corrections create a new UUID; no payload UPDATE or referenced DELETE. Missing/unknown dates stay unknown. Safe plain text; URL or digest alone is insufficient release evidence. |
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

## Stable catalogue identity (GP2-R2)

GP2a must enforce the immutable Programme identity tuple from creation:
`(university_uuid, local_code, award_id, campus_id, study_mode_id, entry_route_id)`.
These are bounded stable identifiers, not display names. The local code is an internal
variant key; it must not assume an official programme code distinguishes all variants.
University UUID and its
stable internal code are also immutable. Unknown optional dimensions are represented
explicitly as unknown, never as "all variants"; a policy cannot be released for a case
where an unknown dimension can affect its rules. Exact identifier formats and supported
dimensions require the pending owner/schema approval before GP2a implementation.

A transfer between universities or a different award/campus/mode/entry-route identity
requires a new Programme UUID and an explicit predecessor reference. Old rows and their
applicability remain intact. An audited display-title rename may retain the identity,
but cannot change resolution or rewrite a published manifest's captured display labels.
A registry-code alias or institutional reorganization needs an explicit correction
workflow; it cannot silently reassign an existing institutional identity.

PROTECT/RESTRICT on deletion alone does not prevent FK reassignment. GP2a must include
database guards against updates to identity fields, plus direct-SQL tests, even before
publication exists. Future canonical applicability pins both the programme/university
UUIDs and the complete immutable identity tuple, scope ranges and unknown-bound meanings.
Shared rule content may apply to different institutions only through separately explicit,
source-backed applicability links; it never implies institution-wide inheritance.

## Immutable evidence snapshots (GP2-R1)

SourceEvidence payloads are append-only from creation, not merely once published. GP2a
must enforce no payload UPDATE and no deletion of referenced evidence through ordinary
access paths, with database guards as well as grants. An artifact digest, official origin,
citation/excerpt, locator or source-date correction creates a new snapshot UUID. Linking
that new snapshot into a draft is a versioned draft edit that invalidates prior approval.
Existing released revision/evidence links continue to name their original snapshot.

Mutable operational annotations, if needed later, are separate records and cannot change
approved payload fields, eligibility or the canonical manifest. A physical storage mirror
may change only under a reviewed availability mechanism that retrieves the same bytes and
checks the pinned digest; it must not substitute content under an existing logical artifact
reference. No artifact storage service or retention policy is approved here.

The GP2b canonical manifest must include bounded, schema-versioned representations of:
revision identity/schema/maximum, sorted exact grade rules, complete applicability identity
and ranges, evidence snapshot UUIDs, official origin, logical artifact reference, artifact
digest, citation/excerpt, locator, explicit known/unknown source dates and captured labels
needed to understand the approval. Decimal/time/text normalization and all field bounds
need golden tests. Hashing a mutable evidence UUID or artifact digest alone is insufficient.

A digest proves byte equality when the artifact is available; it does not retain the
artifact or prove official authority. Before GP3 publication, the approved evidence-access
and retention process must let an authorized reviewer retrieve the pinned artifact and
verify its digest. A live URL plus an unavailable digest is not sufficient to release.
Real artifact ingestion, retention/access, licensing and privacy choices remain pending.

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

Content hashing uses the complete versioned manifest defined under immutable evidence
above. The manifest pins immutable institutional identity and source payloads, not only
indirect references. Review signs off on that exact snapshot, not on a mutable live join.
A hash collision/implementation error is not treated as proof of authority; review and
privilege boundaries remain required. Canonicalization golden tests precede release work.

Immutability guards constrain ordinary publisher privileges, not the DBA or migrator,
which can alter triggers/policies. Do not claim protection from privileged operators.

## Publication races and ambiguity

Draft applicability may overlap while evidence is evaluated. Released/eligible revisions
must not offer conflicting rules for the same programme, cohort, session and any approved
additional dimensions. Dates must not choose a winner by "latest row" ordering.

Proposed synchronization contract, to be proven in GP3 on PostgreSQL 17:

1. Each revision starts with a positive `record_version`. Draft changes to the parent,
   grade rules, applicability or revision/evidence links lock that revision's parent row
   before changing its logical payload, verify an expected version where relevant, and
   increment the version atomically in the same transaction. Direct SQL cannot bypass
   the parent-lock/state/version guard. Immutable evidence and identity rows cannot be edited.
2. Initial publication handles one revision per transaction. It locks the revision parent
   first, then discovers its protected applicability and locks all affected Programme rows
   in sorted UUID order. The same parent-before-programme order applies to every operation
   that needs both. No operation may acquire another revision's parent after programme locks;
   multi-revision publication is unsupported until separately designed. Draft edits need
   the parent lock; they cannot race a publication snapshot by changing a child independently.
3. Use an explicitly verified READ COMMITTED transaction. After acquiring locks, execute
   fresh reads of committed release conflicts, eligibility and the complete canonical
   manifest. Recompute the hash and compare the expected version/hash and approved decision.
   Do not reuse a pre-lock snapshot, trust a client-supplied hash, or assume a REPEATABLE READ
   snapshot refreshed after waiting. Check conflicts in the same protected programme scope.
4. Insert the release event and make the revision immutable atomically. Withdrawal and
   supersession operations that alter eligibility obey the same synchronization boundary.
   A waiting publisher rechecks committed state after getting its programme locks; stale
   approvals, conflicting applicability and child edits yield a conflict without partial release.

GP2a must define draft version/child-change guards; GP2b defines canonicalization. The exact
GP3 SQL, review-ready edit semantics, transition guards and lock/deadlock behaviour still
require independent implementation review and two-connection tests. This is not a claim
that an RLS policy, FK or application precheck alone implements publication synchronization.

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
| Backup role (`ucc_backup`) | Existing privileges unchanged initially. It already has BYPASSRLS, read-only transactions and SELECT only on `BACKUP_TABLES` (`supabase/backup/backup_role.sql`). | Either add catalogue tables to its explicit allowlist, or a separate reference-export login; owner decision. Never broad table SELECT defaults. |

GP2a enables and forces RLS on new catalogue tables, with no website policies/grants;
normal runtime/auth/API reads and writes fail closed. Proposed draft maintenance
uses an explicit owner-only RLS policy targeting the configured migration role,
with no role membership or SET ROLE path from web logins. On plain PostgreSQL 17,
FORCE RLS does not itself give even the table owner row access; tests there must prove
fixtures work through that explicit policy rather than bypassing RLS. On the live
Supabase database the migration login (`postgres`) bypasses RLS entirely (see the
account-deletion notes in docs/LAUNCH.md and migration academics.0024), so the policy
is not what protects the catalogue there; the restricted logins' missing grants and
policies are. Run the role-boundary tests on Supabase's own database image as well
(`tools/test_supabase_sql.py`), and never treat the migrator as a restricted principal
in either environment. The migration role remains privileged
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

Startup/preflight may query catalogue privilege metadata. Student workflows must not fetch
catalogue rows or gain extra request-time database round trips in GP2a. Incorporate required
per-request drift predicates into existing boundary queries where feasible; verify existing
query budgets and injected privilege/RLS drift together. Do not omit drift checks to make a
query-count assertion pass. If both requirements cannot be met, stop for a separately reviewed
query-budget/design decision rather than silently adding queries or weakening the boundary.

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

Reference backup/restore access is a pre-implementation owner decision for GP2a, not just
an operational follow-up. For a login without BYPASSRLS, SELECT alone does not permit
reading rows under FORCE RLS. The existing backup login `ucc_backup` already has BYPASSRLS
(owner-approved in launch step H; docs/BACKUPS.md), read-only transactions and SELECT only
on the tables listed in `BACKUP_TABLES` and `backup_role.sql`. The approved approach must
specify the exact export login, table/column grants, any explicit read-only RLS policy or
export function, encrypted output format, and restore actor/rights. The two options are:
(a) the simplest: add the catalogue tables to the existing encrypted backup's allowlist
(`BACKUP_TABLES`, `backup_role.sql`, restore tool and its test together), which needs no
new login or privilege; or (b) a separately restricted reference-export login without
BYPASSRLS plus an explicit read-only RLS policy. Neither is authorized by this draft.
Never give BYPASSRLS to any other login, add broad default privileges, or widen
`ucc_backup` beyond explicitly listed tables to solve this.

GP2a acceptance must run a restricted-login synthetic reference export/restore drill before
persistent use. Restore identities/evidence/revisions and links in valid FK order with exact
UUIDs, identity tuples, source payloads, versions and hashes; verify both data equality and
post-restore RLS/grants. Existing student backup/restore remains intact. GP3 must extend the
same contract to immutable review/publication history. For later student-linked policies,
restore the exact referenced revisions as well. Missing history fails closed, not default.
No export role, RLS policy, credential or live restore is approved by this document.

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
| Integrity | Unique references/grade rules, protected FKs, mismatched maximum, missing endpoints; draft parent/child version changes; immutable source payload and institutional identity enforced in GP2a; released-parent/child mutation rejected by the GP3 guard. |
| Applicability | Cohort/session boundaries, unknown scope and variant exceptions; direct university/identity reassignment rejected; display renames preserve resolution; new identities retain historical links; no automatic university inheritance. |
| Role boundary | Actual runtime/auth/API/PUBLIC direct-SQL denials on drafts and writes; forced RLS, memberships, ownership, column grants, default privileges and MAINTAIN drift. |
| Migrations | Fresh PostgreSQL 17 and Supabase's database image (where the migrator bypasses RLS), upgrade from exact master history, reverse/reapply only on disposable data, grants re-provisioned, generated Supabase SQL unchanged by re-export. |
| Concurrency (GP3) | Independent connections release overlapping scopes or edit draft children; verify lock order, stale versions/hashes, fresh post-lock READ COMMITTED reads, rejected edits after release, rollback and ambiguous COMMIT. No partial publication. |
| Publication visibility (GP3+) | Draft/rejected/withdrawn definitions unavailable for new bindings; no privileged-view bypass or stale process cache. Pooler tests use real separate logins. |
| Backup/restore | The approved export login (existing `ucc_backup` allowlist, or a separate restricted login) reads only the approved reference scope; unauthorized writes/reads denied; restored identities, source snapshots, FKs and hashes match; existing encrypted student backup and account deletion suites remain intact. |
| Privacy/security | Direct evidence UPDATE/referenced DELETE and artifact substitution rejected; new evidence snapshots invalidate old approval; source strings rendered safely, no secrets/PII leakage, bounded resources; no external network in tests/CI. |

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
5. Before GP2a implementation, approve the reference export/restore principal, exact
   grants/RLS access and restoration contract: option (a) list the catalogue tables in the
   existing encrypted backup (recommended, no new privilege), or option (b) a separate
   restricted export login. Do not widen the student backup role implicitly.

This document recommends defaults; none of these choices is recorded as owner-approved.
The next safe action is independent review of this proposal, then explicit authorization
of an exact GP2a implementation scope. Do not start GP2a simply because this document merges.

## Documentation-only acceptance and rollback

This PR may change only this proposal file. Check Markdown links, whitespace, references,
no conflict markers and repository safety; request exact-head hosted CI. Passing design CI
proves repository compatibility, not correctness of the proposed unimplemented schema.

No schema, application, academic math, auth, tests, grants, migration, SQL export, secrets,
source download, AI call or deployment is changed. Rollback is removing this document.
