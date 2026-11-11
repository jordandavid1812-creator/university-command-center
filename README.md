# University Command Center

A Python app for managing university life, with a terminal interface and a local Streamlit web interface.

- Add, edit, remove, and list courses grouped by semester.
- Track assignments and mark them as complete.
- Save course grades and calculate credit-weighted semester and cumulative GPAs on a 5-point scale.
- Try hypothetical grades with the GPA Predictor without changing saved grades.

Your courses and assignments are saved in JSON files. The CLI uses only Python's standard library. The optional web interface requires Streamlit.

## Local web application

Python **3.12** is the supported and CI-tested version for this milestone. The CLI uses only its standard library. From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==26.3
python -m pip install --require-hashes -r requirements-lock.txt
python -m streamlit run web_app.py --server.address 127.0.0.1
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. Open the local address printed by Streamlit in your browser, usually `http://127.0.0.1:8501`. Stop the app with Ctrl+C.

CI and the fresh-install checks run on Linux. Native Windows and macOS are not part of this milestone's verified platform matrix.

The sidebar has six pages:

- **Dashboard:** actual CGPA, graded and ungraded course counts, pending assignments, and a semester chart.
- **Courses:** add courses, edit names/semesters/credits/actual grades, or confirm removal. Grades can remain unassigned. Course codes stay fixed when editing to preserve assignment links. Remove linked assignments before deleting their course.
- **Assignments:** add a title, course, and due date; mark work complete or pending; confirm removal.
- **Academic performance:** actual semester and cumulative GPAs with graded/ungraded counts and a chart.
- **GPA Predictor:** choose hypothetical grades, calculate, change selections, and calculate again. Nothing is saved.
- **Target CGPA Planner:** enter a target and remaining credits to see the required average. Nothing is saved.

The web app uses existing `courses.json` and `assignments.json` beside `web_app.py`; no migration is needed. Missing files are created only after an explicit save. For a separate workspace, set `UCC_DATA_DIR` to an existing private directory before launching (for example, `UCC_DATA_DIR=/path/to/private/folder python -m streamlit run web_app.py`). The CLI still uses its current working directory, so run it from the project folder to share the same records.

### Protecting your records

This MVP is for **one local user**. Keep the server bound to `127.0.0.1`. Do not publish it, expose it to your network, or deploy it as a shared public app. There is no login or user isolation. No authentication or cloud storage has been added.

Close the CLI before editing in the web app. Do not run multiple writers or edit files externally while a save is in progress. The web app detects changes since a form was opened and asks you to reload rather than overwrite them; this is not a multi-user transaction system. Use **Reload data** after intentional external changes.

Reading or calculating never writes records. Forms save only when submitted. A damaged, unreadable, or wrong-shaped JSON file blocks editing rather than becoming an empty default. Restore or repair it yourself and reload. Before each overwrite, the web app preserves an exact local backup (`.bak`, `.bak.1`, etc.) and writes the replacement atomically. If a backup or save fails, it reports the error and keeps the original. Extra record fields are preserved when editing. Invalid individual records are reported or left untouched; calculations skip them.

Student files and generated backups are ignored by Git. Backups contain personal data too: keep them private and manage their retention yourself. Existing data in old Git history is not removed by ignore rules. Never commit real student records or screenshots of them.

See [architecture notes](docs/ARCHITECTURE.md) for the separation between calculations, forms, and storage.

## Run the app

Open a terminal in the project folder and run:

```bash
python main.py
```

Follow the numbered menu. In the GPA calculator, press Enter to keep a saved grade or Q to cancel. Choose option 10 to exit the app.

Choose option 11 for the GPA Predictor. Enter a hypothetical grade for each course to see the predicted GPA, total credit units, and predicted grade points. Enter R to change grades and recalculate, then press Enter to keep a previous prediction or type a replacement grade. Q returns to the menu. Predictions are not saved.

## Academic Performance Overview

