# Production foundation — Milestone 1 review

Review date: 10 November 2026. This milestone stabilizes the local CLI and Streamlit app. It does not introduce Django, PostgreSQL, accounts, or deployment.

## Correctness and compatibility

The documented tiny-credit planner issue was reproduced before the fix: a target of 5 with an existing A/3-credit course and `1e-30` remaining credits could incorrectly produce a guaranteed result. Such inputs are now outside the documented credit contract and are rejected. The minimum supported credit value, 0.0001, correctly requires an average of 5 in the same scenario. The formula is rearranged to reduce cancellation, uses a controlled Decimal context, and does not convert CLI inputs through float first.

Credit values support four decimal places from 0.0001 to 1000000; targets support four decimal places from 0 to 5. These are technical limits, not a curriculum or graduation policy. Unsupported saved records are warned about and preserved. Normal old records without grades or semesters still work. The old CLI zero-credit warning remains supported.

Shared validators preserve the 5-point scale, distinguish ungraded from F, and keep predictions separate. The CLI predictor reuses pure validation and prediction calculations, including duplicate-code handling. Actual invalid grades can be corrected through normal grade entry; they are never imported as hypothetical grades.

Assignment validation excludes missing fields, invalid dates, non-Boolean completion flags, and unknown course links from normal pending counts. Needs-attention records remain on disk. The Streamlit assignment page explains the problem and does not offer normal completion controls for invalid records. Explicit confirmed removal remains available for dictionary-shaped records; nothing is removed automatically.

## Historical data audit

The audit inspected academic JSON blobs reachable through the available local Git refs, without copying their contents to terminal logs or this report.

- No current tracked courses.json or assignments.json files were found.
- Two historical JSON blobs contain three academic records.
- No direct identifier or credential indicators were detected in those academic records. This limited inspection is not a proof that all repository history is free of sensitive information.
- Real-versus-demo provenance cannot be established. Treat the historical academic contents as potentially sensitive until the owner confirms their origin.
- Commit fe511c9ff1bb contains the earlier tracked data; d51ed5f035ed records its removal from tracking. Removing current files or adding ignore rules does not remove old blobs.
- No history was rewritten, records deleted, or source data copied into this report. Unreachable/deleted objects on GitHub, forks, external clones, and GitHub-retained artifacts were not audited.

Before broader repository distribution, review this history privately. Any history cleanup would require a separate authorized task and coordination with existing clones/forks. Credential rotation would be required if a separate audit finds exposed credentials; none are claimed here.

## JSON safety review

Web storage still refuses damaged/wrong-shaped JSON, rejects ordinary stale snapshots, backs up previous bytes, and writes atomically. It is not safe for simultaneous writers: snapshot comparison and replacement are not one transaction. Keep one local writer at a time and close the CLI before web editing.

Legacy CLI storage remains a local compatibility adapter and is weaker than the web adapter. Backups are local plaintext and have no automatic retention or offsite recovery. These limitations remain explicit; replacing storage belongs to a later reviewed milestone.

Ignore rules now cover student data, backups, temporary saves, secrets, and common virtual environment directories. A read-only CI safety check also detects tracked private/local paths. No ignore or CI rule can remove data already present in history.

## Quality controls

The GitHub workflow runs the full suite with web dependencies installed, pip check, a tracked-file safety check, and pip-audit against the hashed runtime lock. It runs on pull requests, master pushes, a weekly schedule, and manual dispatch. GitHub Actions are pinned by commit, repository permissions are read-only, and checkout credentials are not persisted. Configure required branch checks separately; no repository protection settings were changed here.

The initial environment audit reported advisories affecting Streamlit, Pillow, PyArrow, and the environment's older pip. Advisory aliases may overlap; raw entry counts are not distinct vulnerability counts. The runtime requirement is updated to Streamlit 1.67.0, with Pillow 13.0.0 and PyArrow 26.0.1 in the tested lock. Install tooling uses pip 26.3.

Local verification on Python 3.12: all 113 tests passed, including all 91 original tests unchanged and 22 new regression checks. A fresh environment installed the hashed runtime lock successfully; pip check passed. All 34 locked runtime packages were included in the final pip-audit scan, which reported no known vulnerabilities on the review date. The audit reads the complete lock directly (--disable-pip); artifact hashes are separately verified by installation in the test job. CLI integration and Streamlit interaction tests use synthetic data only. Personal JSON files matched their pre-task checksums.

A live Streamlit 1.67.0 smoke test also passed: the health endpoint returned ok, Chromium loaded all six pages without JavaScript errors, the dashboard flagged a malformed assignment, and the planner correctly handled 0.0001 remaining credits. A 390-pixel mobile view had no horizontal page overflow. The server used temporary synthetic records and was stopped after verification.

These local results do not establish GitHub-hosted CI status. Confirm the hosted tests and dependency-audit checks on the pull request before merging. No branch protection or deployment settings were changed.

requirements-lock.txt fixes runtime versions and hashes for the supported Python 3.12 environment. requirements-dev.txt contains only quality tools. Future vulnerability findings fail CI; there are no advisory suppressions. No scan establishes that unknown vulnerabilities do not exist.

## Remaining boundaries

The app still has no authentication, account isolation, or multi-user transactional storage. Public hosting is not approved. Keep binding to 127.0.0.1. No feature has been intentionally removed. Milestone 2 must wait for review of this branch.
