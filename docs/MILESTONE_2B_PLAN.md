# Milestone 2B plan

1. Preserve all application code, formulas, 113 legacy tests and 33 foundation tests.
2. Add explicit trusted-principal capabilities and owner-scoped CRUD services.
   Reject owner fields, unknown fields, missing context and forged identifiers.
3. Add a semester version field and PostgreSQL RLS migrations. Force RLS on all
   three academic tables, use signed transaction/backend-bound owner context,
   and keep signing keys inaccessible to the restricted runtime role.
4. Separate DBA role creation, migrator-owned schema provisioning and runtime
   DML privileges. No runtime DDL, role membership, account-table access or RLS bypass.
5. Use atomic service units and compare-and-swap record versions; protect deletes,
   rollback partial work and maintain timestamps.
6. Test on real PostgreSQL with separate login connections and non-superuser
   migration/runtime roles, including direct SQL forgery/replay and concurrent edits.
7. Extend CI, document security boundaries, run all tests/audits, push the feature
   branch and open a review PR targeting master. No public auth, deploy or merge.
