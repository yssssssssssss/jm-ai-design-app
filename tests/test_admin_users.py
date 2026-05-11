import re

from app.db import connect
from app.models import ROLE_ADMIN, ROLE_USER, STATUS_DISABLED
from app.repositories import create_user, get_user_by_id, get_user_by_username
from app.repositories import set_user_role_preserving_last_admin
from app.repositories import set_user_status_preserving_last_admin
from app.security import hash_password


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _register(client, username: str):
    page = client.get("/register")
    return client.post(
        "/register",
        data={
            "username": username,
            "password": "secret123",
            "invite_code": "invite-123",
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )


def _logout(client, path: str = "/tasks"):
    page = client.get(path)
    return client.post(
        "/logout",
        data={"csrf_token": _csrf(page.text)},
        follow_redirects=False,
    )


def _login_admin(client):
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "username": "admin",
            "password": "admin-pass",
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )


def _user(settings, username: str):
    conn = connect(settings.db_path)
    try:
        user = get_user_by_username(conn, username)
        assert user is not None
        return user
    finally:
        conn.close()


def test_preserving_last_admin_helpers_reject_last_active_admin_changes(client, settings):
    conn = connect(settings.db_path)
    try:
        admin = get_user_by_username(conn, "admin")
        assert admin is not None

        try:
            set_user_status_preserving_last_admin(conn, admin.id, STATUS_DISABLED)
        except ValueError as exc:
            assert str(exc) == "last active admin"
        else:
            raise AssertionError("last active admin should not be disabled")

        try:
            set_user_role_preserving_last_admin(conn, admin.id, ROLE_USER)
        except ValueError as exc:
            assert str(exc) == "last active admin"
        else:
            raise AssertionError("last active admin should not be demoted")
    finally:
        conn.close()


def test_preserving_last_admin_helpers_allow_changes_when_another_admin_exists(
    client, settings
):
    conn = connect(settings.db_path)
    try:
        admin = get_user_by_username(conn, "admin")
        assert admin is not None
        create_user(conn, "second-admin", hash_password("secret123"), ROLE_ADMIN)

        set_user_status_preserving_last_admin(conn, admin.id, STATUS_DISABLED)

        changed = get_user_by_id(conn, admin.id)
        assert changed is not None
        assert changed.status == STATUS_DISABLED
    finally:
        conn.close()


def test_normal_user_cannot_open_admin_users(client):
    _register(client, "alice")
    response = client.get("/admin/users")

    assert response.status_code == 403


def test_normal_user_cannot_post_admin_action(client, settings):
    _register(client, "alice")
    page = client.get("/tasks")
    user_id = _user(settings, "alice").id

    response = client.post(
        f"/admin/users/{user_id}/status",
        data={"status": "disabled", "csrf_token": _csrf(page.text)},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_admin_can_disable_and_enable_user(client, settings):
    _register(client, "alice")
    _logout(client)
    _login_admin(client)
    user_id = _user(settings, "alice").id

    users_page = client.get("/admin/users")
    assert users_page.status_code == 200
    assert "alice" in users_page.text

    response = client.post(
        f"/admin/users/{user_id}/status",
        data={"status": "disabled", "csrf_token": _csrf(users_page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    _logout(client, "/admin/users")
    login_page = client.get("/login")
    failed_login = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "secret123",
            "csrf_token": _csrf(login_page.text),
        },
    )
    assert "用户名或密码错误" in failed_login.text

    _login_admin(client)
    users_page = client.get("/admin/users")
    response = client.post(
        f"/admin/users/{user_id}/status",
        data={"status": "active", "csrf_token": _csrf(users_page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    _logout(client, "/admin/users")
    login_page = client.get("/login")
    restored_login = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "secret123",
            "csrf_token": _csrf(login_page.text),
        },
        follow_redirects=False,
    )
    assert restored_login.status_code == 303


def test_admin_can_reset_password_and_old_password_stops_working(client, settings):
    _register(client, "alice")
    _logout(client)
    _login_admin(client)
    users_page = client.get("/admin/users")
    user_id = _user(settings, "alice").id

    response = client.post(
        f"/admin/users/{user_id}/password",
        data={"password": "newsecret123", "csrf_token": _csrf(users_page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    _logout(client, "/admin/users")
    login_page = client.get("/login")
    old_password = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "secret123",
            "csrf_token": _csrf(login_page.text),
        },
    )
    assert "用户名或密码错误" in old_password.text

    login_page = client.get("/login")
    new_password = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "newsecret123",
            "csrf_token": _csrf(login_page.text),
        },
        follow_redirects=False,
    )
    assert new_password.status_code == 303


def test_admin_action_rejects_invalid_csrf(client, settings):
    _register(client, "alice")
    _logout(client)
    _login_admin(client)
    user_id = _user(settings, "alice").id

    response = client.post(
        f"/admin/users/{user_id}/status",
        data={"status": "disabled", "csrf_token": "invalid"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid CSRF token" in response.text


def test_admin_action_rejects_missing_csrf(client, settings):
    _register(client, "alice")
    _logout(client)
    _login_admin(client)
    user_id = _user(settings, "alice").id

    response = client.post(
        f"/admin/users/{user_id}/status",
        data={"status": "disabled"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid CSRF token" in response.text


def test_admin_can_manage_username_with_slash_through_user_id(client, settings):
    _register(client, "a/bc")
    _logout(client)
    _login_admin(client)
    target = _user(settings, "a/bc")

    users_page = client.get("/admin/users")
    assert users_page.status_code == 200
    assert "a/bc" in users_page.text
    assert f'action="/admin/users/{target.id}/status"' in users_page.text

    response = client.post(
        f"/admin/users/{target.id}/status",
        data={"status": "disabled", "csrf_token": _csrf(users_page.text)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert _user(settings, "a/bc").status == STATUS_DISABLED


def test_cannot_disable_last_active_admin(client, settings):
    page = client.get("/login")
    client.post(
        "/login",
        data={
            "username": "admin",
            "password": "admin-pass",
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )
    users_page = client.get("/admin/users")
    admin_id = _user(settings, "admin").id

    response = client.post(
        f"/admin/users/{admin_id}/status",
        data={"status": "disabled", "csrf_token": _csrf(users_page.text)},
    )

    assert response.status_code == 400
    assert "不能禁用最后一个管理员" in response.text


def test_cannot_demote_last_active_admin(client, settings):
    _login_admin(client)
    users_page = client.get("/admin/users")
    admin_id = _user(settings, "admin").id

    response = client.post(
        f"/admin/users/{admin_id}/role",
        data={"role": "user", "csrf_token": _csrf(users_page.text)},
    )

    assert response.status_code == 400
    assert "不能降级最后一个管理员" in response.text
