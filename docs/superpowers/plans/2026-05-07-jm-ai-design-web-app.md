# JM AI Design Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-port FastAPI web app where invited users upload multiple screenshots, receive one JM AI design-audit HTML report, and can only view reports allowed by their role.

**Architecture:** A FastAPI monolith serves Jinja2 pages, JSON endpoints, reports, and artifacts. SQLite stores users/tasks/image records; local task directories store uploads and generated evidence. The OpenAI vision audit adapter, evidence wrappers, task runner, and report renderer are separate modules with narrow interfaces.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLite via `sqlite3`, Starlette sessions, Argon2 password hashing, OpenAI Responses API, Pillow, pytest, FastAPI TestClient.

---

## References

- Design spec: `docs/superpowers/specs/2026-05-07-jm-ai-design-web-app-design.md`
- Skill workflow: `SKILL.md`
- JM AI rules: `references/jm-ai-design-spec.md`
- HTML template source: `references/html-report-template.md`
- FastAPI docs consulted through Context7: UploadFile/Form, Jinja2 templates, StaticFiles, BackgroundTasks, TestClient.
- OpenAI official docs consulted:
  - Responses API: https://platform.openai.com/docs/api-reference/responses
  - Image inputs: https://platform.openai.com/docs/guides/images-vision
  - Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs

## File Structure

Create this structure:

```text
pyproject.toml
README.md
app/
  __init__.py
  main.py
  config.py
  db.py
  models.py
  security.py
  storage.py
  repositories.py
  openai_audit.py
  evidence_tools.py
  report_renderer.py
  task_runner.py
  routes/
    __init__.py
    auth.py
    tasks.py
    admin.py
  templates/
    base.html
    login.html
    register.html
    upload.html
    tasks.html
    task_detail.html
    admin_users.html
  static/
    app.css
    app.js
tests/
  conftest.py
  test_config_db.py
  test_security.py
  test_auth_routes.py
  test_admin_users.py
  test_storage.py
  test_task_permissions.py
  test_openai_audit.py
  test_evidence_tools.py
  test_report_renderer.py
  test_task_runner.py
  test_artifact_access.py
```

Responsibilities:

- `config.py`: environment parsing and defaults.
- `db.py`: SQLite connection, schema initialization, transaction helper.
- `models.py`: dataclasses and enum constants only.
- `security.py`: password hashing, session user loading, CSRF helpers, role guards.
- `storage.py`: safe task paths, upload validation, artifact path normalization.
- `repositories.py`: all SQL reads and writes.
- `openai_audit.py`: OpenAI request construction, JSON schema, response parsing.
- `evidence_tools.py`: wrappers for existing scripts under `scripts/`.
- `report_renderer.py`: safe HTML rendering for aggregate reports.
- `task_runner.py`: image-level orchestration and task status transitions.
- `routes/*`: thin HTTP adapters only.

## Execution Rules

- Use TDD for each task: write focused tests, see them fail, implement the minimal behavior, rerun.
- Keep route functions thin. Business logic belongs in services, repositories, or storage.
- Do not add React, a queue service, PostgreSQL, object storage, or SSO.
- If the directory is still not a git repository, skip commit commands and record `commit skipped: not a git repository` in your implementation notes.

---

### Task 1: Project Scaffold And Settings

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `tests/test_config_db.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config_db.py` with:

```python
from app.config import Settings, load_settings


def test_settings_uses_defaults_for_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("APP_SECRET_KEY", "secret")
    monkeypatch.setenv("REGISTER_INVITE_CODE", "invite")
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "password123")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    settings = load_settings()

    assert settings.max_upload_files == 8
    assert settings.max_upload_mb_per_file == 10
    assert settings.openai_audit_model == "gpt-4.1-mini"
    assert settings.data_dir == tmp_path


def test_settings_rejects_missing_required_env(monkeypatch):
    for key in [
        "OPENAI_API_KEY",
        "APP_SECRET_KEY",
        "REGISTER_INVITE_CODE",
        "INITIAL_ADMIN_USERNAME",
        "INITIAL_ADMIN_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)

    try:
        load_settings()
    except RuntimeError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("load_settings should fail when required env vars are missing")


def test_settings_can_be_constructed_directly(tmp_path):
    settings = Settings(
        openai_api_key="test-key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
    )

    assert settings.uploads_dir == tmp_path / "uploads"
    assert settings.db_path == tmp_path / "app.db"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_config_db.py -q
```

Expected: failure because `app.config` does not exist.

- [ ] **Step 3: Create package metadata**

Create `pyproject.toml`:

```toml
[project]
name = "jm-ai-design-web-app"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "jinja2>=3.1",
  "python-multipart>=0.0.9",
  "pillow>=10.0",
  "openai>=1.0",
  "argon2-cffi>=23.1",
  "itsdangerous>=2.2",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "httpx>=0.27",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 4: Implement settings**

Create `app/__init__.py` as an empty package marker.

Create `app/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REQUIRED_ENV = [
    "OPENAI_API_KEY",
    "APP_SECRET_KEY",
    "REGISTER_INVITE_CODE",
    "INITIAL_ADMIN_USERNAME",
    "INITIAL_ADMIN_PASSWORD",
]


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    app_secret_key: str
    register_invite_code: str
    initial_admin_username: str
    initial_admin_password: str
    data_dir: Path
    openai_audit_model: str = "gpt-4.1-mini"
    max_upload_files: int = 8
    max_upload_mb_per_file: int = 10
    secure_cookies: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


def load_settings() -> Settings:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    data_dir = Path(os.getenv("DATA_DIR", "data")).expanduser().resolve()
    return Settings(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        app_secret_key=os.environ["APP_SECRET_KEY"],
        register_invite_code=os.environ["REGISTER_INVITE_CODE"],
        initial_admin_username=os.environ["INITIAL_ADMIN_USERNAME"],
        initial_admin_password=os.environ["INITIAL_ADMIN_PASSWORD"],
        data_dir=data_dir,
        openai_audit_model=os.getenv("OPENAI_AUDIT_MODEL", "gpt-4.1-mini"),
        max_upload_files=int(os.getenv("MAX_UPLOAD_FILES", "8")),
        max_upload_mb_per_file=int(os.getenv("MAX_UPLOAD_MB_PER_FILE", "10")),
        secure_cookies=os.getenv("SECURE_COOKIES", "false").lower() == "true",
    )
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
pytest tests/test_config_db.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add pyproject.toml app/__init__.py app/config.py tests/test_config_db.py
git commit -m "chore: scaffold FastAPI app settings"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 2: SQLite Schema And Repositories

**Files:**
- Create: `app/models.py`
- Create: `app/db.py`
- Create: `app/repositories.py`
- Modify: `tests/test_config_db.py`

- [ ] **Step 1: Add failing database tests**

Append to `tests/test_config_db.py`:

```python
from app.db import connect, init_db
from app.repositories import (
    create_user,
    count_active_admins,
    create_task,
    add_task_image,
    list_tasks_for_user,
)


def test_init_db_creates_core_tables(tmp_path):
    db_path = tmp_path / "app.db"
    conn = connect(db_path)
    init_db(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }

    assert {"users", "tasks", "task_images"}.issubset(tables)


def test_repositories_create_users_tasks_and_filter_by_owner(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)

    admin = create_user(conn, "admin", "hash-1", "admin")
    user_a = create_user(conn, "alice", "hash-2", "user")
    user_b = create_user(conn, "bob", "hash-3", "user")

    task_a = create_task(conn, owner_id=user_a.id, title="Alice task", image_count=1)
    task_b = create_task(conn, owner_id=user_b.id, title="Bob task", image_count=1)
    add_task_image(
        conn,
        task_id=task_a.id,
        filename="image-001.png",
        original_path="uploads/a/originals/image-001.png",
        sort_order=0,
    )

    assert count_active_admins(conn) == 1
    assert [task.id for task in list_tasks_for_user(conn, user_a)] == [task_a.id]
    assert {task.id for task in list_tasks_for_user(conn, admin)} == {task_a.id, task_b.id}
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_config_db.py -q
```

Expected: failure because `app.db` and repositories do not exist.

- [ ] **Step 3: Create model dataclasses**

Create `app/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


ROLE_ADMIN = "admin"
ROLE_USER = "user"
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"
TASK_QUEUED = "queued"
TASK_RUNNING = "running"
TASK_SUCCEEDED = "succeeded"
TASK_FAILED = "failed"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    role: str
    status: str
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


@dataclass(frozen=True)
class Task:
    id: int
    owner_id: int
    title: str
    status: str
    image_count: int
    summary: str | None
    report_path: str | None
    error_message: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    owner_username: str | None = None


@dataclass(frozen=True)
class TaskImage:
    id: int
    task_id: int
    filename: str
    original_path: str
    sort_order: int
    status: str
    annotated_path: str | None = None
    tokens_path: str | None = None
    measurements_path: str | None = None
    issues_path: str | None = None
    audit_json_path: str | None = None
    error_message: str | None = None
```

- [ ] **Step 4: Implement SQLite schema**

