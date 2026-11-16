"""Fail CI if local data, backups, secrets, or environments become tracked."""
from pathlib import Path, PurePosixPath
import re
import subprocess

# API key shapes (AI study assistant): a Google API key is "AIza" plus exactly 35 key
# characters; an xAI key is "xai-" plus at least 40. Ordinary prose never matches.
KEY_SHAPES = (
    re.compile(rb"(?<![0-9A-Za-z_\-])AIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])"),
    re.compile(rb"(?<![0-9A-Za-z_\-])xai-[0-9A-Za-z]{40,}"),
)
MAX_SCANNED_BYTES = 5 * 1024 * 1024


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


def contains_api_key(content):
    """True if the bytes contain something shaped like a Google or xAI API key."""
    return any(shape.search(content) for shape in KEY_SHAPES)


def tracked_files_with_keys(paths):
    """How many tracked files contain a key-shaped string. Never returns the match or path."""
    count = 0
    for path in paths:
        file = Path(path)
        if file.is_file() and file.stat().st_size <= MAX_SCANNED_BYTES and contains_api_key(file.read_bytes()):
            count += 1
    return count


def main():
    paths = [path for path in subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0") if path]
    count = sum(private_path(path) for path in paths)
    if count:
        print(f"Repository safety check failed: {count} private/local paths are tracked.")
        print("Inspect tracked paths locally; do not copy their contents into CI logs.")
        return 1
    keys = tracked_files_with_keys(paths)
    if keys:
        print(f"Repository safety check failed: {keys} tracked files contain an API-key-shaped string.")
        print("Remove the key, revoke it with the provider, and never paste keys into the repository.")
        return 1
    print("Repository safety check passed: no private/local paths or API keys are tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
