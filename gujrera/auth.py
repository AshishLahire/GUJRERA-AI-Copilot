"""Login for the prototype: PBKDF2 passwords, signed expiring tokens, and lockout.

This is enough to demonstrate role-based access with seeded demo accounts. A
GUJRERA deployment would replace ``authenticate`` with its own sign-in
(portal SSO or mobile OTP) and keep the rest: the token carries only the user
id and role, and every data rule is enforced in ``Repository``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from gujrera.config import get_gujrera_settings
from gujrera.db.models import User
from gujrera.db.repository import Principal

PBKDF2_ITERATIONS = 200_000
MAX_FAILURES = 5
LOCK_SECONDS = 300


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    key = get_gujrera_settings().GUJRERA_AUTH_SECRET.get_secret_value().encode()
    return _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def issue_token(user: User, *, now: float | None = None) -> str:
    now = now or time.time()
    body = _b64(json.dumps({"uid": user.id, "role": user.role, "v": user.token_version or 0,
                            "exp": int(now + get_gujrera_settings().GUJRERA_TOKEN_HOURS * 3600)}).encode())
    return f"{body}.{_sign(body)}"


def read_token(token: str, session: Session, *, now: float | None = None) -> User | None:
    """The user the token belongs to, or None if it is forged, expired or the role changed."""
    try:
        body, sig = token.split(".")
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < (now or time.time()):
        return None
    user = session.get(User, data.get("uid"))
    if user is None or user.role != data.get("role"):
        return None
    # A disabled account, or one whose password was reset, loses every session it had.
    if user.is_active is False or data.get("v", 0) != (user.token_version or 0):
        return None
    return user


@dataclass
class _Failures:
    count: int = 0
    locked_until: float = 0.0


class LoginLimiter:
    """Locks a username for LOCK_SECONDS after MAX_FAILURES wrong passwords (per process)."""

    def __init__(self) -> None:
        self._items: dict[str, _Failures] = {}
        self._lock = threading.Lock()

    def locked(self, username: str) -> bool:
        with self._lock:
            f = self._items.get(username)
            return bool(f and f.locked_until > time.time())

    def fail(self, username: str) -> None:
        with self._lock:
            f = self._items.setdefault(username, _Failures())
            f.count += 1
            if f.count >= MAX_FAILURES:
                f.count, f.locked_until = 0, time.time() + LOCK_SECONDS

    def success(self, username: str) -> None:
        with self._lock:
            self._items.pop(username, None)


LIMITER = LoginLimiter()


class LoginError(Exception):
    def __init__(self, message: str, locked: bool = False, disabled: bool = False):
        super().__init__(message)
        self.locked = locked
        self.disabled = disabled


def authenticate(session: Session, username: str, password: str, limiter: LoginLimiter = LIMITER) -> User:
    username = (username or "").strip().lower()
    if limiter.locked(username):
        raise LoginError("Too many failed attempts. Try again in a few minutes.", locked=True)
    user = session.scalar(select(User).where(User.username == username))
    # Verify against a dummy hash when the user is unknown, so timing does not reveal valid usernames.
    ok = verify_password(password or "", user.password_hash if user else _DUMMY_HASH)
    if not (user and ok):
        limiter.fail(username)
        raise LoginError("Wrong username or password.")
    if user.is_active is False:
        raise LoginError("This account is disabled. Contact the GUJRERA administrator.", disabled=True)
    limiter.success(username)
    return user


_DUMMY_HASH = hash_password("not-a-real-password", salt=b"\0" * 16)


def principal_for(user: User | None) -> Principal:
    return Principal.from_user(user) if user else Principal.anonymous()