Create `app/db.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists users (
          id integer primary key autoincrement,
          username text not null unique,
          password_hash text not null,
          role text not null check (role in ('admin', 'user')),
          status text not null default 'active' check (status in ('active', 'disabled')),
          created_at text not null default current_timestamp,
          last_login_at text
        );

        create table if not exists tasks (
          id integer primary key autoincrement,
          owner_id integer not null references users(id),
          title text not null,
          status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
          image_count integer not null,
          summary text,
          report_path text,
          error_message text,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          completed_at text
        );

        create table if not exists task_images (
          id integer primary key autoincrement,
          task_id integer not null references tasks(id) on delete cascade,
          filename text not null,
          original_path text not null,
          annotated_path text,
          tokens_path text,
          measurements_path text,
          issues_path text,
          audit_json_path text,
          sort_order integer not null,
          status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
          error_message text
        );

        create index if not exists idx_tasks_owner_created on tasks(owner_id, created_at desc);
        create index if not exists idx_task_images_task_order on task_images(task_id, sort_order);
        """
    )
    conn.commit()
```

- [ ] **Step 5: Implement repositories**

Create `app/repositories.py`:

```python
from __future__ import annotations

import sqlite3
from typing import Iterable

from app.models import (
    ROLE_ADMIN,
    STATUS_ACTIVE,
    TASK_QUEUED,
    TASK_RUNNING,
    TASK_SUCCEEDED,
    TASK_FAILED,
    Task,
    TaskImage,
    User,
)


def _user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=row["role"],
        status=row["status"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


def _task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        owner_id=row["owner_id"],
        title=row["title"],
        status=row["status"],
        image_count=row["image_count"],
        summary=row["summary"],
        report_path=row["report_path"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        owner_username=row["owner_username"] if "owner_username" in row.keys() else None,
    )


def _image(row: sqlite3.Row) -> TaskImage:
    return TaskImage(
        id=row["id"],
        task_id=row["task_id"],
        filename=row["filename"],
        original_path=row["original_path"],
        annotated_path=row["annotated_path"],
        tokens_path=row["tokens_path"],
        measurements_path=row["measurements_path"],
        issues_path=row["issues_path"],
        audit_json_path=row["audit_json_path"],
        sort_order=row["sort_order"],
        status=row["status"],
        error_message=row["error_message"],
    )


def create_user(conn: sqlite3.Connection, username: str, password_hash: str, role: str) -> User:
    cur = conn.execute(
        "insert into users (username, password_hash, role) values (?, ?, ?)",
        (username, password_hash, role),
    )
    conn.commit()
    return get_user_by_id(conn, int(cur.lastrowid))


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
    return _user(row) if row else None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> User | None:
    row = conn.execute("select * from users where username = ?", (username,)).fetchone()
    return _user(row) if row else None


def count_active_admins(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "select count(*) as count from users where role = ? and status = ?",
        (ROLE_ADMIN, STATUS_ACTIVE),
    ).fetchone()
    return int(row["count"])


def create_task(conn: sqlite3.Connection, owner_id: int, title: str, image_count: int) -> Task:
    cur = conn.execute(
        """
        insert into tasks (owner_id, title, status, image_count)
        values (?, ?, ?, ?)
        """,
        (owner_id, title, TASK_QUEUED, image_count),
    )
    conn.commit()
    return get_task_by_id(conn, int(cur.lastrowid))


def add_task_image(
    conn: sqlite3.Connection,
    task_id: int,
    filename: str,
    original_path: str,
    sort_order: int,
) -> TaskImage:
    cur = conn.execute(
        """
        insert into task_images (task_id, filename, original_path, sort_order, status)
        values (?, ?, ?, ?, ?)
        """,
        (task_id, filename, original_path, sort_order, TASK_QUEUED),
    )
    conn.commit()
    return get_task_image_by_id(conn, int(cur.lastrowid))


def get_task_by_id(conn: sqlite3.Connection, task_id: int) -> Task | None:
    row = conn.execute(
        """
        select tasks.*, users.username as owner_username
        from tasks
        join users on users.id = tasks.owner_id
        where tasks.id = ?
        """,
        (task_id,),
    ).fetchone()
    return _task(row) if row else None


def get_task_image_by_id(conn: sqlite3.Connection, image_id: int) -> TaskImage | None:
    row = conn.execute("select * from task_images where id = ?", (image_id,)).fetchone()
    return _image(row) if row else None


def list_task_images(conn: sqlite3.Connection, task_id: int) -> list[TaskImage]:
    rows = conn.execute(
        "select * from task_images where task_id = ? order by sort_order asc",
        (task_id,),
    ).fetchall()
    return [_image(row) for row in rows]


def list_tasks_for_user(conn: sqlite3.Connection, user: User) -> list[Task]:
    if user.is_admin:
        rows = conn.execute(
            """
            select tasks.*, users.username as owner_username
            from tasks
            join users on users.id = tasks.owner_id
            order by tasks.created_at desc, tasks.id desc
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select tasks.*, users.username as owner_username
            from tasks
            join users on users.id = tasks.owner_id
            where tasks.owner_id = ?
            order by tasks.created_at desc, tasks.id desc
            """,
            (user.id,),
        ).fetchall()
    return [_task(row) for row in rows]
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/test_config_db.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add app/models.py app/db.py app/repositories.py tests/test_config_db.py
git commit -m "feat: add sqlite schema and repositories"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 3: Passwords, Sessions, CSRF, And Auth Guards

**Files:**
- Create: `app/security.py`
- Create: `tests/test_security.py`
- Modify: `app/repositories.py`

- [ ] **Step 1: Write failing security tests**

Create `tests/test_security.py`:

```python
from starlette.requests import Request

from app.db import connect, init_db
from app.models import ROLE_ADMIN, ROLE_USER, STATUS_DISABLED
from app.repositories import create_user, set_user_status
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


def test_require_login_rejects_missing_and_disabled_user(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    disabled = create_user(conn, "disabled", hash_password("secret"), ROLE_USER)
    set_user_status(conn, disabled.id, STATUS_DISABLED)

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


def test_verify_csrf_matches_session_token():
    assert verify_csrf({"csrf_token": "abc"}, "abc") is None

    try:
        verify_csrf({"csrf_token": "abc"}, "wrong")
    except CsrfError as exc:
        assert "Invalid CSRF token" in str(exc)
    else:
        raise AssertionError("mismatched token should fail")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_security.py -q
```

Expected: failure because `security.py` and `set_user_status` do not exist.

- [ ] **Step 3: Add user status repository helper**

Append to `app/repositories.py`:

```python
def set_user_status(conn: sqlite3.Connection, user_id: int, status: str) -> None:
    conn.execute("update users set status = ? where id = ?", (status, user_id))
    conn.commit()


def set_user_password(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    conn.execute("update users set password_hash = ? where id = ?", (password_hash, user_id))
    conn.commit()


def set_user_role(conn: sqlite3.Connection, user_id: int, role: str) -> None:
    conn.execute("update users set role = ? where id = ?", (role, user_id))
    conn.commit()


def mark_user_login(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("update users set last_login_at = current_timestamp where id = ?", (user_id,))
    conn.commit()
```

- [ ] **Step 4: Implement security helpers**

Create `app/security.py`:

```python
from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

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
    except (VerifyMismatchError, VerificationError):
        return False


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(session: dict, submitted_token: str | None) -> None:
    if not submitted_token or session.get("csrf_token") != submitted_token:
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
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_security.py tests/test_config_db.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add app/security.py app/repositories.py tests/test_security.py
git commit -m "feat: add security helpers"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 4: FastAPI App Factory, Login, Registration, And Templates

**Files:**
- Create: `app/main.py`
- Create: `app/routes/__init__.py`
- Create: `app/routes/auth.py`
- Create: `app/routes/tasks.py`
- Create: `app/routes/admin.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/templates/register.html`
- Create: `app/templates/upload.html`
- Create: `app/static/app.css`
- Create: `tests/conftest.py`
- Create: `tests/test_auth_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        openai_api_key="test-key",
        app_secret_key="test-secret",
        register_invite_code="invite-123",
        initial_admin_username="admin",
        initial_admin_password="admin-pass",
        data_dir=tmp_path,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    return TestClient(app)
```

Create `tests/test_auth_routes.py`:

```python
import re


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


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
    register_page = client.get("/register")
    csrf = _csrf(register_page.text)

    response = client.post(
        "/register",
        data={
            "username": "alice",
            "password": "secret123",
            "invite_code": "invite-123",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    tasks = client.get("/tasks")
    assert tasks.status_code == 200
    assert "历史任务" in tasks.text

    logout_page = client.post(
        "/logout",
        data={"csrf_token": _csrf(tasks.text)},
        follow_redirects=False,
    )
    assert logout_page.status_code == 303
```

- [ ] **Step 2: Run route tests and verify failure**

Run:

```bash
pytest tests/test_auth_routes.py -q
```

Expected: failure because `app.main` does not exist.

- [ ] **Step 3: Implement app factory**

Create `app/main.py`:

```python
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, load_settings
from app.db import connect, init_db
from app.repositories import count_active_admins, create_user
from app.security import hash_password, new_csrf_token


templates = Jinja2Templates(directory="app/templates")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(settings.db_path)
    init_db(conn)
    if count_active_admins(conn) == 0:
        create_user(
            conn,
            settings.initial_admin_username,
            hash_password(settings.initial_admin_password),
            "admin",
        )
    conn.close()

    app = FastAPI()
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_secret_key,
        https_only=settings.secure_cookies,
        same_site="lax",
        max_age=60 * 60 * 12,
    )

    from app.routes import admin, auth, tasks

    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(admin.router)
    return app


def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = new_csrf_token()
        request.session["csrf_token"] = token
    return token
```

- [ ] **Step 4: Implement auth routes**

Create `app/routes/__init__.py` as an empty package marker.

Create `app/routes/auth.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import connect
from app.main import ensure_csrf, templates
from app.repositories import create_user, get_user_by_username, mark_user_login
from app.security import CsrfError, hash_password, verify_csrf, verify_password


router = APIRouter()


def _conn(request: Request):
    return connect(request.app.state.settings.db_path)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": ensure_csrf(request), "error": None, "user": None},
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    try:
        verify_csrf(request.session, csrf_token)
    except CsrfError:
        return HTMLResponse("Invalid CSRF token", status_code=400)

    conn = _conn(request)
    user = get_user_by_username(conn, username.strip())
    if not user or user.status != "active" or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"csrf_token": ensure_csrf(request), "error": "用户名或密码错误", "user": None},
            status_code=400,
        )
    mark_user_login(conn, user.id)
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        request,
        "register.html",
        {"csrf_token": ensure_csrf(request), "error": None, "user": None},
    )


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    invite_code: str = Form(...),
    csrf_token: str = Form(...),
):
    try:
        verify_csrf(request.session, csrf_token)
    except CsrfError:
        return HTMLResponse("Invalid CSRF token", status_code=400)

    settings = request.app.state.settings
    if invite_code != settings.register_invite_code:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"csrf_token": ensure_csrf(request), "error": "邀请码错误", "user": None},
            status_code=400,
        )
    clean_username = username.strip()
    if len(clean_username) < 3 or len(password) < 8:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"csrf_token": ensure_csrf(request), "error": "用户名至少 3 位，密码至少 8 位", "user": None},
            status_code=400,
        )

    conn = _conn(request)
    if get_user_by_username(conn, clean_username):
        return templates.TemplateResponse(
            request,
            "register.html",
            {"csrf_token": ensure_csrf(request), "error": "用户名已存在", "user": None},
            status_code=400,
        )
    user = create_user(conn, clean_username, hash_password(password), "user")
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    try:
        verify_csrf(request.session, csrf_token)
    except CsrfError:
        return HTMLResponse("Invalid CSRF token", status_code=400)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 5: Create temporary task/admin route stubs**

Create `app/routes/admin.py`:

```python
from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/admin")
```

Create `app/routes/tasks.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import connect
from app.main import ensure_csrf, templates
from app.repositories import get_user_by_id
from app.security import ForbiddenError, require_login


router = APIRouter()


def _current_user(request: Request):
    conn = connect(request.app.state.settings.db_path)
    user_id = request.session.get("user_id")
    user = get_user_by_id(conn, int(user_id)) if user_id else None
    return require_login(user)


@router.get("/", response_class=HTMLResponse)
def upload_page(request: Request):
    try:
        user = _current_user(request)
    except ForbiddenError:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"user": user, "csrf_token": ensure_csrf(request), "error": None},
    )


@router.get("/tasks", response_class=HTMLResponse)
def task_list_stub(request: Request):
    try:
        user = _current_user(request)
    except ForbiddenError:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        "<!doctype html><html><body><h1>历史任务</h1></body></html>",
        status_code=200,
    )
