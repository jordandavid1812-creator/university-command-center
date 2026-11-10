"""Local JSON storage for web forms. Never recover from errors with empty data."""
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class DataError(Exception):
    pass


@dataclass
class Snapshot:
    records: list
    original: bytes | None


def read_records(path):
    path = Path(path)
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return Snapshot([], None)
    except OSError as error:
        raise DataError(f"Cannot read {path.name}. Check permissions; no data was changed.") from error
    try:
        records = json.loads(original)
        if not isinstance(records, list):
            raise ValueError("Expected a list")
    except (ValueError, UnicodeError) as error:
        raise DataError(f"{path.name} is damaged or is not a list. Restore it before editing; no data was changed.") from error
    return Snapshot(records, original)


def write_records(path, records, snapshot):
    path = Path(path)
    if not isinstance(records, list):
        raise DataError("Data must be a list. Nothing was saved.")
    temporary = None
    try:
        # A file changed since this form opened must be reloaded, not overwritten.
        current = read_records(path)
        if current.original != snapshot.original:
            raise DataError("Data changed since this form opened. Reload the page before editing again.")
        payload = json.dumps(records, indent=4, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if current.original is not None:
            backup = Path(f"{path}.bak")
            number = 1
            while backup.exists():
                backup = Path(f"{path}.bak.{number}")
                number += 1
            with backup.open("xb") as file:
                os.chmod(backup, 0o600)
                file.write(current.original)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".ucc-", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError) as error:
        raise DataError(f"Could not save {path.name}. The original file was preserved.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
