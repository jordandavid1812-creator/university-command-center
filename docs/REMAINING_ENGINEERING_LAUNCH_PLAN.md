# UNIVERSITY COMMAND CENTER
## Remaining Engineering and Launch Execution Plan

**Status:** Planning only

**Target:** Secure private synthetic-data staging, followed by a separately approved public launch

**Baseline:** Master includes merged PR #30

**Restriction:** No PR merges, purchases, deployments or new implementation authorized by this plan

### STAGE A — CLOSE EXISTING SECURITY WORK

1. Retain Codex's final independent approvals for PR #29 (`42910ed`) and PR #26 (`44c515f`).
2. When the owner authorizes merges, integrate PR #29 first.
3. Reassess PR #26's compatibility with the updated master and merge separately only after authorization.
4. Preserve dormant trusted-device behavior.
5. Run the complete historical and security suites on the combined PostgreSQL 17 release.
6. Review the documentation PRs #27, #28 and #32–34 separately.
7. Close the redundant PR #31 only when authorized.
8. Record the accepted release SHA, security findings, CI results and remaining risks.

**Completion gate:** A reproducible, fully tested security baseline with no unauthorized feature activation.

### STAGE B — COMPLETE ACCOUNT SECURITY

9. Design and implement S0-02B account-aware throttling and trusted-device caller integration.
10. Address shared-campus-network fairness, account-lockout abuse and rate-limit saturation.
11. Verify device issuance, rotation, revocation and lost-response handling.
12. Design and implement S0-02C recovery and independent access restoration.
13. Verify password-reset concurrency, session invalidation, account verification and cookie behavior.
14. Define and test safe database lock, request, session-save and transaction failure handling.
15. Obtain independent review of S0-02B/C before activating restrictions.

**Completion gate:** No hard account restriction is enabled without a reliable and independently tested recovery path.

### STAGE C — BUILD LOCAL STAGING

16. Establish a reproducible PostgreSQL 17 and Django staging harness.
17. Configure restricted runtime/authentication roles and offline migration credentials.
18. Add production-style settings with DEBUG disabled and strict host/CSRF configuration.
19. Package the application with an approved WSGI server and static-file handling.
20. Simulate HTTPS, TLS certificate validation, reverse proxy and private networking.
21. Test forced RLS, signed context, grants, session isolation and role drift.
22. Rehearse migrations, interrupted releases and rollback.

**Completion gate:** Clean local installation, predictable startup, security-boundary verification and repeatable teardown.

### STAGE D — MAKE THE SYSTEM OPERABLE

23. Implement encrypted backups with restricted offline credentials.
24. Restore into a fresh PostgreSQL 17 environment and verify all academic and security records.
25. Establish key custody, credential rotation and restored-session invalidation procedures.
26. Design email sending with safe timeout, retry, logging and outage behavior.
27. Test authentication messages locally with a controlled SMTP sink.
28. Implement sanitized application logs, monitoring and health checks.
29. Test alerts, database failures, unavailable email and recovery procedures.
30. Document release, rollback, backup and incident runbooks.

**Completion gate:** Demonstrated recoverability without weakened security controls.

### STAGE E — VERIFY THE PRODUCT

31. Test account creation and login.
32. Test semester, course and assignment workflows.
33. Reconcile GPA/CGPA and academic calculations against documented grading rules.
34. Test predictions, planning, editing, deletion and conflicting updates.
35. Verify isolation between independent student accounts.
36. Test desktop and mobile browsers, keyboard navigation and real screen readers.
37. Run approved bounded performance tests at 1, 5 and 10 concurrent synthetic users.
38. Fix blocking functional, usability and accessibility defects.

**Completion gate:** Core student journeys complete successfully without critical academic, accessibility or security failures.

### STAGE F — QUALIFY REAL INFRASTRUCTURE

39. Select a candidate hosting architecture and obtain an itemized quote.
40. Qualify PostgreSQL 17, non-owner roles, RLS, pgcrypto, TLS and backup/restore access on that provider.
41. Approve region, budget, private access and named operator responsibilities.
42. Configure private ingress, DNS, HTTPS and operational secrets.
43. Validate real email delivery, recipient controls, outages and recovery.
44. Deploy only after explicit owner authorization.
45. Re-run the full release checklist in the provider environment.

**Completion gate:** Approved private synthetic-data staging passes the evidence gates.

### STAGE G — PILOT AND LAUNCH READINESS

46. Invite a small approved group of private reviewers.
47. Record usability, performance, security and operational findings.
48. Revoke test access and address blocking defects.
49. Arrange a qualified independent penetration test under written scope.
50. Retest all Critical and High findings.
51. Finalize privacy, data retention, incident response, university-specific policy and support obligations.
52. Prepare release notes, operational contacts, launch monitoring and rollback plan.
53. Conduct final GO/NO-GO review.
54. Seek separate authorization for any public pilot or production launch.

**Completion gate:** Explicit documented acceptance of security, reliability, privacy and support responsibilities.

### NON-NEGOTIABLE RESTRICTIONS

- No real student records in local or private synthetic staging.
- No disabling RLS or relaxing database privileges to pass tests.
- No enabling dormant account/device restrictions without separate approval and verified recovery.
- No deployment credentials committed to GitHub.
- No cloud purchases without an approved spending limit.
- No treating green CI as proof of production readiness.
- No production launch without its own final authorization.

### NEXT ASSIGNMENT

Begin with Stage A's security-integration readiness and Stage C's local architecture preparation. Stage B's detailed design can proceed separately, but implementation and activation require explicit scope approval. No other work is implicitly authorized.