import re
import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _register(client, username: str = "alice", password: str = "secret123"):
    register_page = client.get("/register")
    return client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "invite_code": "invite-123",
            "csrf_token": _csrf(register_page.text),
        },
        follow_redirects=False,
    )


def test_register_requires_invite_code(client):
    register_page = client.get("/register")
    response = client.post(
        "/register",
        data={
            "username": "alice",
            "password": "secret123",
            "invite_code": "wrong",
            "csrf_token": _csrf(register_page.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "邀请码错误" in response.text


def test_register_login_and_logout(client):
    response = _register(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    tasks = client.get("/tasks")
    assert tasks.status_code == 200
    assert "历史任务" in tasks.text

    logout = client.post(
        "/logout",
        data={"csrf_token": _csrf(tasks.text)},
        follow_redirects=False,
    )
    assert logout.status_code == 303

    logged_out_tasks = client.get("/tasks", follow_redirects=False)
    assert logged_out_tasks.status_code == 303
    assert logged_out_tasks.headers["location"] == "/login"

    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "secret123",
            "csrf_token": _csrf(login_page.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    tasks = client.get("/tasks")
    assert tasks.status_code == 200
    assert "历史任务" in tasks.text

    logout = client.post(
        "/logout",
        data={"csrf_token": _csrf(tasks.text)},
        follow_redirects=False,
    )
    assert logout.status_code == 303

    logged_out_tasks = client.get("/tasks", follow_redirects=False)
    assert logged_out_tasks.status_code == 303
    assert logged_out_tasks.headers["location"] == "/login"


def test_app_factory_uses_package_static_and_templates(settings, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/register")

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text


def test_register_rejects_duplicate_username(client):
    response = _register(client)
    assert response.status_code == 303

    response = _register(client)

    assert response.status_code == 400
    assert "用户名已存在" in response.text


def test_register_handles_unique_race_as_duplicate_username(client, monkeypatch):
    def raise_integrity_error(conn, username, password_hash, role):
        raise sqlite3.IntegrityError("unique constraint failed: users.username")

    monkeypatch.setattr("app.routes.auth.create_user", raise_integrity_error)
    register_page = client.get("/register")

    response = client.post(
        "/register",
        data={
            "username": "alice",
            "password": "secret123",
            "invite_code": "invite-123",
            "csrf_token": _csrf(register_page.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "用户名已存在" in response.text


def test_login_rejects_wrong_password(client):
    response = _register(client)
    assert response.status_code == 303

    tasks = client.get("/tasks")
    client.post(
        "/logout",
        data={"csrf_token": _csrf(tasks.text)},
        follow_redirects=False,
    )
    login_page = client.get("/login")

    response = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "wrong-password",
            "csrf_token": _csrf(login_page.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    redirected_page = client.get("/login")
    assert redirected_page.status_code == 200
    assert "用户名或密码错误" in redirected_page.text


def test_register_rejects_invalid_csrf(client):
    response = client.post(
        "/register",
        data={
            "username": "alice",
            "password": "secret123",
            "invite_code": "invite-123",
            "csrf_token": "invalid",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid CSRF token" in response.text
