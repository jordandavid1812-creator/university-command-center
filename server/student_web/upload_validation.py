"""Basic upload metadata checks; these do not verify file contents."""

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def validate_upload_metadata(filename, size):
    """Return the allowed extension or raise a friendly error."""
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Choose a file with a name.")

    if (
        len(filename) > 255
        or any(character in filename for character in ("/", "\\"))
        or any(ord(character) < 32 for character in filename)
    ):
        raise ValueError("Use a simple filename without folders or control characters.")

    extension = "." + filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Choose a PDF or TXT file.")

    if type(size) is not int or size <= 0:
        raise ValueError("Choose a file that is not empty.")

    if size > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a file no larger than 10 MiB.")

    return extension
