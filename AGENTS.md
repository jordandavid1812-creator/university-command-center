University Command Center is a Python app for managing university life. It tracks courses, assignments and GPA.

Files:
main.py runs the app.
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
Do not add new libraries without asking.
Make small changes, one at a time.
Keep the academic overview read-only. Never save data or use predictor grades there.
Use the shared GRADE_POINTS scale in gpa.py and weight GPA by credit units.
Ungraded courses are not F grades. Count attempted units only for valid graded courses.
Preserve semester record order; free-text names do not establish chronological order.
Course codes are unique across the app. In the overview, use the first valid record per code and skip duplicates.
The target CGPA planner shares the overview's validation and deduplication helper.
Keep planning read-only and exclude hypothetical grades. Students supply remaining credits.
Do not infer graduation, repeated-course, or excluded-credit policies.
