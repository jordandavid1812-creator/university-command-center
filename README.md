# University Command Center

A simple Python command-line app for managing university life.

- Add, edit, remove, and list courses grouped by semester.
- Track assignments and mark them as complete.
- Save course grades and calculate credit-weighted semester and cumulative GPAs on a 5-point scale.

Your courses and assignments are saved in JSON files. The app uses Python 3 and needs no extra libraries.

## Run the app

Open a terminal in the project folder and run:

```bash
python main.py
```

Follow the numbered menu. In the GPA calculator, press Enter to keep a saved grade or Q to cancel. Choose option 10 to exit the app.

## Run the tests

From the project folder, run:

```bash
python -m unittest discover -v
```
