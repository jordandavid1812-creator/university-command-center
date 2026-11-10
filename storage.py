import json


def save_data(filename, data):
    try:
        with open(filename, "w") as file:
            json.dump(data, file, indent=4)
    except OSError:
        print(f"Could not save {filename}. Please check the file and its permissions.")


def load_data(filename):
    try:
        with open(filename, "r") as file:
            return json.load(file)

    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, UnicodeError, OSError):
        print(f"Could not read {filename}. The file may be damaged or unreadable.")
        return []
