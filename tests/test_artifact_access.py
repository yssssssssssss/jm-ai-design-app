import re

from app.db import connect
from app.repositories import create_task, create_user, update_task_status
from app.security import hash_password
from app.storage import ensure_task_dirs, relative_to_data


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _login(client, username: str, password: str):
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )


def test_report_requires_task_permission(client, settings):
    conn = connect(settings.db_path)
    alice = create_user(conn, "alice", hash_password("secret123"), "user")
    create_user(conn, "bob", hash_password("secret123"), "user")
    task = create_task(conn, alice.id, "Private report", 1)
    dirs = ensure_task_dirs(settings, task.id)
    dirs.report.write_text("<html>private</html>", encoding="utf-8")
    update_task_status(
        conn,
        task.id,
        "succeeded",
        report_path=relative_to_data(settings, dirs.report),
    )
    conn.close()

    _login(client, "bob", "secret123")
    forbidden = client.get(f"/tasks/{task.id}/report.html")
    assert forbidden.status_code == 403

    client.post(
        "/logout",
        data={"csrf_token": _csrf(client.get("/tasks").text)},
        follow_redirects=False,
    )
    _login(client, "alice", "secret123")
    allowed = client.get(f"/tasks/{task.id}/report.html")
    assert allowed.status_code == 200
    assert "private" in allowed.text


def test_artifact_path_traversal_is_rejected(client, settings):
    conn = connect(settings.db_path)
    alice = create_user(conn, "alice", hash_password("secret123"), "user")
    task = create_task(conn, alice.id, "Private report", 1)
    conn.close()
    _login(client, "alice", "secret123")

    response = client.get(f"/artifacts/{task.id}/../app.db")
    assert response.status_code in {400, 404}


def test_artifact_requires_task_permission(client, settings):
    conn = connect(settings.db_path)
    alice = create_user(conn, "alice", hash_password("secret123"), "user")
    create_user(conn, "bob", hash_password("secret123"), "user")
    task = create_task(conn, alice.id, "Private artifacts", 1)
    dirs = ensure_task_dirs(settings, task.id)
    artifact = dirs.artifacts / "image-001" / "tokens.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"private": true}', encoding="utf-8")
    conn.close()

    _login(client, "bob", "secret123")
    forbidden = client.get(f"/artifacts/{task.id}/image-001/tokens.json")
    assert forbidden.status_code == 403

    client.post(
        "/logout",
        data={"csrf_token": _csrf(client.get("/tasks").text)},
        follow_redirects=False,
    )
    _login(client, "alice", "secret123")
    allowed = client.get(f"/artifacts/{task.id}/image-001/tokens.json")
    assert allowed.status_code == 200
    assert allowed.json() == {"private": True}
