Milestone 2A implementation plan (before coding)

1. Keep all existing CLI, Streamlit, calculation code and 113 tests unchanged.
2. Add a Python 3.12 Django 5.2 LTS project under server/, with a UUID custom user, separate settings and no login/registration routes.
3. Configure PostgreSQL from environment variables; require an external secret key; default development hosts and database connections to loopback.
4. Add semester, course and assignment models with explicit deletion policies, shared credit/grade validation, normalized codes, record versions and database checks.
5. Add PostgreSQL composite foreign keys for owner consistency. Document precision coercion and the limits of model validation and tenant isolation.
6. Generate migrations; test fresh migrations and database constraints against actual PostgreSQL, plus the untouched legacy test suite. Extend CI and audit hashed dependencies.
7. Document local setup, schema, limits and verification. Commit and push only feature/database-foundation after verification; no deployment, merge or Milestone 2B.
