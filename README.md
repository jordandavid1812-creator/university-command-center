# University Command Center

A simple Python command-line app for managing university life.

- Add, edit, remove, and list courses grouped by semester.
- Track assignments and mark them as complete.
- Save course grades and calculate credit-weighted semester and cumulative GPAs on a 5-point scale.
- Try hypothetical grades with the GPA Predictor without changing saved grades.

Your courses and assignments are saved in JSON files. The app uses Python 3 and needs no extra libraries.

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
