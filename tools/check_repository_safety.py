"""Fail CI if local data, backups, secrets, or environments become tracked."""
from pathlib import PurePosixPath
import subprocess


def private_path(filename):
    path = PurePosixPath(filename)
    name = path.name
    if any(part in {".venv", "venv", "env", ".env", ".tox", ".nox", "__pypackages__", "__pycache__"}
           or part.startswith((".venv-", "venv-")) for part in path.parts):
        return True
    return (name in {"courses.json", "assignments.json", "secrets.toml", "pyvenv.cfg"}
            or (name.startswith(".env") and name != ".env.example")
            or name.endswith((".bak", ".tmp", ".pyc")) or ".bak." in name
            or name.startswith(".ucc-"))


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    count = sum(private_path(path) for path in paths if path)
    if count:
        print(f"Repository safety check failed: {count} private/local paths are tracked.")
        print("Inspect tracked paths locally; do not copy their contents into CI logs.")
        return 1
    print("Repository safety check passed: no private/local paths are tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
