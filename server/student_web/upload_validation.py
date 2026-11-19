"""Study file upload checks: name, extension, size and real content (PDF signature, UTF-8 text)."""

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # The largest any deployment allows (database limit).
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
PDF_SIGNATURE = b"%PDF-"


def describe_size(limit):
    """A size for people: 10485760 -> '10 MiB', 4000000 -> '4 MB'."""
    if limit % (1024 * 1024) == 0:
        return f"{limit // (1024 * 1024)} MiB"
    return f"{limit / 1_000_000:g} MB"


def validate_upload_metadata(filename, size, limit=MAX_UPLOAD_BYTES):
    """Return the allowed extension or raise a friendly error. `limit` is the deployment's
    per-file cap (settings.UCC_MAX_UPLOAD_BYTES), never more than MAX_UPLOAD_BYTES."""
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Choose a file with a name.")

    if (
        len(filename) > 255
        or any(character in filename for character in ("/", "\\"))
        or any(ord(character) < 32 for character in filename)
    ):
        raise ValueError("Use a simple filename without folders or control characters.")

    if "." not in filename or not filename.rsplit(".", 1)[0].strip():
        raise ValueError("Choose a PDF or TXT file.")

    extension = "." + filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Choose a PDF or TXT file.")

    if type(size) is not int or size <= 0:
        raise ValueError("Choose a file that is not empty.")

    if size > min(limit, MAX_UPLOAD_BYTES):
        raise ValueError(f"Choose a file no larger than {describe_size(min(limit, MAX_UPLOAD_BYTES))}.")

    return extension


def validate_text_content(content):
    """Validate bounded UTF-8 text bytes and return the decoded text."""
    if not isinstance(content, bytes):
        raise ValueError("Text content must be supplied as bytes.")

    validate_upload_metadata("material.txt", len(content))

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Choose a TXT file saved with UTF-8 encoding.") from None

    if not text.strip():
        raise ValueError("Choose a text file containing readable text.")

    if any(
        (ord(character) < 32 and character not in "\t\n\r\f")
        or 127 <= ord(character) <= 159
        for character in text
    ):
        raise ValueError("The text file contains unsupported control characters.")

    return text


def validate_pdf_content(content):
    """Check bounded bytes start like a PDF. This does not prove the PDF is safe."""
    if not isinstance(content, bytes):
        raise ValueError("PDF content must be supplied as bytes.")

    validate_upload_metadata("material.pdf", len(content))

    if not content.startswith(PDF_SIGNATURE):
        raise ValueError("Choose a real PDF file.")

    return content