```

- [ ] **Step 6: Create base templates and minimal CSS**

Create `app/templates/base.html`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title or "JM AI 设计审核" }}</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/">JM AI 设计审核</a>
    <nav>
      {% if user %}
        <a href="/tasks">历史任务</a>
        {% if user.role == "admin" %}<a href="/admin/users">用户管理</a>{% endif %}
        <form method="post" action="/logout" class="inline">
          <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
          <button type="submit">退出</button>
        </form>
      {% else %}
        <a href="/login">登录</a>
        <a href="/register">注册</a>
      {% endif %}
    </nav>
  </header>
  <main class="page">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

Create `app/templates/login.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel auth-panel">
  <h1>登录</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/login">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <label>用户名 <input name="username" required autocomplete="username"></label>
    <label>密码 <input name="password" type="password" required autocomplete="current-password"></label>
    <button type="submit">登录</button>
  </form>
</section>
{% endblock %}
```

Create `app/templates/register.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel auth-panel">
  <h1>注册</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/register">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <label>用户名 <input name="username" required autocomplete="username"></label>
    <label>密码 <input name="password" type="password" required autocomplete="new-password"></label>
    <label>邀请码 <input name="invite_code" required></label>
    <button type="submit">注册并登录</button>
  </form>
</section>
{% endblock %}
```

Create the temporary `app/templates/upload.html` used before Task 7 replaces the upload form:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h1>上传审核任务</h1>
  <p>上传功能将在任务模块接入。</p>
</section>
{% endblock %}
```

Create `app/static/app.css`:

```css
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #f7f7f9;
  color: #1f1f24;
  font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
}
.topbar {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e7e7eb;
}
.brand { color: #6B36FA; font-weight: 600; text-decoration: none; }
nav { display: flex; gap: 16px; align-items: center; }
nav a { color: #1f1f24; text-decoration: none; }
.page { max-width: 1180px; margin: 0 auto; padding: 32px 24px 56px; }
.panel { background: #fff; border: 1px solid #e7e7eb; border-radius: 8px; padding: 20px; }
.auth-panel { max-width: 420px; margin: 48px auto; }
form { display: grid; gap: 14px; }
form.inline { display: inline; }
label { display: grid; gap: 6px; color: #4b4b55; }
input, select {
  min-height: 38px;
  border: 1px solid #d8d8df;
  border-radius: 6px;
  padding: 8px 10px;
  font: inherit;
}
button {
  min-height: 38px;
  border: 0;
  border-radius: 6px;
  padding: 0 14px;
  background: #6B36FA;
  color: white;
  font-weight: 600;
  cursor: pointer;
}
.error { color: #d92d20; }
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/test_auth_routes.py tests/test_security.py tests/test_config_db.py -q
```

Expected: auth tests may need the regex CSRF extraction adjustment described in Step 1; after adjustment all tests pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add app/main.py app/routes app/templates app/static tests/conftest.py tests/test_auth_routes.py
git commit -m "feat: add auth routes and templates"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 5: Admin User Management

**Files:**
- Create: `app/routes/admin.py`
- Create: `app/templates/admin_users.html`
- Create: `tests/test_admin_users.py`
- Modify: `app/repositories.py`

- [ ] **Step 1: Add failing admin tests**

Create `tests/test_admin_users.py`:

```python
import re


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


def test_normal_user_cannot_open_admin_users(client):
    _register(client, "alice")
    response = client.get("/admin/users")

    assert response.status_code == 403


def test_admin_can_disable_and_enable_user(client):
    _register(client, "alice")
    client.post("/logout", data={"csrf_token": _csrf(client.get("/tasks").text)}, follow_redirects=False)

    page = client.get("/login")
    client.post(
        "/login",
        data={"username": "admin", "password": "admin-pass", "csrf_token": _csrf(page.text)},
        follow_redirects=False,
    )

    users_page = client.get("/admin/users")
    assert users_page.status_code == 200
    assert "alice" in users_page.text

    response = client.post(
        "/admin/users/alice/status",
        data={"status": "disabled", "csrf_token": _csrf(users_page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    client.post("/logout", data={"csrf_token": _csrf(client.get("/admin/users").text)}, follow_redirects=False)
    login_page = client.get("/login")
    failed_login = client.post(
        "/login",
        data={"username": "alice", "password": "secret123", "csrf_token": _csrf(login_page.text)},
    )
    assert "用户名或密码错误" in failed_login.text


def test_cannot_disable_last_active_admin(client):
    page = client.get("/login")
    client.post(
        "/login",
        data={"username": "admin", "password": "admin-pass", "csrf_token": _csrf(page.text)},
        follow_redirects=False,
    )
    users_page = client.get("/admin/users")

    response = client.post(
        "/admin/users/admin/status",
        data={"status": "disabled", "csrf_token": _csrf(users_page.text)},
    )

    assert response.status_code == 400
    assert "不能禁用最后一个管理员" in response.text
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_admin_users.py -q
```

Expected: failure because admin routes do not exist.

- [ ] **Step 3: Add repository helpers**

Append to `app/repositories.py`:

```python
def list_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute("select * from users order by created_at desc, id desc").fetchall()
    return [_user(row) for row in rows]


def get_user_required_by_username(conn: sqlite3.Connection, username: str) -> User:
    user = get_user_by_username(conn, username)
    if user is None:
        raise ValueError("user not found")
    return user
```

- [ ] **Step 4: Implement admin routes**

