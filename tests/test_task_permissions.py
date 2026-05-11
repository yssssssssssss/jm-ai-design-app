import re
from dataclasses import replace

from PIL import Image

from app.db import connect
from app.main import create_app
from app.repositories import (
    create_task,
    get_task_by_id,
    get_user_by_username,
    update_task_status,
)
from app.storage import ensure_task_dirs, relative_to_data


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _register(client, username: str):
    page = client.get("/register")
    client.post(
        "/register",
        data={
            "username": username,
            "password": "secret123",
            "invite_code": "invite-123",
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )


def _png_bytes(tmp_path, name: str):
    path = tmp_path / name
    Image.new("RGB", (16, 16), color=(107, 54, 250)).save(path)
    return path.read_bytes()


def _current_user(settings, username: str):
    conn = connect(settings.db_path)
    try:
        user = get_user_by_username(conn, username)
        assert user is not None
        return user
    finally:
        conn.close()


def _make_task(settings, user, title: str, status: str, report: bool = False):
    conn = connect(settings.db_path)
    try:
        task = create_task(conn, user.id, title, 1)
        if status != "queued":
            report_path = None
            if report:
                dirs = ensure_task_dirs(settings, task.id)
                dirs.report.write_text(f"<html>{title}</html>", encoding="utf-8")
                report_path = relative_to_data(settings, dirs.report)
            update_task_status(conn, task.id, status, report_path=report_path)
        return task
    finally:
        conn.close()


def test_upload_creates_task_and_lists_only_owner_tasks(client, tmp_path):
    _register(client, "alice")
    page = client.get("/")
    response = client.post(
        "/tasks",
        data={"title": "Alice audit", "csrf_token": _csrf(page.text)},
        files=[
            ("files", ("a.png", _png_bytes(tmp_path, "a.png"), "image/png")),
            ("files", ("b.png", _png_bytes(tmp_path, "b.png"), "image/png")),
        ],
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tasks/")

    tasks_page = client.get("/tasks/running")
    assert "Alice audit" in tasks_page.text

    client.post(
        "/logout",
        data={"csrf_token": _csrf(client.get("/tasks").text)},
        follow_redirects=False,
    )
    _register(client, "bob")
    bob_tasks = client.get("/tasks/running")
    assert "Alice audit" not in bob_tasks.text


def test_upload_persists_declared_screen_size(client, settings, tmp_path):
    _register(client, "alice")
    page = client.get("/")
    response = client.post(
        "/tasks",
        data={
            "title": "Desktop audit",
            "screen_width_px": "1440",
            "screen_height_px": "900",
            "csrf_token": _csrf(page.text),
        },
        files=[("files", ("a.png", _png_bytes(tmp_path, "a.png"), "image/png"))],
        follow_redirects=False,
    )

    assert response.status_code == 303
    task_id = int(response.headers["location"].rsplit("/", 1)[1])
    conn = connect(settings.db_path)
    try:
        task = get_task_by_id(conn, task_id)
    finally:
        conn.close()

    assert task is not None
    assert task.screen_width_px == 1440
    assert task.screen_height_px == 900


def test_upload_enqueues_task_without_running_audit(monkeypatch, settings, tmp_path):
    settings = replace(settings, enqueue_background_tasks=True)
    app = create_app(settings)
    calls = []
    monkeypatch.setattr(
        "app.routes.tasks.enqueue_task",
        lambda queued_settings, task_id: calls.append((queued_settings, task_id)),
    )

    from fastapi.testclient import TestClient

    with TestClient(app) as local_client:
        _register(local_client, "alice")
        page = local_client.get("/")
        response = local_client.post(
            "/tasks",
            data={"title": "Queued audit", "csrf_token": _csrf(page.text)},
            files=[("files", ("a.png", _png_bytes(tmp_path, "a.png"), "image/png"))],
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert len(calls) == 1
    task_id = int(response.headers["location"].rsplit("/", 1)[1])
    assert calls[0] == (settings, task_id)
    conn = connect(settings.db_path)
    try:
        task = get_task_by_id(conn, task_id)
    finally:
        conn.close()
    assert task is not None
    assert task.status == "queued"


def test_upload_rejects_partial_or_non_integer_screen_size(client, tmp_path):
    _register(client, "alice")
    page = client.get("/")
    partial = client.post(
        "/tasks",
        data={
            "title": "Bad audit",
            "screen_width_px": "1440",
            "screen_height_px": "",
            "csrf_token": _csrf(page.text),
        },
        files=[("files", ("a.png", _png_bytes(tmp_path, "a.png"), "image/png"))],
    )
    decimal = client.post(
        "/tasks",
        data={
            "title": "Bad audit",
            "screen_width_px": "1440.5",
            "screen_height_px": "900",
            "csrf_token": _csrf(page.text),
        },
        files=[("files", ("b.png", _png_bytes(tmp_path, "b.png"), "image/png"))],
    )

    assert partial.status_code == 400
    assert "截图宽度和高度需要同时填写" in partial.text
    assert decimal.status_code == 400
    assert "截图宽度和高度必须填写整数" in decimal.text


def test_task_navigation_shows_active_view_and_full_history(client, settings):
    _register(client, "alice")
    alice = _current_user(settings, "alice")
    _make_task(settings, alice, "Queued audit", "queued")
    _make_task(settings, alice, "Running audit", "running")
    _make_task(settings, alice, "Failed audit", "failed")
    _make_task(settings, alice, "Successful audit", "succeeded", report=True)

    history = client.get("/tasks")
    assert history.status_code == 200
    assert "历史任务" in history.text
    assert "Successful audit" in history.text
    assert "Queued audit" in history.text
    assert "Running audit" in history.text
    assert "Failed audit" in history.text
    assert 'class="section-heading"' not in history.text

    running = client.get("/tasks/running")
    assert running.status_code == 200
    assert "正在进行" in running.text
    assert "Queued audit" in running.text
    assert "Running audit" in running.text
    assert "Successful audit" not in running.text
    assert "Failed audit" not in running.text


def test_history_tab_shows_dot_for_new_completed_task_until_history_is_opened(
    client, settings
):
    _register(client, "alice")
    alice = _current_user(settings, "alice")
    _make_task(settings, alice, "Unread report", "succeeded", report=True)

    running = client.get("/tasks/running")
    assert '<span class="nav-dot"' in running.text

    history = client.get("/tasks")
    assert '<span class="nav-dot"' not in history.text

    running_after_read = client.get("/tasks/running")
    assert '<span class="nav-dot"' not in running_after_read.text


def test_normal_user_cannot_open_other_user_task(client, tmp_path):
    _register(client, "alice")
    page = client.get("/")
    response = client.post(
        "/tasks",
        data={"title": "Alice private", "csrf_token": _csrf(page.text)},
        files=[("files", ("a.png", _png_bytes(tmp_path, "a.png"), "image/png"))],
        follow_redirects=False,
    )
    task_url = response.headers["location"]
    client.post(
        "/logout",
        data={"csrf_token": _csrf(client.get("/tasks").text)},
        follow_redirects=False,
    )

    _register(client, "bob")
    forbidden = client.get(task_url)

    assert forbidden.status_code == 403
