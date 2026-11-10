# University Command Center

A Python app for managing university life, with a terminal interface and a local Streamlit web interface.

- Add, edit, remove, and list courses grouped by semester.
- Track assignments and mark them as complete.
- Save course grades and calculate credit-weighted semester and cumulative GPAs on a 5-point scale.
- Try hypothetical grades with the GPA Predictor without changing saved grades.

Your courses and assignments are saved in JSON files. The CLI uses only Python's standard library. The optional web interface requires Streamlit.

## Local web application

Use Python 3.11 or newer (tested with Python 3.12). From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run web_app.py --server.address 127.0.0.1
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. Open the local address printed by Streamlit in your browser, usually `http://127.0.0.1:8501`. Stop the app with Ctrl+C.

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