Choose option 12 to see each semester's GPA, a cumulative GPA, and a simple text bar comparison using actual saved grades. It never asks for grades or changes your data, and GPA Predictor grades are excluded.

GPA is total grade points (grade value times credit units) divided by graded credit units, using the existing 5-point scale. Completed courses means courses with valid saved grades, including F; it does not mean courses passed. Attempted credit units include only these graded courses. Courses without grades are listed separately and excluded from GPA. A semester with no grades shows N/A, not zero.

Older courses without semesters appear under Unassigned. Missing or invalid records are skipped with messages. Course codes are unique across the app; the first valid record per code is used, and duplicates are skipped, even across semesters. Semester names are free text, so the overview keeps their order in the records rather than guessing chronological order.

## Target CGPA Planner

Choose option 13 to enter a target CGPA from 0.00 to 5.00 and a positive number of remaining credit units. Q cancels either prompt. The planner shows your current CGPA, current quality points, and the average grade point needed to finish at or above the target.

Required average = ((target CGPA × (completed attempted credits + remaining credits)) − current quality points) / remaining credits.

Only valid actual saved grades count toward current points and attempted credits, including F grades. Ungraded courses and predictor grades do not count. Validation and duplicate handling match the overview: the first valid record per normalized course code is retained, even if it has no grade. With no graded courses, current CGPA is N/A and the calculation starts with zero credits and points.

Enter all remaining credits yourself, including ungraded courses. The planner assumes current grades stay fixed and all remaining credits are completed on the 0–5 scale. An average above 5 means the target is impossible under these assumptions; an average at or below zero means at least the target is guaranteed even with zero points on all remaining credits. Other results indicate the needed credit-weighted average; individual course weights and letter-grade choices may prevent an exact match.

This is a mathematical estimate, not a check of university graduation requirements. It does not apply repeated-course replacement rules or infer excluded credits. Review which courses are included and supply the appropriate remaining credits yourself. Nothing is saved or changed.

## Run the tests

From the project folder, run:

```bash
python -m unittest discover -v
```

Run this command inside the environment where requirements were installed to include the Streamlit interaction tests. Without Streamlit, the CLI and pure-logic tests still run, but web interaction tests are explicitly skipped. All tests use synthetic data and temporary directories. Tests cover calculations, backups, failed and stale saves, course/assignment forms, read-only pages, and corrupted-file handling.

## Production foundation — Milestone 1

The project is still a local, single-user application. No Django, PostgreSQL, authentication, or deployment is included in this milestone. See [foundation review](docs/FOUNDATION_REVIEW.md) for the data-history audit and remaining risks.

### Supported calculation inputs

- The grading scale stays A=5, B=4, C=3, D=2, E=1, F=0. Lowercase letters are normalized. Missing, null, or blank actual grades stay ungraded; booleans and numeric grade values are invalid.
- Calculation credit values and remaining credits must be finite numbers from **0.0001 to 1,000,000**, with at most **four decimal places**. These are technical safety limits, not university graduation rules. Saved course credits must be JSON numbers rather than strings. Unsupported records are reported and left unchanged, not rounded or rewritten.
- Target CGPA must be **0–5**, with at most **four decimal places**. CLI planning parses Decimal values directly, without float conversion. Unsupported tiny remaining credits such as `1e-30` are rejected rather than producing a false guarantee.
- Calculations use an isolated Decimal context and an algebraically equivalent planner formula to avoid subtracting nearly equal graduation totals. Displayed values are rounded; achievable/impossible decisions use unrounded values.
- Course creation/editing keeps its existing whole-number **1–6** credit rule. Valid older fractional-credit records remain usable in calculations. The legacy CLI calculator still displays its existing zero-credit warning, but zero credits are not accepted by planning or prediction.
- Predictions use their own grades and never save or overwrite actual grades. An invalid actual grade does not prevent a hypothetical prediction for an otherwise valid course.
- A normal pending assignment must have a nonempty title, an existing course code, a real `YYYY-MM-DD` date, and a Boolean completion flag. Incomplete, orphaned, or malformed records are excluded from dashboard pending counts and upcoming work, with a needs-attention message. The original records are left untouched.