Create `app/routes/admin.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import connect
from app.main import ensure_csrf, templates
from app.repositories import (
    count_active_admins,
    get_user_by_id,
    get_user_required_by_username,
    list_users,
    set_user_password,
    set_user_role,
    set_user_status,
)
from app.security import CsrfError, ForbiddenError, hash_password, require_admin, verify_csrf


router = APIRouter(prefix="/admin")


def _current_admin(request: Request):
    conn = connect(request.app.state.settings.db_path)
    user_id = request.session.get("user_id")
    user = get_user_by_id(conn, int(user_id)) if user_id else None
    return require_admin(user), conn


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    try:
        user, conn = _current_admin(request)
    except ForbiddenError as exc:
        return HTMLResponse(str(exc), status_code=exc.status_code)
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"user": user, "users": list_users(conn), "csrf_token": ensure_csrf(request), "error": None},
    )


@router.post("/users/{username}/status")
def change_status(request: Request, username: str, status: str = Form(...), csrf_token: str = Form(...)):
    try:
        user, conn = _current_admin(request)
        verify_csrf(request.session, csrf_token)
    except (ForbiddenError, CsrfError) as exc:
        return HTMLResponse(str(exc), status_code=getattr(exc, "status_code", 400))

    target = get_user_required_by_username(conn, username)
    if target.role == "admin" and target.status == "active" and status == "disabled" and count_active_admins(conn) <= 1:
        return HTMLResponse("不能禁用最后一个管理员", status_code=400)
    if status not in {"active", "disabled"}:
        return HTMLResponse("Invalid status", status_code=400)
    set_user_status(conn, target.id, status)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{username}/role")
def change_role(request: Request, username: str, role: str = Form(...), csrf_token: str = Form(...)):
    try:
        user, conn = _current_admin(request)
        verify_csrf(request.session, csrf_token)
    except (ForbiddenError, CsrfError) as exc:
        return HTMLResponse(str(exc), status_code=getattr(exc, "status_code", 400))

    target = get_user_required_by_username(conn, username)
    if target.role == "admin" and role == "user" and target.status == "active" and count_active_admins(conn) <= 1:
        return HTMLResponse("不能降级最后一个管理员", status_code=400)
    if role not in {"admin", "user"}:
        return HTMLResponse("Invalid role", status_code=400)
    set_user_role(conn, target.id, role)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{username}/password")
def reset_password(request: Request, username: str, password: str = Form(...), csrf_token: str = Form(...)):
    try:
        user, conn = _current_admin(request)
        verify_csrf(request.session, csrf_token)
    except (ForbiddenError, CsrfError) as exc:
        return HTMLResponse(str(exc), status_code=getattr(exc, "status_code", 400))

    if len(password) < 8:
        return HTMLResponse("密码至少 8 位", status_code=400)
    target = get_user_required_by_username(conn, username)
    set_user_password(conn, target.id, hash_password(password))
    return RedirectResponse("/admin/users", status_code=303)
```

- [ ] **Step 5: Create admin template**

Create `app/templates/admin_users.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h1>用户管理</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <table>
    <thead>
      <tr><th>用户名</th><th>角色</th><th>状态</th><th>操作</th></tr>
    </thead>
    <tbody>
      {% for item in users %}
      <tr>
        <td>{{ item.username }}</td>
        <td>{{ item.role }}</td>
        <td>{{ item.status }}</td>
        <td class="actions">
          <form method="post" action="/admin/users/{{ item.username }}/status">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="hidden" name="status" value="{{ 'disabled' if item.status == 'active' else 'active' }}">
            <button type="submit">{{ "禁用" if item.status == "active" else "启用" }}</button>
          </form>
          <form method="post" action="/admin/users/{{ item.username }}/role">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="hidden" name="role" value="{{ 'user' if item.role == 'admin' else 'admin' }}">
            <button type="submit">{{ "降级" if item.role == "admin" else "提升管理员" }}</button>
          </form>
          <form method="post" action="/admin/users/{{ item.username }}/password">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input name="password" type="password" minlength="8" required placeholder="新密码">
            <button type="submit">重置密码</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
```

- [ ] **Step 6: Add table CSS**

Append to `app/static/app.css`:

```css
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { padding: 10px 12px; border-bottom: 1px solid #e7e7eb; text-align: left; vertical-align: top; }
th { background: #fafafa; font-weight: 600; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions form { display: flex; gap: 6px; align-items: center; }
.actions input { min-height: 32px; }
.actions button { min-height: 32px; }
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/test_admin_users.py tests/test_auth_routes.py tests/test_security.py tests/test_config_db.py -q
```

Expected: all tests pass after fixing any CSRF extraction mismatch in tests.

- [ ] **Step 8: Commit**

Run:

```bash
git add app/routes/admin.py app/templates/admin_users.html app/static/app.css app/repositories.py tests/test_admin_users.py
git commit -m "feat: add admin user management"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 6: Storage And Upload Validation

**Files:**
- Create: `app/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
from pathlib import Path

from app.config import Settings
from app.storage import (
    UploadValidationError,
    ensure_task_dirs,
    safe_artifact_path,
    save_upload_file,
    stored_image_name,
    validate_upload_batch,
)


class FakeUpload:
    def __init__(self, filename: str, content_type: str, size: int):
        self.filename = filename
        self.content_type = content_type
        self.size = size


def _settings(tmp_path):
    return Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
        max_upload_files=2,
        max_upload_mb_per_file=1,
    )


def test_validate_upload_batch_rejects_bad_type_and_count(tmp_path):
    settings = _settings(tmp_path)

    try:
        validate_upload_batch(settings, [FakeUpload("a.txt", "text/plain", 12)])
    except UploadValidationError as exc:
        assert "仅支持 PNG/JPG/JPEG/WEBP" in str(exc)
    else:
        raise AssertionError("text upload should be rejected")

    try:
        validate_upload_batch(
            settings,
            [
                FakeUpload("a.png", "image/png", 12),
                FakeUpload("b.png", "image/png", 12),
                FakeUpload("c.png", "image/png", 12),
            ],
        )
    except UploadValidationError as exc:
        assert "最多上传 2 张图片" in str(exc)
    else:
        raise AssertionError("too many files should be rejected")


def test_stored_image_name_ignores_user_filename():
    assert stored_image_name(0, "evil/../../x.png") == "image-001.png"
    assert stored_image_name(1, "mock.JPG") == "image-002.jpg"


def test_task_dirs_and_safe_artifact_paths(tmp_path):
    settings = _settings(tmp_path)
    dirs = ensure_task_dirs(settings, task_id=42)

    assert dirs.root == tmp_path / "uploads" / "42"
    assert dirs.originals.exists()
    assert dirs.artifacts.exists()

    assert safe_artifact_path(dirs, "artifacts/annotated.png") == dirs.artifacts / "annotated.png"

    try:
        safe_artifact_path(dirs, "../app.db")
    except UploadValidationError as exc:
        assert "非法文件路径" in str(exc)
    else:
        raise AssertionError("path traversal should fail")


def test_save_upload_file_enforces_size_limit(tmp_path):
    settings = _settings(tmp_path)
    output = tmp_path / "out.png"

    class FileObj:
        def read(self, size=-1):
            return b"x" * (settings.max_upload_mb_per_file * 1024 * 1024 + 1)

    try:
        save_upload_file(settings, FileObj(), output)
    except UploadValidationError as exc:
        assert "单张图片不能超过" in str(exc)
    else:
        raise AssertionError("oversized stream should fail")
```

- [ ] **Step 2: Run storage tests and verify failure**

Run:

```bash
pytest tests/test_storage.py -q
```

Expected: failure because `app.storage` does not exist.

- [ ] **Step 3: Implement storage module**

Create `app/storage.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


class UploadValidationError(Exception):
    pass


@dataclass(frozen=True)
class TaskDirs:
    root: Path
    originals: Path
    artifacts: Path
    report: Path


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def stored_image_name(index: int, original_filename: str) -> str:
    ext = _extension(original_filename)
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".png"
    return f"image-{index + 1:03d}{ext}"


def validate_upload_batch(settings: Settings, files: list) -> None:
    if not files:
        raise UploadValidationError("请至少上传 1 张图片")
    if len(files) > settings.max_upload_files:
        raise UploadValidationError(f"最多上传 {settings.max_upload_files} 张图片")

    max_bytes = settings.max_upload_mb_per_file * 1024 * 1024
    for file in files:
        ext = _extension(getattr(file, "filename", ""))
        content_type = getattr(file, "content_type", "")
        if ext not in ALLOWED_EXTENSIONS or content_type not in ALLOWED_CONTENT_TYPES:
            raise UploadValidationError("仅支持 PNG/JPG/JPEG/WEBP 图片")
        size = getattr(file, "size", None)
        if size is not None and size > max_bytes:
            raise UploadValidationError(f"单张图片不能超过 {settings.max_upload_mb_per_file}MB")


def save_upload_file(settings: Settings, file_obj, output_path: Path) -> None:
    max_bytes = settings.max_upload_mb_per_file * 1024 * 1024
    written = 0
    with output_path.open("wb") as out:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                output_path.unlink(missing_ok=True)
                raise UploadValidationError(f"单张图片不能超过 {settings.max_upload_mb_per_file}MB")
            out.write(chunk)


def ensure_task_dirs(settings: Settings, task_id: int) -> TaskDirs:
    root = settings.uploads_dir / str(task_id)
    originals = root / "originals"
    artifacts = root / "artifacts"
    originals.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    return TaskDirs(root=root, originals=originals, artifacts=artifacts, report=root / "report.html")


def relative_to_data(settings: Settings, path: Path) -> str:
    return path.resolve().relative_to(settings.data_dir.resolve()).as_posix()


def resolve_data_path(settings: Settings, relative_path: str) -> Path:
    candidate = (settings.data_dir / relative_path).resolve()
    root = settings.data_dir.resolve()
    if root not in candidate.parents and candidate != root:
        raise UploadValidationError("非法文件路径")
    return candidate


