from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.models import ROLE_ADMIN, STATUS_ACTIVE, User


_hasher = PasswordHasher()


@dataclass
class ForbiddenError(Exception):
    message: str
    status_code: int = 403

    def __str__(self) -> str:
        return self.message


class CsrfError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError, VerificationError):
        return False


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(session: dict, submitted_token: str | None) -> None:
    session_token = session.get("csrf_token")
    if (
        not isinstance(session_token, str)
        or not isinstance(submitted_token, str)
        or not session_token
        or not submitted_token
    ):
        raise CsrfError("Invalid CSRF token")
    try:
        matches = secrets.compare_digest(session_token, submitted_token)
    except TypeError as exc:
        raise CsrfError("Invalid CSRF token") from exc
    if not matches:
        raise CsrfError("Invalid CSRF token")


def require_login(user: User | None) -> User:
    if user is None or user.status != STATUS_ACTIVE:
        raise ForbiddenError("Login required", status_code=303)
    return user


def require_admin(user: User | None) -> User:
    user = require_login(user)
    if user.role != ROLE_ADMIN:
        raise ForbiddenError("Admin role required", status_code=403)
    return user
