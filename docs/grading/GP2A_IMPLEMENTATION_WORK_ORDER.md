# GP2a: dormant catalogue implementation work order

Status: PROPOSED — documentation only, for owner decisions and independent review.
The owner's request to continue authorizes this preparation; it does not establish
approval of the new schema or backup grants below. No university coverage is verified.

Prepared on 20 November 2026 against master
`808356e6c3c70f62f52bb9a09c6804a534a5f103` (PR #118).
The merged [catalogue design](CATALOGUE_DESIGN.md) remains authoritative. In particular:
“Do not start GP2a simply because this document merges.”
See also [the existing calculation core](POLICY_CORE.md),
[database security](../DATABASE_SECURITY.md) and [backups](../BACKUPS.md).

## Purpose and current evidence

Build the private storage foundation for future source-backed Nigerian university and
programme grading policies. The existing website's student-selected four/five-point
scales remain the only calculation inputs. A catalogue listing must not imply verified
grading rules, programme accreditation, student affiliation or complete national coverage.

Reconnaissance found the design and GP1 calculation core, but no catalogue Django app,
catalogue migrations or open GP2 implementation PR. Master quality run
[44740460273](https://github.com/jordandavid1812-creator/university-command-center/actions/runs/44740460273)
was still running its database job at preparation; its other five jobs had passed.
That observation is historical, not a claim of completed baseline verification. Reverify
the exact current master and all required quality jobs before implementation starts.

## Proposed first implementation boundary

One isolated draft implementation PR, with the seven tables below in a separate
`server/grading_catalogue/` app. Use synthetic data only. Include schema, database guards,
restricted-role tests, provisioning/preflight integration, generated Supabase SQL and
the approved reference backup/restore support. If that cannot remain a reviewable slice,
stop and propose a split; an incomplete catalogue must not enter persistent use.

No Student foreign keys, student-policy bindings, admin authoring screens, public routes,
website queries, policy publication, real institutional seeds, source fetching, AI calls,
schedulers, credentials or new dependencies are included. No live migration or deployment.
The current GPA formulas, saved letters, selected scale, class bands, authentication,
sessions and signed student ownership context must remain unchanged.

| Proposed model/table | Minimum contract |
| --- | --- |
| University / `grading_catalogue_university` | UUID, immutable unique internal code, bounded official display name, optional protected evidence reference, timestamps. Display renames preserve identity. |
| Programme / `grading_catalogue_programme` | UUID, protected university FK, internal local code and immutable award/campus/mode/entry-route identity identifiers; display title and optional protected predecessor reference. Unique university/local-code pair. |
| PolicyRevision / `grading_catalogue_policyrevision` | UUID, immutable identifier/revision pair, schema version, exact maximum, positive draft record_version, timestamps and nullable content hash. Database state is DRAFT only. |
| GradeRule / `grading_catalogue_graderule` | Protected revision FK, single ASCII uppercase grade, exact points, unique revision/grade. Database guards enforce maximum agreement. |
| PolicyApplicability / `grading_catalogue_policyapplicability` | Protected revision/programme FKs; separate cohort/session scope kinds and year bounds. No university-wide or name-based inheritance. |
| SourceEvidence / `grading_catalogue_sourceevidence` | Append-only snapshot UUID, origin, logical artifact reference, SHA-256, bounded citation/excerpt/locator, captured time and explicitly unknown source dates. No artifact download or storage service. |
| RevisionEvidence / `grading_catalogue_revisionevidence` | Protected revision/evidence FKs and bounded rule/applicability citations. Link changes are versioned draft edits. |

The table names are proposed exact names, not assertions that these tables exist.
ReviewDecision and PublicationEvent remain GP3. A digest, URL or DRAFT row is never
publication authority. Do not mark a fixture released or institutionally verified.

## D-GP2A-1: initial representation — PENDING owner approval

Recommended bounded subset:

- Reuse GP1's identifier alphabet and 1–64-character bound for internal codes and
  policy references. Programme identity is the full tuple specified in the merged design;
  unknown optional dimensions are explicit NULL/unknown, never “all variants”. Enforce
  immutable identity and protected relationship endpoints with database guards, not just
  Django `editable=False` or deletion policies. Reject self/cyclic predecessor lineage.
- Scope kinds initially support UNKNOWN or BOUNDED. UNKNOWN has no bounds and grants no
  applicability. BOUNDED has integer starting-year bounds in 1–9999, with lower < upper,
  lower-inclusive/upper-exclusive. Cohort and session are independent. Open ranges,
  unsupported variants and inferred “all programmes” rules are outside this first subset.
  This intentionally narrower proposal needs explicit approval; no real source is inferred
  to fit it. Academic-session labels do not derive from student Semester labels.
- Points and maximum follow GP1's exact finite numeric contract: points >= 0, maximum > 0
  and <= 100, points <= revision maximum, no nonzero precision beyond four decimal places.
  Use unconstrained PostgreSQL NUMERIC with explicit checks; do not silently round.
- Important compatibility detail: GP1 accepts trailing zeroes such as Decimal('1.00000').
  A bare `scale(value) <= 4` check copied from course credits would reject that value.
  Require a mathematically exact four-place representability check, finite/range checks,
  and differential Python/direct-SQL tests against GP1. Reject 1.00001; accept 1.00000.
- Incomplete rules may remain DRAFT. They cannot become a computational policy until GP2b
  validates endpoints and completeness. No release, resolver or fallback is introduced.
- Parent and child draft edits lock the revision parent first, verify expected versions
  and increment atomically. Raw SQL must not bypass these guards; maximum changes must
  not leave existing grade rows out of range. Concurrent stale edits produce conflicts.
  SourceEvidence payloads cannot be updated, including while unreferenced or in a draft.

Implementation must present the complete column/bound/CHECK/trigger inventory for review.
The table above is not a substitute for reviewing the actual migration and guard SQL.

## D-GP2A-2: schema and access boundary — PENDING owner approval

Recommended access:

| Principal | Proposed GP2a rights |
| --- | --- |
| Academic runtime and auth | No new table, function or row access. Existing student/account privileges unchanged. |
| PUBLIC and Supabase anon/authenticated/service_role | No catalogue access; no browser Data API path. |
| Existing configured migrator | DDL and privileged offline maintenance; explicit owner-only RLS policy supports synthetic fixtures on plain PostgreSQL. Never website credentials. |
| Publisher / monitor / extractor | No role, membership, credential, function or job created. |
| Existing backup login | Only the explicitly approved SELECT expansion in D-GP2A-3. |

Enable and FORCE RLS on all seven tables. Ordinary web logins remain denied even when
their student context is valid. Plain PostgreSQL's owner needs an explicit row policy;
Supabase's postgres migrator bypasses RLS and is not a restricted-role test principal.
Do not claim protection from the privileged operator who can alter schema or policies.

Preflight and existing boundary queries must detect unauthorized grants, object ownership,
memberships, missing FORCE RLS, default privileges and PostgreSQL 17 MAINTAIN. Integrate
metadata predicates without adding request-time round trips or reading catalogue rows.
If existing query budgets cannot be preserved, stop for a separate reviewed decision.
No SECURITY DEFINER publication function or released-data view is included.

## D-GP2A-3: reference backup option A — PENDING owner approval

Recommend the existing `ucc_backup` login and existing age-encrypted backup pipeline.
This adds SELECT on **all columns of exactly the seven named catalogue tables**. It is
an object-grant expansion requiring approval, even though it adds no new login or role
attribute. Existing BYPASSRLS stays confined to the already approved backup login;
do not give that attribute to another role or add broad default SELECT privileges.

Change `BACKUP_TABLES`, the explicit grant list in `supabase/backup/backup_role.sql`,
restore emptiness/version compatibility handling, tests and documentation together.
The seven tables are global reference data; do not add them to student-owned deletion
lists or invent Student FKs. Sessions, tokens and signing keys remain excluded.

Proposed recovery actor: the existing authorized migration/table-owner login, only on
an isolated schema-compatible empty target; never the website or backup login. Preserve
UUIDs, complete identity/source payloads, links, versions and any stored draft hashes in
valid FK order. Verify exact equality and RLS/grants after restoration before cutover.
No live restore or cutover is authorized by approval of this work order.

Two implementation hazards must be resolved and independently reviewed:

1. Child-insert/version triggers can change restored revision versions. Prove exact
   restoration on PostgreSQL 17; do not silently suppress validation, trust a web-settable
   GUC, use blanket trigger/RLS disabling, or substitute a new hash/version. If the current
   restore tool cannot satisfy this, present the narrowly privileged recovery design
   separately before claiming GP2a backup support or allowing persistent use.
2. Older archives lack the catalogue tables and may target an earlier schema. Establish
   schema compatibility explicitly; do not claim missing catalogue history was restored.
   Never fake/reverse a persistent migration to accommodate an archive. Any future student
   binding makes its exact policy history mandatory; no default policy may replace it.

Test actual backup-login reads and denied writes even after it turns off the read-only
session default. That default is an availability preference; SELECT-only grants are the
write boundary. Preserve existing encryption, bounded diagnostic privacy and student
backup behaviour; do not print source excerpts, secrets or student data in test evidence.

## Required acceptance and negative controls

| Area | Minimum repeatable evidence |
| --- | --- |
| Numeric/identity integrity | Direct SQL and Python agree on finite exact values, trailing zeroes, ranges, unknown scope, immutable university/programme identity, evidence immutability and FK reassignment. |
| Draft concurrency | Independent PostgreSQL connections contend on the parent; stale parent/child edits fail, versions increment atomically, errors roll back changes and endpoint/range guards cannot be bypassed. |
| Role isolation | Real separate LOGIN connections for runtime/auth/API/backup; raw SELECT/INSERT/UPDATE/DELETE and MAINTAIN attempts, missing owner policy, stray grants/ownership/memberships, disabled RLS and reused connections. No superuser SET ROLE substitute. |
| Migrations/SQL | Fresh and exact-master upgrade; reverse/reapply only on disposable synthetic data; regenerated numbered SQL matches; existing Supabase-image/pooler tests pass. No production SQL. |
| Encrypted recovery | Exact seven-table graph round trip through approved export login and privileged isolated restore actor, including version-trigger behaviour, denied writes/private-table reads, incomplete archives and failure atomicity. Existing student backup/deletion tests preserved. |
| Compatibility | Complete current root, foundation, authentication, isolation, website and all browser suites; no added catalogue reads or query-budget weakening. Preserve existing security and seven grading-policy mutation controls. |
| New negative controls | Deliberately break precision, an identity/evidence guard, child-version locking, FORCE RLS, a denial check and backup scope. Require an unmodified green control and specific assertion failures, not no-op/import errors. |

Report actual source SHAs, Python/Django/PostgreSQL/browser versions, counts, skips,
mutation outcomes, failures and exact-head hosted quality CI. Do not reuse historical
counts or infer PostgreSQL guarantees from pure Python tests. No network/AI/provider calls
or real student/institution data in tests. No catalogue tests have been implemented or run
as part of this documentation work.

## Delivery, rollback and later stages

Before code: independent design review and owner approval of D-GP2A-1/2/3. Then a fresh
implementation branch from a verified green master, small commits and one draft PR.
Stop for independent code review and a separate owner merge decision. No deployment.
If recovery/privilege design proves broader than this slice, stop for a reviewed split.

Before any later authorized rollout: rehearse migration/provisioning, inspect real migration
history, verify grants/RLS, keep catalogue access dormant and approve an operational
rollback plan. Unapplying populated catalogue migrations may destroy source/history; it
is not a generic rollback. Synthetic reverse tests do not authorize persistent reversal.

Next stages remain separate: GP2b canonical validation; GP3 manual evidence/publication;
GP4 student-selected, programme/cohort-bound immutable policy references; GP5+ official
source monitoring. Proposed monitoring may check periodically and perform an annual
full review, but can only create proposals. Humans approve releases; new releases never
silently reinterpret older student grades. Source availability, licences, retention,
reviewer accountability, providers/budget and scheduler credentials remain later decisions.

No phase certifies “all Nigerian universities and courses” until a source-backed coverage
inventory supports that claim. No school API, annual feed or grading-rule agreement exists
merely because it is planned. No annual automation is implemented by GP2a.

Owner approval record: D-GP2A-1, D-GP2A-2 and D-GP2A-3 are all PENDING. Publication authority,
real-source ingestion and monitoring remain unapproved, outside this work order.