def safe_artifact_path(dirs: TaskDirs, relative_path: str) -> Path:
    candidate = (dirs.root / relative_path).resolve()
    if dirs.root.resolve() not in candidate.parents and candidate != dirs.root.resolve():
        raise UploadValidationError("非法文件路径")
    return candidate
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_storage.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add upload storage validation"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 7: Task Creation, List, Detail, And Permission Filtering

**Files:**
- Create: `app/routes/tasks.py`
- Create: `app/templates/tasks.html`
- Create: `app/templates/task_detail.html`
- Modify: `app/templates/upload.html`
- Modify: `app/repositories.py`
- Create: `tests/test_task_permissions.py`

- [ ] **Step 1: Write failing task permission tests**

Create `tests/test_task_permissions.py`:

```python
import re

from PIL import Image


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

    tasks_page = client.get("/tasks")
    assert "Alice audit" in tasks_page.text

    client.post("/logout", data={"csrf_token": _csrf(client.get("/tasks").text)}, follow_redirects=False)
    _register(client, "bob")
    bob_tasks = client.get("/tasks")
    assert "Alice audit" not in bob_tasks.text


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
    client.post("/logout", data={"csrf_token": _csrf(client.get("/tasks").text)}, follow_redirects=False)

    _register(client, "bob")
    forbidden = client.get(task_url)

    assert forbidden.status_code == 403
```

These tests run before Task 11 wires `run_task` into `BackgroundTasks`, so they do not call OpenAI.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_task_permissions.py -q
```

Expected: failure because task routes do not implement upload/list/detail.

- [ ] **Step 3: Add repository update helpers**

Append to `app/repositories.py`:

```python
def user_can_access_task(user: User, task: Task) -> bool:
    return user.is_admin or task.owner_id == user.id


def update_task_status(
    conn: sqlite3.Connection,
    task_id: int,
    status: str,
    summary: str | None = None,
    report_path: str | None = None,
    error_message: str | None = None,
) -> None:
    completed_sql = ", completed_at = current_timestamp" if status in {TASK_SUCCEEDED, TASK_FAILED} else ""
    conn.execute(
        f"""
        update tasks
        set status = ?, summary = coalesce(?, summary), report_path = coalesce(?, report_path),
            error_message = ?, updated_at = current_timestamp {completed_sql}
        where id = ?
        """,
        (status, summary, report_path, error_message, task_id),
    )
    conn.commit()


