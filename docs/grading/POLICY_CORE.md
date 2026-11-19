# Grading-policy core: GP1

## Scope and implementation plan

The owner authorized the recommended staged approach toward coverage of Nigerian
universities and programmes. GP1 introduces an immutable, explicit policy input to
pure shared calculations, demonstrates it with synthetic scales, and preserves the
existing application's five-point behaviour. It does not establish verified coverage
of any university. National coverage requires source-backed, programme/cohort-aware
policies reviewed and published in later increments.

Base: `1c3ec68cb56011c855353d95da3a0f3006a5a3a9` (master, PR #105).
The source assessment was made at `3140aa3c8e692b911bc4e59065bf55c3f4972526`;
the intervening backup increment does not change the shared academic calculations.

The small implementation sequence is:

1. Validate and freeze a letter-grade policy; retain an explicit legacy default.
2. Pass the selected policy through every shared summary/prediction/planner path.
3. Prove default compatibility and synthetic four-point behaviour, including negative controls.
4. Include the new shared module in existing website packaging; no deployment.
5. Stop for independent review before subsequent catalogue/schema work.

## API and compatibility

`grading_policy.GradingPolicy(identifier, revision, grade_points, maximum)` copies
its rules into a read-only mapping. Its identifier and revision are bounded ASCII
references, not verification or publication claims. Grade labels are single uppercase
ASCII letters; points are exact built-in integers or finite Decimals, at most four
fractional places. The computational scale must be greater than zero and at most 100;
rules must include both zero and that maximum. These are GP1's supported input bounds,
not a statement that all institutional policies fit this representation. Floats,
booleans, invalid labels, incomplete endpoints and malformed references are rejected.

`LEGACY_POLICY` preserves A=5, B=4, C=3, D=2, E=1 and F=0. The historical public
`academic_logic.GRADE_POINTS` dictionary is derived from it and retains integer values
for existing CLI/forms. Calculation rules come from the immutable definition.

The following shared helpers accept keyword-only `policy=LEGACY_POLICY`:

- `checked_grade`, `checked_target` and `validate_courses`.
- `academic_summary`, `course_breakdown` and `predicted_summary`.
- `target_plan` and `projected_cgpa`.

An explicitly missing or unknown policy object is rejected, rather than substituted.
Each call uses exactly one policy for all its course inputs. The caller must establish
applicability; this API does not infer policy from a course code or free-text institution.
It must not be used to combine different policy revisions or convert four-point results
to five-point results. Course records have no policy binding yet, so mixed-policy
transcripts are unsupported rather than a supported or verified use case.

All existing callers omit the keyword and keep the legacy behaviour. No policy selector,
new form input, route or stored value is introduced. Existing grade/credit validation,
first-valid normalized-code deduplication, semester order, ungraded/F distinction,
Decimal arithmetic and formulas remain. Predictions and plans remain read-only.

`class_standing`, `checked_bands`, existing UI targets and database A–F CHECKs remain
legacy-only. Personal class bands are still an unverified guide. A four-point policy
must not be passed through those existing UI/storage paths. General classification,
score-to-grade intervals, rounding rules and institutional verification are deferred.

Vercel's allowlist and the server image's build context/COPY list include
`grading_policy.py`, since `academic_logic.py` now imports it. No hosting settings,
credentials, deployment commands, privileges or service configuration change.

## Verification

Reproduce the focused and complete Python suites from the repository root using the
project's Python 3.12 environment and hashed requirements:

```sh
python -m unittest tests.test_grading_policy tests.test_vercel_config -v
python -m unittest discover -v
python tools/check_repository_safety.py
git diff --check
```

Ten new tests cover immutable copies, exact point validation under low Decimal
precision, invalid policy references, explicit missing-policy rejection, legacy
compatibility, four-point summaries and breakdowns, prediction propagation, target
bounds, planner feasibility, projection, empty data, F/ungraded handling, duplicate
codes, semester order and unchanged input records.

The mutation test runs the calculation tests against temporary source copies. It first
requires an unmodified green control, then requires assertion failures (not import errors)
for three mutations: ignoring selected grade points, restoring the planner's hard-coded
five-point ceiling, and losing the policy when calculating predictions. It rejects no-op
mutations and never modifies the working checkout. All three were detected locally.

An additional local seeded comparison against the base's unmodified academic_logic.py
compared 500 synthetic workspaces across six paths (summary, breakdown, validation,
prediction, target and projection): 3,000 equal default results. The seed was 20261119;
records included duplicates, unknown grades, ungraded records and invalid credits.
This is supplementary evidence; committed tests and hosted CI are the repeatable gate.

Hosted quality CI runs the PostgreSQL 17 restricted-role suites, academic/security/
website regressions, browser suites, dependency audits, server-package smoke tests and
Supabase/pooler tests. See the draft PR's exact-head run for actual results; this document
does not claim a pending job passed. No database constraint or migration behaviour is
inferred from the pure Python tests. No real student data or external AI calls are used.

## Next gates and limitations

1. Independently review GP1 for compatibility. Do not merge automatically.
2. Design versioned catalogue/applicability records and restricted publication authority.
   Preserve auth/runtime separation, signed transaction context, forced RLS and generated
   Supabase SQL. New schema work requires its own reviewed increment.
3. Build manual source verification before student selection or policy activation.
   Pin policies to the correct programme, cohort/session and attempts. Distinguish
   verified, awaiting verification and unsupported coverage without silent substitution.
4. Address repeated-course modelling, mixed-policy handling, raw-score intervals,
   rounding, classification and historical corrections explicitly before supporting them.
5. Only then add isolated official-source retrieval, AI-assisted proposals and scheduling.
   AI must never publish rules or change student grades. Provider, budget, source-fetch,
   privacy and operational policies require separate review.

No catalogue, institutional policy, verified source, database schema, stored score,
AI monitoring, external service, authentication change or student-data migration is
part of GP1. Existing default results are not newly certified university results.

Rollback: revert GP1's code, tests, documentation and packaging additions together.
No database rollback, grant change, data conversion or policy migration is necessary.
