"""Only a live, signed server-side Django session establishes academic identity."""
from dataclasses import dataclass, field
import time
import uuid
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.utils.crypto import constant_time_compare
from .backends import StudentBackend
from .boundary import require_auth_role


@dataclass(frozen=True)
class VerifiedSessionPrincipal:
    student_id: uuid.UUID
    session_key: str = field(repr=False)
    auth_hash: str = field(repr=False)
    expires_at: int
    proof: str = field(repr=False)


def session_student(session_key):
    """Revalidate DB session signature/expiry, backend, password hash, active + verified status."""
    if not isinstance(session_key, str) or len(session_key) != 32 or not session_key.isalnum():
        return None
    require_auth_role()
    session = SessionStore(session_key=session_key).load()
    if session.get(BACKEND_SESSION_KEY) != "accounts.backends.StudentBackend":
        return None
    student = StudentBackend().get_user(session.get(SESSION_KEY))
    saved_hash = session.get(HASH_SESSION_KEY)
    if not student or not isinstance(saved_hash, str) or not constant_time_compare(saved_hash, student.get_session_auth_hash()):
        return None
    return student


def principal_for_request(request):
    from academics.ownership import OwnershipRequired, signature
    session = getattr(request, 'session', None)
    key = getattr(session, 'session_key', None)
    student = session_student(key)
    if (not student or not getattr(getattr(request, 'user', None), 'is_authenticated', False)
            or request.user.pk != student.pk):
        raise OwnershipRequired()
    expires = int(time.time()) + 300
    auth_hash = student.get_session_auth_hash()
    payload = f"verified-session|{student.pk}|{key}|{auth_hash}|{expires}"
    return VerifiedSessionPrincipal(student.pk, key, auth_hash, expires, signature(payload))


def validate_principal(principal):
    from academics.ownership import OwnershipRequired, signature
    if (not isinstance(principal, VerifiedSessionPrincipal) or not isinstance(principal.student_id, uuid.UUID)
            or type(principal.expires_at) is not int or principal.expires_at <= time.time()
            or not isinstance(principal.proof, str) or not principal.proof.isascii()
            or len(principal.proof) != 64):
        raise OwnershipRequired()
    payload = (f"verified-session|{principal.student_id}|{principal.session_key}|"
               f"{principal.auth_hash}|{principal.expires_at}")
    if not constant_time_compare(principal.proof, signature(payload)):
        raise OwnershipRequired()
    student = session_student(principal.session_key)
    if not student or student.pk != principal.student_id or not constant_time_compare(
            student.get_session_auth_hash(), principal.auth_hash):
        raise OwnershipRequired()
    return student
