import json
import shutil
from pathlib import Path


damaged_files = set()


def save_data(filename, data):
    path = Path(filename).resolve()
    try:
        if path in damaged_files:
            backup = Path(f"{path}.bak")
            number = 1
            while backup.exists():
                backup = Path(f"{path}.bak.{number}")
                number += 1
            shutil.copyfile(path, backup)
            print(f"Saved a backup of the damaged file to {backup}.")
        with open(filename, "w") as file:
            json.dump(data, file, indent=4)
        damaged_files.discard(path)
    except OSError:
        print(f"Could not save {filename}. Please check the file and its permissions.")


def load_data(filename):
    try:
        with open(filename, "r") as file:
            return json.load(file)

    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, UnicodeError, OSError) as error:
        if isinstance(error, (json.JSONDecodeError, UnicodeError)):
            damaged_files.add(Path(filename).resolve())
        print(f"Could not read {filename}. The file may be damaged or unreadable.")
        return []