def update_task_image_status(
    conn: sqlite3.Connection,
    image_id: int,
    status: str,
    annotated_path: str | None = None,
    tokens_path: str | None = None,
    measurements_path: str | None = None,
    issues_path: str | None = None,
    audit_json_path: str | None = None,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        update task_images
        set status = ?, annotated_path = coalesce(?, annotated_path),
            tokens_path = coalesce(?, tokens_path),
            measurements_path = coalesce(?, measurements_path),
            issues_path = coalesce(?, issues_path),
            audit_json_path = coalesce(?, audit_json_path),
            error_message = ?
        where id = ?
        """,
        (status, annotated_path, tokens_path, measurements_path, issues_path, audit_json_path, error_message, image_id),
    )
    conn.commit()
```

- [ ] **Step 4: Implement task routes without runner integration**

Create `app/routes/tasks.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.db import connect
from app.main import ensure_csrf, templates
from app.repositories import (
    add_task_image,
    create_task,
    get_task_by_id,
    get_user_by_id,
    list_task_images,
    list_tasks_for_user,
    user_can_access_task,
)
from app.security import ForbiddenError, require_login, verify_csrf
from app.storage import ensure_task_dirs, relative_to_data, save_upload_file, stored_image_name, validate_upload_batch, UploadValidationError


router = APIRouter()


def _current_user_and_conn(request: Request):
    conn = connect(request.app.state.settings.db_path)
    user_id = request.session.get("user_id")
    user = get_user_by_id(conn, int(user_id)) if user_id else None
    return require_login(user), conn


@router.get("/", response_class=HTMLResponse)
def upload_page(request: Request):
    try:
        user, _ = _current_user_and_conn(request)
    except ForbiddenError:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"user": user, "csrf_token": ensure_csrf(request), "error": None},
    )


@router.post("/tasks")
async def create_task_route(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    csrf_token: str = Form(...),
    files: list[UploadFile] = File(...),
):
    try:
        user, conn = _current_user_and_conn(request)
        verify_csrf(request.session, csrf_token)
        validate_upload_batch(request.app.state.settings, files)
    except (ForbiddenError, UploadValidationError) as exc:
        status = getattr(exc, "status_code", 400)
        return HTMLResponse(str(exc), status_code=status)

    task = create_task(conn, owner_id=user.id, title=title.strip() or "未命名审核任务", image_count=len(files))
    dirs = ensure_task_dirs(request.app.state.settings, task.id)

    for index, file in enumerate(files):
        filename = stored_image_name(index, file.filename or "")
        output_path = dirs.originals / filename
        save_upload_file(request.app.state.settings, file.file, output_path)
        add_task_image(
            conn,
            task_id=task.id,
            filename=filename,
            original_path=relative_to_data(request.app.state.settings, output_path),
            sort_order=index,
        )

    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.get("/tasks", response_class=HTMLResponse)
def task_list(request: Request):
    try:
        user, conn = _current_user_and_conn(request)
    except ForbiddenError:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {"user": user, "csrf_token": ensure_csrf(request), "tasks": list_tasks_for_user(conn, user)},
    )


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int):
    try:
        user, conn = _current_user_and_conn(request)
    except ForbiddenError:
        return RedirectResponse("/login", status_code=303)
    task = get_task_by_id(conn, task_id)
    if not task or not user_can_access_task(user, task):
        return HTMLResponse("Forbidden", status_code=403)
    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "user": user,
            "csrf_token": ensure_csrf(request),
            "task": task,
            "images": list_task_images(conn, task.id),
        },
    )


@router.get("/tasks/{task_id}/status")
def task_status(request: Request, task_id: int):
    try:
        user, conn = _current_user_and_conn(request)
    except ForbiddenError:
        return JSONResponse({"error": "login required"}, status_code=401)
    task = get_task_by_id(conn, task_id)
    if not task or not user_can_access_task(user, task):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    images = list_task_images(conn, task.id)
    return {
        "id": task.id,
        "status": task.status,
        "summary": task.summary,
        "error_message": task.error_message,
        "images": [{"id": image.id, "filename": image.filename, "status": image.status} for image in images],
    }
```

- [ ] **Step 5: Create task templates**

Replace `app/templates/upload.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h1>上传审核任务</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/tasks" enctype="multipart/form-data">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <label>任务标题 <input name="title" required value="JM AI 设计审核"></label>
    <label>截图文件 <input name="files" type="file" accept=".png,.jpg,.jpeg,.webp" multiple required></label>
    <button type="submit">提交审核</button>
  </form>
</section>
{% endblock %}
```

Create `app/templates/tasks.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h1>历史任务</h1>
  <table>
    <thead>
      <tr><th>标题</th><th>提交人</th><th>图片数</th><th>状态</th><th>创建时间</th><th>报告</th></tr>
    </thead>
    <tbody>
      {% for task in tasks %}
      <tr>
        <td><a href="/tasks/{{ task.id }}">{{ task.title }}</a></td>
        <td>{{ task.owner_username or task.owner_id }}</td>
        <td>{{ task.image_count }}</td>
        <td>{{ task.status }}</td>
        <td>{{ task.created_at }}</td>
        <td>{% if task.report_path %}<a href="/tasks/{{ task.id }}/report.html">查看报告</a>{% else %}-{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
```

Create `app/templates/task_detail.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="panel" data-task-id="{{ task.id }}">
  <h1>{{ task.title }}</h1>
  <p>状态：<strong id="task-status">{{ task.status }}</strong></p>
  {% if task.summary %}<p>{{ task.summary }}</p>{% endif %}
  {% if task.error_message %}<p class="error">{{ task.error_message }}</p>{% endif %}
  {% if task.report_path %}<p><a href="/tasks/{{ task.id }}/report.html">查看 HTML 报告</a></p>{% endif %}
  <h2>图片</h2>
  <table>
    <thead><tr><th>文件</th><th>状态</th><th>错误</th></tr></thead>
    <tbody id="image-statuses">
      {% for image in images %}
      <tr><td>{{ image.filename }}</td><td>{{ image.status }}</td><td>{{ image.error_message or "" }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
</section>
<script src="/static/app.js"></script>
{% endblock %}
```

Create `app/static/app.js`:

```javascript
const detail = document.querySelector("[data-task-id]");
if (detail) {
  const taskId = detail.getAttribute("data-task-id");
  const poll = async () => {
    const response = await fetch(`/tasks/${taskId}/status`);
    if (!response.ok) return;
    const data = await response.json();
    const status = document.querySelector("#task-status");
    if (status) status.textContent = data.status;
    if (data.status === "queued" || data.status === "running") {
      window.setTimeout(poll, 2500);
    } else {
      window.location.reload();
    }
  };
  const current = document.querySelector("#task-status");
  if (current && (current.textContent === "queued" || current.textContent === "running")) {
    window.setTimeout(poll, 2500);
  }
}
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/test_task_permissions.py tests/test_admin_users.py tests/test_auth_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add app/routes/tasks.py app/templates/upload.html app/templates/tasks.html app/templates/task_detail.html app/static/app.js app/repositories.py tests/test_task_permissions.py
git commit -m "feat: add task upload and permission filtering"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 8: OpenAI Audit Adapter

**Files:**
- Create: `app/openai_audit.py`
- Create: `tests/test_openai_audit.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_openai_audit.py`:

```python
import json

from PIL import Image

from app.openai_audit import AuditModelError, build_audit_prompt, parse_audit_json


def test_build_audit_prompt_includes_spec_rules():
    prompt = build_audit_prompt("SPEC TEXT")

    assert "JM AI" in prompt
    assert "SPEC TEXT" in prompt
    assert "JSON" in prompt
    assert "bbox" in prompt


def test_parse_audit_json_accepts_minimal_valid_payload():
    payload = {
        "screen_context": "首页",
        "overall_conclusion": "整体基本符合",
        "major_issues": [],
        "passes": [],
        "issues": [],
        "sample_points": [],
        "regions": [],
        "distances": [],
        "checklist": [],
        "cannot_verify": [],
    }

    result = parse_audit_json(json.dumps(payload, ensure_ascii=False))

    assert result["screen_context"] == "首页"
    assert result["issues"] == []


def test_parse_audit_json_rejects_missing_required_key():
    try:
        parse_audit_json('{"screen_context":"x"}')
    except AuditModelError as exc:
        assert "overall_conclusion" in str(exc)
    else:
        raise AssertionError("missing keys should fail")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_openai_audit.py -q
```

Expected: failure because `app.openai_audit` does not exist.

- [ ] **Step 3: Implement adapter schema and parsing**

Create `app/openai_audit.py`:

```python
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from openai import OpenAI


REQUIRED_KEYS = {
    "screen_context",
    "overall_conclusion",
    "major_issues",
    "passes",
    "issues",
    "sample_points",
    "regions",
    "distances",
    "checklist",
    "cannot_verify",
}


class AuditModelError(Exception):
    pass


def build_audit_prompt(spec_text: str) -> str:
    return (
        "你是 JM AI 设计规范审核助手。必须根据下面的 JM AI 规范审核图片。"
        "输出必须是 JSON，字段必须完整。证据和推断要分开，无法确认的项目放入 cannot_verify。"
        "问题 bbox 使用 [x, y, w, h] 截图像素坐标；无法可靠定位时 bbox 为 null。"
        "\\n\\nJM AI SPEC:\\n"
        f"{spec_text}"
    )


def audit_json_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "jm_ai_image_audit",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(REQUIRED_KEYS),
            "properties": {
                "screen_context": {"type": "string"},
                "overall_conclusion": {"type": "string"},
                "major_issues": {"type": "array", "items": {"type": "string"}},
                "passes": {"type": "array", "items": {"type": "string"}},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "id",
                            "category",
                            "severity",
                            "location",
                            "current_observation",
                            "spec_expectation",
                            "recommendation",
                            "confidence",
                            "bbox",
                        ],
                        "properties": {
                            "id": {"type": "string"},
                            "category": {"type": "string"},
                            "severity": {"type": "string", "enum": ["高", "中", "低"]},
                            "location": {"type": "string"},
                            "current_observation": {"type": "string"},
                            "spec_expectation": {"type": "string"},
                            "recommendation": {"type": "string"},
                            "confidence": {"type": "number"},
                            "bbox": {
                                "anyOf": [
                                    {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                                    {"type": "null"},
                                ]
                            },
                        },
                    },
                },
                "sample_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["label", "x", "y"],
                        "properties": {
                            "label": {"type": "string"},
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                        },
                    },
                },
                "regions": {"type": "array", "items": {"type": "object"}},
                "distances": {"type": "array", "items": {"type": "object"}},
                "checklist": {"type": "array", "items": {"type": "object"}},
                "cannot_verify": {"type": "array", "items": {"type": "object"}},
            },
        },
    }


def parse_audit_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuditModelError("模型返回的 JSON 无法解析") from exc
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise AuditModelError(f"模型返回缺少字段: {', '.join(sorted(missing))}")
    return data


def image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    media_type = "image/png"
    if suffix in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif suffix == ".webp":
        media_type = "image/webp"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def audit_image(client: OpenAI, model: str, image_path: Path, spec_text: str) -> dict[str, Any]:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": build_audit_prompt(spec_text)},
                    {"type": "input_image", "image_url": image_data_url(image_path), "detail": "high"},
                ],
            }
        ],
        text={"format": audit_json_schema()},
    )
    return parse_audit_json(response.output_text)
```

- [ ] **Step 4: Run adapter tests**

Run:

```bash
pytest tests/test_openai_audit.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/openai_audit.py tests/test_openai_audit.py
git commit -m "feat: add OpenAI audit adapter"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 9: Evidence Tool Wrappers

**Files:**
- Create: `app/evidence_tools.py`
- Create: `tests/test_evidence_tools.py`

- [ ] **Step 1: Write failing evidence tests**

Create `tests/test_evidence_tools.py`:

```python
import json

from PIL import Image

from app.evidence_tools import build_issues_json, write_regions_json, run_color_analysis


def test_build_issues_json_keeps_only_issues_with_bbox():
    issues = [
        {"id": "color-01", "title": "颜色错误", "severity": "中", "category": "色彩", "bbox": [1, 2, 3, 4]},
        {"id": "text-01", "title": "字体偏小", "severity": "低", "category": "字体", "bbox": None},
    ]

    result = build_issues_json(issues)

    assert result == [
        {"id": "color-01", "title": "颜色错误", "severity": "中", "category": "色彩", "bbox": [1, 2, 3, 4]}
    ]


def test_write_regions_json(tmp_path):
    path = tmp_path / "regions.json"
    write_regions_json(path, [{"id": "a", "bbox": [0, 0, 10, 10]}], [{"id": "gap", "from": "a", "to": "a", "axis": "x"}])

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["regions"][0]["id"] == "a"
    assert data["distances"][0]["id"] == "gap"


def test_run_color_analysis_creates_tokens_json(tmp_path):
    image = tmp_path / "input.png"
    Image.new("RGB", (20, 20), color=(107, 54, 250)).save(image)
    output = tmp_path / "tokens.json"

    run_color_analysis(image, output, [{"label": "center", "x": 10, "y": 10}])

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["image_size_px"]["width"] == 20
    assert data["samples"][0]["label"] == "center"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_evidence_tools.py -q
```

Expected: failure because `app.evidence_tools` does not exist.

- [ ] **Step 3: Implement wrappers**

Create `app/evidence_tools.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


class EvidenceToolError(Exception):
    pass


def _run(args: list[str]) -> None:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "evidence tool failed"
        raise EvidenceToolError(message)


def build_issues_json(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for issue in issues:
        bbox = issue.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            continue
        output.append(
            {
                "id": str(issue.get("id", "issue")),
                "title": str(issue.get("title") or issue.get("current_observation") or issue.get("id")),
                "severity": str(issue.get("severity") or "中"),
                "category": str(issue.get("category") or "其他"),
                "bbox": bbox,
            }
        )
    return output


def write_regions_json(path: Path, regions: list[dict[str, Any]], distances: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"regions": regions, "distances": distances}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_color_analysis(image_path: Path, output_path: Path, sample_points: list[dict[str, Any]]) -> None:
    args = [sys.executable, "scripts/analyze_image_tokens.py", str(image_path), "--output", str(output_path)]
    for point in sample_points:
        args.extend(["--sample", f"{point['label']}:{point['x']}:{point['y']}"])
    _run(args)


def run_measurements(image_path: Path, regions_path: Path, output_path: Path, crop_dir: Path) -> None:
    _run(
        [
            sys.executable,
            "scripts/measure_regions.py",
            str(image_path),
            str(regions_path),
            "--output",
            str(output_path),
            "--crop-dir",
            str(crop_dir),
        ]
    )


def run_annotations(image_path: Path, issues_path: Path, output_dir: Path) -> None:
    _run([sys.executable, "scripts/annotate_issues.py", str(image_path), str(issues_path), str(output_dir)])
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_evidence_tools.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/evidence_tools.py tests/test_evidence_tools.py
git commit -m "feat: wrap audit evidence scripts"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 10: Aggregate HTML Report Renderer

**Files:**
- Create: `app/report_renderer.py`
- Create: `tests/test_report_renderer.py`

- [ ] **Step 1: Write failing renderer tests**

Create `tests/test_report_renderer.py`:

```python
from app.report_renderer import render_report_html


def test_render_report_html_escapes_user_text_and_includes_image_sections():
    html = render_report_html(
        task={"title": "<script>alert(1)</script>", "summary": "部分图片存在问题"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": {
                    "screen_context": "首页",
                    "overall_conclusion": "基本符合",
                    "major_issues": ["中：按钮颜色偏差"],
                    "passes": ["字号层级清晰"],
                    "issues": [
                        {
                            "id": "color-01",
                            "severity": "中",
                            "category": "色彩",
                            "location": "主按钮",
                            "current_observation": "偏蓝",
                            "spec_expectation": "应使用 #6B36FA",
                            "recommendation": "改为 JM AI 主色",
                            "confidence": 0.9,
                            "bbox": [1, 2, 3, 4],
                        }
                    ],
                    "checklist": [{"item": "AI 主色", "status": "不通过", "note": "偏蓝"}],
                    "cannot_verify": [],
                },
                "artifacts": {"annotated": "artifacts/image-001/annotated.png", "tokens": "artifacts/image-001/tokens.json"},
            }
        ],
    )

    assert "<script>" not in html
    assert "JM AI 设计规范审核报告" in html
    assert "image-001.png" in html
    assert "按钮颜色偏差" in html
    assert "artifacts/image-001/annotated.png" in html
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_report_renderer.py -q
```

Expected: failure because `app.report_renderer` does not exist.

- [ ] **Step 3: Implement report renderer**

Create `app/report_renderer.py`:

```python
from __future__ import annotations

from html import escape
from typing import Any


def _li(items: list[str]) -> str:
    if not items:
        return "<p class='meta'>无</p>"
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def _issues_table(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "<p class='meta'>未发现明确问题。</p>"
    rows = []
    for issue in issues:
        rows.append(
            "<tr>"
            f"<td>{escape(str(issue.get('severity', '')))}</td>"
            f"<td>{escape(str(issue.get('category', '')))}</td>"
            f"<td>{escape(str(issue.get('location', '')))}</td>"
            f"<td>{escape(str(issue.get('current_observation', '')))}</td>"
            f"<td>{escape(str(issue.get('spec_expectation', '')))}</td>"
            f"<td>{escape(str(issue.get('recommendation', '')))}</td>"
            f"<td>{escape(str(issue.get('confidence', '')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>优先级</th><th>分类</th><th>位置</th><th>当前表现</th>"
        "<th>规范要求</th><th>修改建议</th><th>置信度</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _checklist_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p class='meta'>无</p>"
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('item', '')))}</td>"
            f"<td>{escape(str(item.get('status', '')))}</td>"
            f"<td>{escape(str(item.get('note', '')))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>检查项</th><th>状态</th><th>说明</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def render_report_html(task: dict[str, Any], image_results: list[dict[str, Any]], task_id: int | None = None) -> str:
    def artifact_url(path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith("/"):
            return path
        if task_id is None:
            return path
        prefix = f"uploads/{task_id}/"
        normalized = path[len(prefix):] if path.startswith(prefix) else path
        return f"/artifacts/{task_id}/{normalized}"

    sections = []
    for index, result in enumerate(image_results, start=1):
        audit = result["audit"]
        artifacts = result.get("artifacts", {})
        annotated = artifact_url(artifacts.get("annotated"))
        tokens = artifact_url(artifacts.get("tokens"))
        measurements = artifact_url(artifacts.get("measurements"))
        screenshot_html = (
            f"<figure><img src='{escape(annotated)}' alt='标注图'><figcaption>标注图</figcaption></figure>"
            if annotated
            else "<p class='meta'>本图没有可生成的标注截图。</p>"
        )
        sections.append(
            f"""
            <section class="card">
              <h2>{index}. {escape(result['filename'])}</h2>
              <p class="meta">页面识别：{escape(str(audit.get('screen_context', '')))}</p>
              <p>{escape(str(audit.get('overall_conclusion', '')))}</p>
              <h3>主要问题</h3>
              {_li([str(item) for item in audit.get('major_issues', [])])}
              <h3>问题截图</h3>
              <div class="screenshots">{screenshot_html}</div>
              <h3>详细问题清单</h3>
              {_issues_table(audit.get('issues', []))}
              <h3>符合规范的点</h3>
              {_li([str(item) for item in audit.get('passes', [])])}
              <h3>研发/验收 Checklist</h3>
              {_checklist_table(audit.get('checklist', []))}
              <h3>测量证据</h3>
              <p>{escape(str(tokens or ''))} {escape(str(measurements or ''))}</p>
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JM AI 设计规范审核报告</title>
  <style>
    body {{ margin: 0; background: #f7f7f9; color: #1f1f24; font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 24px 56px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 40px; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; line-height: 30px; }}
    h3 {{ margin: 24px 0 8px; font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e7e7eb; text-align: left; vertical-align: top; }}
    th {{ background: #fafafa; }}
    .summary, .card {{ background: #fff; border: 1px solid #e7e7eb; border-radius: 8px; padding: 16px; margin-top: 16px; }}
    .meta {{ color: #767680; }}
    .screenshots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    figure {{ margin: 0; border: 1px solid #e7e7eb; border-radius: 8px; overflow: hidden; }}
    figure img {{ display: block; width: 100%; height: auto; }}
    figcaption {{ padding: 10px 12px; color: #767680; }}
  </style>
</head>
<body>
  <main>
    <h1>JM AI 设计规范审核报告</h1>
    <section class="summary">
      <p>任务：{escape(str(task.get('title', '')))}</p>
      <p>{escape(str(task.get('summary', '')))}</p>
    </section>
    {''.join(sections)}
  </main>
</body>
</html>"""
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_report_renderer.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/report_renderer.py tests/test_report_renderer.py
git commit -m "feat: render aggregate audit report"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 11: Task Runner Integration

**Files:**
- Create: `app/task_runner.py`
- Create: `tests/test_task_runner.py`
- Modify: `app/routes/tasks.py`

- [ ] **Step 1: Write failing task runner test with fake auditor**

Create `tests/test_task_runner.py`:

```python
from PIL import Image

from app.config import Settings
from app.db import connect, init_db
from app.repositories import create_task, create_user, add_task_image, get_task_by_id, list_task_images
from app.security import hash_password
from app.storage import ensure_task_dirs, relative_to_data
from app.task_runner import run_task


def test_run_task_generates_report_for_successful_images(tmp_path):
    settings = Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
    )
    conn = connect(settings.db_path)
    init_db(conn)
    user = create_user(conn, "alice", hash_password("secret123"), "user")
    task = create_task(conn, user.id, "Audit", 1)
    dirs = ensure_task_dirs(settings, task.id)
    image_path = dirs.originals / "image-001.png"
    Image.new("RGB", (20, 20), color=(107, 54, 250)).save(image_path)
    add_task_image(conn, task.id, "image-001.png", relative_to_data(settings, image_path), 0)

    def fake_auditor(path):
        return {
            "screen_context": "测试页",
            "overall_conclusion": "基本符合",
            "major_issues": [],
            "passes": ["主色接近规范"],
            "issues": [],
            "sample_points": [{"label": "center", "x": 10, "y": 10}],
            "regions": [],
            "distances": [],
            "checklist": [{"item": "AI 主色", "status": "通过", "note": ""}],
            "cannot_verify": [],
        }

    run_task(settings, task.id, auditor=fake_auditor)

    refreshed = get_task_by_id(conn, task.id)
    images = list_task_images(conn, task.id)

    assert refreshed.status == "succeeded"
    assert refreshed.report_path == "uploads/1/report.html"
    assert (tmp_path / refreshed.report_path).exists()
    assert images[0].status == "succeeded"
    assert images[0].tokens_path.endswith("tokens.json")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_task_runner.py -q
```

Expected: failure because `task_runner.py` does not exist.

- [ ] **Step 3: Implement runner**

Create `app/task_runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from app.config import Settings
from app.db import connect
from app.evidence_tools import (
    build_issues_json,
    run_annotations,
    run_color_analysis,
    run_measurements,
    write_regions_json,
)
from app.models import TASK_FAILED, TASK_RUNNING, TASK_SUCCEEDED
from app.openai_audit import audit_image
from app.report_renderer import render_report_html
from app.repositories import (
    get_task_by_id,
    list_task_images,
    update_task_image_status,
    update_task_status,
)
from app.storage import ensure_task_dirs, relative_to_data, resolve_data_path


def _default_auditor(settings: Settings) -> Callable[[Path], dict[str, Any]]:
    spec_text = Path("references/jm-ai-design-spec.md").read_text(encoding="utf-8")
    client = OpenAI(api_key=settings.openai_api_key)
    return lambda image_path: audit_image(client, settings.openai_audit_model, image_path, spec_text)


def run_task(settings: Settings, task_id: int, auditor: Callable[[Path], dict[str, Any]] | None = None) -> None:
    conn = connect(settings.db_path)
    task = get_task_by_id(conn, task_id)
    if task is None:
        return
    update_task_status(conn, task_id, TASK_RUNNING, error_message=None)
    dirs = ensure_task_dirs(settings, task_id)
    auditor = auditor or _default_auditor(settings)

    image_results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    for image in list_task_images(conn, task_id):
        update_task_image_status(conn, image.id, TASK_RUNNING, error_message=None)
        image_path = resolve_data_path(settings, image.original_path)
        image_artifacts = dirs.artifacts / image.filename.rsplit(".", 1)[0]
        image_artifacts.mkdir(parents=True, exist_ok=True)
        try:
            audit = auditor(image_path)
            audit_path = image_artifacts / "audit.json"
            tokens_path = image_artifacts / "tokens.json"
            regions_path = image_artifacts / "regions.json"
            measurements_path = image_artifacts / "measurements.json"
            issues_path = image_artifacts / "issues.json"
            crop_dir = image_artifacts / "region-crops"

            audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            run_color_analysis(image_path, tokens_path, audit.get("sample_points", []))
            write_regions_json(regions_path, audit.get("regions", []), audit.get("distances", []))
            run_measurements(image_path, regions_path, measurements_path, crop_dir)

            issues_for_screenshots = build_issues_json(audit.get("issues", []))
            issues_path.write_text(json.dumps(issues_for_screenshots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            annotated_path = None
            if issues_for_screenshots:
                run_annotations(image_path, issues_path, image_artifacts)
                annotated_path = image_artifacts / "annotated.png"

            update_task_image_status(
                conn,
                image.id,
                TASK_SUCCEEDED,
                annotated_path=relative_to_data(settings, annotated_path) if annotated_path else None,
                tokens_path=relative_to_data(settings, tokens_path),
                measurements_path=relative_to_data(settings, measurements_path),
                issues_path=relative_to_data(settings, issues_path),
                audit_json_path=relative_to_data(settings, audit_path),
                error_message=None,
            )
            image_results.append(
                {
                    "filename": image.filename,
                    "audit": audit,
                    "artifacts": {
                        "annotated": relative_to_data(settings, annotated_path) if annotated_path else None,
                        "tokens": relative_to_data(settings, tokens_path),
                        "measurements": relative_to_data(settings, measurements_path),
                    },
                }
            )
            success_count += 1
        except Exception as exc:
            failure_count += 1
            update_task_image_status(conn, image.id, TASK_FAILED, error_message=str(exc)[:500])

    if success_count:
        summary = "审核完成" if failure_count == 0 else f"部分图片审核失败：成功 {success_count} 张，失败 {failure_count} 张"
        html = render_report_html({"title": task.title, "summary": summary}, image_results, task_id=task_id)
        dirs.report.write_text(html, encoding="utf-8")
        update_task_status(conn, task_id, TASK_SUCCEEDED, summary=summary, report_path=relative_to_data(settings, dirs.report), error_message=None)
    else:
        update_task_status(conn, task_id, TASK_FAILED, summary=None, report_path=None, error_message="全部图片审核失败")
```

- [ ] **Step 4: Connect upload route to background runner**

In `app/routes/tasks.py`, import and enqueue the runner:

```python
from app.task_runner import run_task
```

After all images are saved in `create_task_route`, before returning the redirect, add:

```python
background_tasks.add_task(run_task, request.app.state.settings, task.id)
```

- [ ] **Step 5: Run runner tests**

Run:

```bash
pytest tests/test_task_runner.py tests/test_task_permissions.py tests/test_report_renderer.py tests/test_evidence_tools.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add app/task_runner.py app/routes/tasks.py tests/test_task_runner.py
git commit -m "feat: run multi-image audit tasks"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 12: Permission-Checked Report And Artifact Serving

**Files:**
- Modify: `app/routes/tasks.py`
- Create: `tests/test_artifact_access.py`

- [ ] **Step 1: Write failing artifact access tests**

Create `tests/test_artifact_access.py`:

```python
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
        data={"username": username, "password": password, "csrf_token": _csrf(page.text)},
        follow_redirects=False,
    )


def test_report_requires_task_permission(client, settings):
    conn = connect(settings.db_path)
    alice = create_user(conn, "alice", hash_password("secret123"), "user")
    bob = create_user(conn, "bob", hash_password("secret123"), "user")
    task = create_task(conn, alice.id, "Private report", 1)
    dirs = ensure_task_dirs(settings, task.id)
    dirs.report.write_text("<html>private</html>", encoding="utf-8")
    update_task_status(conn, task.id, "succeeded", report_path=relative_to_data(settings, dirs.report))

    _login(client, "bob", "secret123")
    forbidden = client.get(f"/tasks/{task.id}/report.html")
    assert forbidden.status_code == 403

    client.post("/logout", data={"csrf_token": _csrf(client.get("/tasks").text)}, follow_redirects=False)
    _login(client, "alice", "secret123")
    allowed = client.get(f"/tasks/{task.id}/report.html")
    assert allowed.status_code == 200
    assert "private" in allowed.text


def test_artifact_path_traversal_is_rejected(client, settings):
    conn = connect(settings.db_path)
    alice = create_user(conn, "alice", hash_password("secret123"), "user")
    task = create_task(conn, alice.id, "Private report", 1)
    _login(client, "alice", "secret123")

    response = client.get(f"/artifacts/{task.id}/../app.db")
    assert response.status_code in {400, 404}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_artifact_access.py -q
```

Expected: failure because report/artifact routes do not exist.

- [ ] **Step 3: Add routes**

Append to `app/routes/tasks.py`:

```python
from fastapi.responses import FileResponse
from app.storage import safe_artifact_path, resolve_data_path


def _authorized_task_or_response(request: Request, task_id: int):
    try:
        user, conn = _current_user_and_conn(request)
    except ForbiddenError:
        return None, HTMLResponse("Login required", status_code=401)
    task = get_task_by_id(conn, task_id)
    if not task or not user_can_access_task(user, task):
        return None, HTMLResponse("Forbidden", status_code=403)
    return task, None


@router.get("/tasks/{task_id}/report.html")
def report_html(request: Request, task_id: int):
    task, response = _authorized_task_or_response(request, task_id)
    if response:
        return response
    if not task.report_path:
        return HTMLResponse("Report not ready", status_code=404)
    path = resolve_data_path(request.app.state.settings, task.report_path)
    if not path.exists():
        return HTMLResponse("Report not found", status_code=404)
    return FileResponse(path, media_type="text/html; charset=utf-8")


@router.get("/artifacts/{task_id}/{artifact_path:path}")
def artifact_file(request: Request, task_id: int, artifact_path: str):
    task, response = _authorized_task_or_response(request, task_id)
    if response:
        return response
    dirs = ensure_task_dirs(request.app.state.settings, task_id)
    try:
        path = safe_artifact_path(dirs, artifact_path)
    except UploadValidationError:
        return HTMLResponse("非法文件路径", status_code=400)
    if not path.exists() or not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path)
```

- [ ] **Step 4: Run artifact tests**

Run:

```bash
pytest tests/test_artifact_access.py tests/test_task_permissions.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/routes/tasks.py tests/test_artifact_access.py
git commit -m "feat: protect reports and artifacts"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

---

### Task 13: README, Manual Run, And Final Verification

**Files:**
- Create: `README.md`
- Modify: files only if verification exposes a real defect.

- [ ] **Step 1: Create README**

Create `README.md`:

```markdown
# JM AI Design Web App

Single-port FastAPI app for JM AI design-spec screenshot audits.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Required Environment

```bash
export OPENAI_API_KEY="..."
export APP_SECRET_KEY="change-me"
export REGISTER_INVITE_CODE="invite-code"
export INITIAL_ADMIN_USERNAME="admin"
export INITIAL_ADMIN_PASSWORD="change-me-password"
export DATA_DIR="$(pwd)/data"
export OPENAI_AUDIT_MODEL="gpt-4.1-mini"
```

## Run

```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://localhost:8000`.

## Test

```bash
pytest -q
```

## Storage

SQLite lives at `data/app.db`. Uploaded originals and generated reports live under `data/uploads/<task_id>/`.
Back up both `data/app.db` and `data/uploads`.
```

- [ ] **Step 2: Install dependencies if needed**

Run:

```bash
python -m pip install -e ".[dev]"
```

Expected: dependencies install successfully. If network is blocked by sandboxing, rerun with escalated permission as required by the environment.

- [ ] **Step 3: Run full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass. If a test fails, fix the smallest implementation defect and rerun the exact failing test before rerunning the full suite.

- [ ] **Step 4: Start the single-port app**

Run:

```bash
OPENAI_API_KEY=test-key \
APP_SECRET_KEY=test-secret \
REGISTER_INVITE_CODE=invite-123 \
INITIAL_ADMIN_USERNAME=admin \
INITIAL_ADMIN_PASSWORD=admin-pass \
DATA_DIR="$(pwd)/data-dev" \
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Expected: FastAPI starts on `http://127.0.0.1:8000`.

- [ ] **Step 5: Manual smoke**

In a browser:

1. Open `/register`.
2. Register with invite code `invite-123`.
3. Open `/`.
4. Upload two `.png` screenshots.
5. Confirm redirect to `/tasks/{id}`.
6. Confirm task reaches `succeeded` when OpenAI credentials are valid.
7. Confirm `/tasks/{id}/report.html` opens.
8. Log in as `admin`.
9. Confirm `/tasks` shows all tasks and `/admin/users` shows users.

- [ ] **Step 6: Commit README and verification fixes**

Run:

```bash
git add README.md
git commit -m "docs: add web app setup guide"
```

Expected if git exists: commit succeeds. Expected in the current directory: `fatal: not a git repository`; record `commit skipped: not a git repository`.

## Self-Review Checklist

- Spec coverage:
  - Multi-image upload: Task 7.
  - OpenAI vision audit: Task 8.
  - Evidence generation: Task 9 and Task 11.
  - Aggregate HTML report: Task 10 and Task 11.
  - History tasks: Task 7.
  - Admin/user report visibility: Task 7 and Task 12.
  - Self-registration with invite code: Task 4.
  - Admin user management: Task 5.
  - SQLite and local file storage: Task 2 and Task 6.
  - Single-port FastAPI deployment: Task 4 and Task 13.
- Placeholder scan:
  - No unresolved `TBD`, `TODO`, or intentionally blank implementation steps.
- Type consistency:
  - `User`, `Task`, and `TaskImage` dataclasses match repository return values.
  - Task statuses use `queued`, `running`, `succeeded`, `failed`.
  - User roles use `admin`, `user`.
  - Artifact paths flow through `storage.py` helpers.
