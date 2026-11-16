"""One-time consent tokens for the AI study assistant (stage 3b).

The confirm page issues a token; only a Send POST that carries it can call a provider.
The token is signed with Django's signing (SECRET_KEY, its own salt) and binds the signed-in
student, the material, the tool, the question and the number of characters shown. It expires
after 10 minutes. The ledger stores only its SHA-256 hash, so a repeated Send finds the request
already made with it and never sends twice.
"""
import hashlib
import secrets
from django.core import signing

SALT = "student_web.ai_consent.v1"
MAX_AGE_SECONDS = 600


class ConsentInvalid(Exception):
    """Forged, altered, for someone or something else, or unreadable."""


class ConsentExpired(Exception):
    """Genuine but older than 10 minutes."""


def _question_hash(question):
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def issue(user_id, material_id, tool, question, characters):
    payload = {"u": str(user_id), "m": str(material_id), "t": tool, "q": _question_hash(question),
               "c": characters, "n": secrets.token_hex(16)}
    return signing.dumps(payload, salt=SALT, compress=False)


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def check(token, user_id, material_id, tool, question):
    """Return (hash, characters) for a genuine token matching this request, ignoring its age.

    Age is checked separately (`check_fresh`), after the caller has looked for a request already
    made with this token, so an old token for a finished request still leads to it.
    """
    try:
        payload = signing.loads(token, salt=SALT, max_age=None)
    except signing.BadSignature:
        raise ConsentInvalid() from None
    expected = {"u": str(user_id), "m": str(material_id), "t": tool, "q": _question_hash(question)}
    if (not isinstance(payload, dict) or set(payload) != {"u", "m", "t", "q", "c", "n"}
            or any(payload[key] != value for key, value in expected.items())
            or type(payload["c"]) is not int or payload["c"] < 1):
        raise ConsentInvalid()
    return token_hash(token), payload["c"]


def check_fresh(token):
    try:
        signing.loads(token, salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        raise ConsentExpired() from None
    except signing.BadSignature:
        raise ConsentInvalid() from None
