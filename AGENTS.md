University Command Center is a Python app for managing university life. It tracks courses, assignments and GPA.

Files:
main.py runs the app.
web_app.py runs the local Streamlit interface.
academic_logic.py contains pure shared grading, validation, summaries, and planning calculations.
web_actions.py validates form edits and returns new records without writing files.
web_data.py safely loads and saves web records, with snapshots, backups, and atomic replacement.
courses.py handles courses.
assignments.py handles assignments.
gpa.py calculates GPA.
gpa_predictor.py tries temporary hypothetical grades.
academic_overview.py displays a read-only summary of actual saved grades.
target_cgpa.py estimates the average needed across remaining credits for a target CGPA.
storage.py saves and loads data in JSON files.

Goal: finish the GPA calculator so it works fully.

Rules:
Keep the code simple. I am a beginner.
Explain every change in plain words.
The web MVP uses Streamlit from requirements.txt. Do not add other application libraries without asking.
Make small changes, one at a time.
Keep the academic overview read-only. Never save data or use predictor grades there.
Use the shared GRADE_POINTS scale in gpa.py and weight GPA by credit units.
Ungraded courses are not F grades. Count attempted units only for valid graded courses.
Preserve semester record order; free-text names do not establish chronological order.
Course codes are unique across the app. In the overview, use the first valid record per code and skip duplicates.
The target CGPA planner shares the overview's validation and deduplication helper.
Keep planning read-only and exclude hypothetical grades. Students supply remaining credits.
Do not infer graduation, repeated-course, or excluded-credit policies.
Keep calculation helpers free of print, input, Streamlit calls, and filesystem writes.
Keep the CLI working without Streamlit installed. Run the full unittest suite with web requirements installed before finishing web changes.
The web app is local and single-user only. Do not deploy it publicly with shared JSON data.
Never use empty fallback data after a web load error. Preserve original files, extra fields, and backups; reject stale saves.
Use synthetic data and temporary directories for tests and screenshots. Do not commit student data or backups.