### Automated quality and dependency checks

GitHub Actions runs the full suite and a dependency audit on pull requests, pushes to `master`, and weekly. It installs web requirements so Streamlit tests are included. Workflows use read-only repository permissions and pinned action commits. Configure branch protection to require the `tests` and `dependency-audit` checks before merging; adding a workflow does not itself enable branch protection.

`requirements.txt` lists the direct web dependency. `requirements-lock.txt` fixes all runtime dependency versions and package hashes. Install from the lock file for reproducibility. Streamlit was updated to a patched release after the dependency audit identified advisories affecting the earlier installation. The audit fails on known findings; no vulnerabilities are silently ignored.

To run the same checks locally after installing the runtime lock file:

```bash
python -m pip install -r requirements-dev.txt
python -m pip check
python tools/check_repository_safety.py
python -m unittest discover -v
python -m pip_audit --strict --require-hashes --disable-pip --progress-spinner off -r requirements-lock.txt
```

`pip-audit` needs access to PyPI and vulnerability metadata. Network or audit-service failures are failures, not evidence that dependencies are safe. A clean scan only means no known advisories were reported at scan time.

To deliberately refresh the runtime lock on Python 3.12 after changing the direct requirement:

```bash
python -m piptools compile --generate-hashes --strip-extras --no-header --no-emit-index-url --index-url https://pypi.org/simple -o requirements-lock.txt requirements.txt
```

Run all tests and the audit after updating it. Dependabot proposes dependency and action updates weekly; review and regenerate the lock as needed. It does not merge updates automatically.

Student JSON files, backups, temporary files, local secrets, and common virtual environment folders are ignored by Git. CI also rejects tracked private/local paths, including files added with `git add -f`. Ignore rules do not erase old history or prevent someone from overriding a failing check.

## Django/PostgreSQL foundation (Milestone 2A)

The separate `server/` project adds database models without replacing the CLI or
Streamlit. It has no login/registration routes and is not approved for public
hosting. See [local setup, schema, testing and security limits](docs/DATABASE_FOUNDATION.md)
and the [implementation plan](docs/MILESTONE_2A_PLAN.md). Owner isolation must still
be verified in Milestone 2B.

Milestone 2B adds [database security and student isolation](docs/DATABASE_SECURITY.md):
owner-scoped services, restricted PostgreSQL roles, forced RLS and optimistic
concurrency. These controls are tested database foundations; public authentication,
registration and deployment remain outside scope.

## Student authentication (Milestone 3)

Local Django registration, email verification, login/logout and password recovery
now use a separate restricted authentication connection. Academic access remains
on the original restricted role with forced RLS. Start with the
[authentication setup and security boundary](docs/AUTHENTICATION.md), then open
`http://127.0.0.1:8000/accounts/register/`. Use only synthetic data and local
console/in-memory email. Public deployment and the full dashboard remain deferred.

## Student website (Milestone 4A)

The Django website now includes the dashboard, semester/course/assignment management,
weighted GPA/CGPA, read-only prediction, target planning and account settings.
See [student website setup, pages and limits](docs/STUDENT_WEBSITE.md). Run locally
with `python server/manage.py runserver 127.0.0.1:8000 --settings=config.settings.web_development`
after the separate role/schema setup, then open `http://127.0.0.1:8000/`.
No personal JSON import, public deployment or replacement of CLI/Streamlit is included.

Milestone 4B refines the student dashboard, search, form feedback and mobile/keyboard
experience. See [the quality review](docs/MILESTONE_4B_REVIEW.md) and
[website guide](docs/STUDENT_WEBSITE.md) for verification and local startup.
