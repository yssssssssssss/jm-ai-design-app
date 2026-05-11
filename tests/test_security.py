from app.db import connect, init_db
from app.models import ROLE_ADMIN, ROLE_USER, STATUS_DISABLED
from app.repositories import create_user, get_user_by_id, set_user_status
from app.security import (
    CsrfError,
    ForbiddenError,
    hash_password,
    require_admin,
    require_login,
    verify_csrf,
    verify_password,
)


def test_password_hash_verification_roundtrip():
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)
    assert verify_password("secret", "not-a-hash") is False


def test_require_login_rejects_missing_and_disabled_user(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    disabled = create_user(conn, "disabled", hash_password("secret"), ROLE_USER)
    set_user_status(conn, disabled.id, STATUS_DISABLED)
    disabled = get_user_by_id(conn, disabled.id)

    try:
        require_login(None)
    except ForbiddenError as exc:
        assert exc.status_code == 303
    else:
        raise AssertionError("missing user should be rejected")

    try:
        require_login(disabled)
    except ForbiddenError as exc:
        assert exc.status_code == 303
    else:
        raise AssertionError("disabled user should be rejected")


def test_require_admin_rejects_normal_user(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", hash_password("secret"), ROLE_USER)
    admin = create_user(conn, "admin", hash_password("secret"), ROLE_ADMIN)

    try:
        require_admin(user)
    except ForbiddenError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("normal user should not pass admin guard")

    assert require_admin(admin) == admin


def test_verify_csrf_matches_session_token(monkeypatch):
    compared = []

    def compare_digest(left, right):
        compared.append((left, right))
        return left == right

    monkeypatch.setattr("app.security.secrets.compare_digest", compare_digest)

    assert verify_csrf({"csrf_token": "abc"}, "abc") is None
    assert compared == [("abc", "abc")]

    try:
        verify_csrf({"csrf_token": "abc"}, "wrong")
    except CsrfError as exc:
        assert "Invalid CSRF token" in str(exc)
    else:
        raise AssertionError("mismatched token should fail")


def test_verify_csrf_rejects_missing_or_invalid_tokens():
    invalid_cases = [
        ({}, "abc"),
        ({"csrf_token": "abc"}, None),
        ({"csrf_token": ""}, "abc"),
        ({"csrf_token": "abc"}, ""),
        ({"csrf_token": 123}, "123"),
    ]

    for session, submitted_token in invalid_cases:
        try:
            verify_csrf(session, submitted_token)
        except CsrfError as exc:
            assert "Invalid CSRF token" in str(exc)
        else:
            raise AssertionError("invalid token should fail")


def test_verify_csrf_rejects_non_ascii_submitted_token():
    try:
        verify_csrf({"csrf_token": "abc"}, "错")
    except CsrfError as exc:
        assert "Invalid CSRF token" in str(exc)
    else:
        raise AssertionError("non-ASCII token should fail")


def test_set_user_status_rejects_missing_user(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)

    try:
        set_user_status(conn, 999, STATUS_DISABLED)
    except ValueError as exc:
        assert str(exc) == "user not found"
    else:
        raise AssertionError("missing user should fail")
