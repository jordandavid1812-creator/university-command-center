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

## Run the tests

From the project folder, run:

```bash
python -m unittest discover -v
```
