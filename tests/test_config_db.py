import sqlite3
from pathlib import Path

from app.config import Settings, load_settings
from app.db import SCHEMA_VERSION, connect, init_db
from app.repositories import (
    add_task_image,
    count_active_admins,
    create_task,
    create_user,
    get_task_by_id,
    list_task_images,
    list_tasks_for_user,
    mark_successful_task_reports_read_for_user,
    mark_task_report_read,
    mark_user_login,
    update_task_status,
)
from app.models import TASK_SUCCEEDED


REQUIRED_ENV = [
    "OPENAI_API_KEY",
    "APP_SECRET_KEY",
    "REGISTER_INVITE_CODE",
    "INITIAL_ADMIN_USERNAME",
    "INITIAL_ADMIN_PASSWORD",
]

OPTIONAL_ENV = [
    "AUDIT_MODEL_PROVIDER",
    "MAX_UPLOAD_FILES",
    "MAX_UPLOAD_MB_PER_FILE",
    "OPENAI_AUDIT_MODEL",
    "OPENAI_REASONING_EFFORT",
    "OPENAI_TIMEOUT_SECONDS",
    "JDCLOUD_OPENAI_API_KEY",
    "JDCLOUD_OPENAI_BASE_URL",
    "JDCLOUD_OPENAI_AUDIT_MODEL",
    "JDCLOUD_OPENAI_REASONING_EFFORT",
    "JDCLOUD_OPENAI_TIMEOUT_SECONDS",
    "SUPERAPI_OPENAI_API_KEY",
    "SUPERAPI_OPENAI_BASE_URL",
    "SUPERAPI_OPENAI_AUDIT_MODEL",
    "SUPERAPI_OPENAI_REASONING_EFFORT",
    "SUPERAPI_OPENAI_TIMEOUT_SECONDS",
    "SECURE_COOKIES",
    "DATA_DIR",
    "OPENAI_BASE_URL",
]

ALL_ENV = REQUIRED_ENV + OPTIONAL_ENV


def _set_required_env(monkeypatch, tmp_path):
    for key in OPTIONAL_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("APP_SECRET_KEY", "secret")
    monkeypatch.setenv("REGISTER_INVITE_CODE", "invite")
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "password123")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.PROJECT_ROOT", tmp_path / "project")


def _clear_settings_env(monkeypatch):
    for key in ALL_ENV:
        monkeypatch.delenv(key, raising=False)


def test_settings_uses_defaults_for_limits(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)

    settings = load_settings()

    assert settings.max_upload_files == 8
    assert settings.max_upload_mb_per_file == 10
    assert settings.audit_model_provider == "openai"
    assert settings.openai_audit_model == "gpt-4.1-mini"
    assert settings.openai_timeout_seconds == 180
    assert settings.data_dir == tmp_path


def test_settings_loads_dotenv_file(tmp_path, monkeypatch):
    _clear_settings_env(monkeypatch)
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("app.config.PROJECT_ROOT", project_root)
    env_path = project_root / ".env"
    data_dir = tmp_path / "data"
    monkeypatch.chdir(tmp_path)
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=env-file-key",
                "OPENAI_BASE_URL=https://llm.example.com/v1",
                "APP_SECRET_KEY=secret",
                "REGISTER_INVITE_CODE=invite",
                "INITIAL_ADMIN_USERNAME=admin",
                "INITIAL_ADMIN_PASSWORD=password123",
                f"DATA_DIR={data_dir}",
                "AUDIT_MODEL_PROVIDER=jdcloud",
                "OPENAI_AUDIT_MODEL=vision-model",
                "OPENAI_REASONING_EFFORT=xhigh",
                "OPENAI_TIMEOUT_SECONDS=45",
                "JDCLOUD_OPENAI_API_KEY=jd-key",
                "JDCLOUD_OPENAI_BASE_URL=https://modelservice.jdcloud.com/v1/",
                "JDCLOUD_OPENAI_AUDIT_MODEL=Kimi-K2.6",
                "JDCLOUD_OPENAI_REASONING_EFFORT=",
                "JDCLOUD_OPENAI_TIMEOUT_SECONDS=60",
                "SECURE_COOKIES=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.openai_api_key == "env-file-key"
    assert settings.openai_base_url == "https://llm.example.com/v1"
    assert settings.openai_audit_model == "vision-model"
    assert settings.openai_reasoning_effort == "xhigh"
    assert settings.openai_timeout_seconds == 45
    assert settings.audit_model_provider == "jdcloud"
    assert settings.audit_api_key == "jd-key"
    assert settings.audit_base_url == "https://modelservice.jdcloud.com/v1/"
    assert settings.audit_model == "Kimi-K2.6"
    assert settings.audit_reasoning_effort is None
    assert settings.audit_timeout_seconds == 60
    assert settings.data_dir == data_dir
    assert settings.secure_cookies is True


def test_real_environment_overrides_dotenv_file(tmp_path, monkeypatch):
    _clear_settings_env(monkeypatch)
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("app.config.PROJECT_ROOT", project_root)
    env_path = project_root / ".env"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "real-env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://real-env.example.com/v1")
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=env-file-key",
                "OPENAI_BASE_URL=https://env-file.example.com/v1",
                "APP_SECRET_KEY=secret",
                "REGISTER_INVITE_CODE=invite",
                "INITIAL_ADMIN_USERNAME=admin",
                "INITIAL_ADMIN_PASSWORD=password123",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.openai_api_key == "real-env-key"
    assert settings.openai_base_url == "https://real-env.example.com/v1"


def test_settings_rejects_missing_required_env(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)

    try:
        load_settings()
    except RuntimeError as exc:
        message = str(exc)
        for key in REQUIRED_ENV:
            assert key in message
    else:
        raise AssertionError("load_settings should fail when required env vars are missing")


def test_settings_rejects_blank_required_env(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_SECRET_KEY", "   ")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "APP_SECRET_KEY" in str(exc)
    else:
        raise AssertionError("load_settings should fail when required env vars are blank")


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


def test_settings_uses_default_data_dir_when_env_is_blank(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DATA_DIR", "   ")

    settings = load_settings()

    assert settings.data_dir == Path("data").resolve()


def test_settings_parses_secure_cookies_explicit_values(tmp_path, monkeypatch):
    true_values = ["true", "1", "yes", "on", " TRUE "]
    false_values = ["false", "0", "no", "off", " FALSE "]

    for value in true_values:
        _set_required_env(monkeypatch, tmp_path)
        monkeypatch.setenv("SECURE_COOKIES", value)
        assert load_settings().secure_cookies is True

    for value in false_values:
        _set_required_env(monkeypatch, tmp_path)
        monkeypatch.setenv("SECURE_COOKIES", value)
        assert load_settings().secure_cookies is False


def test_settings_rejects_unknown_secure_cookies_value(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("SECURE_COOKIES", "enabled")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "SECURE_COOKIES" in str(exc)
    else:
        raise AssertionError("load_settings should fail for unknown SECURE_COOKIES values")


def test_settings_rejects_unknown_reasoning_effort(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "extreme")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "OPENAI_REASONING_EFFORT" in str(exc)
    else:
        raise AssertionError("load_settings should reject unknown reasoning effort")


def test_settings_rejects_invalid_openai_timeout(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "0")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "OPENAI_TIMEOUT_SECONDS" in str(exc)
    else:
        raise AssertionError("load_settings should reject non-positive OpenAI timeout")


def test_settings_rejects_unknown_audit_model_provider(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AUDIT_MODEL_PROVIDER", "azure")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "AUDIT_MODEL_PROVIDER" in str(exc)
    else:
        raise AssertionError("load_settings should reject unknown audit provider")


def test_settings_requires_jdcloud_fields_when_provider_is_jdcloud(
    tmp_path, monkeypatch
):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AUDIT_MODEL_PROVIDER", "jdcloud")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "JDCLOUD_OPENAI_API_KEY" in str(exc)
        assert "JDCLOUD_OPENAI_BASE_URL" in str(exc)
        assert "JDCLOUD_OPENAI_AUDIT_MODEL" in str(exc)
    else:
        raise AssertionError("load_settings should require jdcloud fields")


def test_settings_loads_superapi_provider(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AUDIT_MODEL_PROVIDER", "superapi")
    monkeypatch.setenv("OPENAI_AUDIT_MODEL", "gpt-5.5")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "medium")
    monkeypatch.setenv("SUPERAPI_OPENAI_API_KEY", "super-key")
    monkeypatch.setenv("SUPERAPI_OPENAI_BASE_URL", "https://superapi.buzz/v1")
    monkeypatch.setenv("SUPERAPI_OPENAI_TIMEOUT_SECONDS", "90")

    settings = load_settings()

    assert settings.audit_model_provider == "superapi"
    assert settings.audit_api_key == "super-key"
    assert settings.audit_base_url == "https://superapi.buzz/v1"
    assert settings.audit_model == "gpt-5.5"
    assert settings.audit_reasoning_effort == "medium"
    assert settings.audit_timeout_seconds == 90


def test_settings_requires_superapi_fields_when_provider_is_superapi(
    tmp_path, monkeypatch
):
    _set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AUDIT_MODEL_PROVIDER", "superapi")

    try:
        load_settings()
    except RuntimeError as exc:
        assert "SUPERAPI_OPENAI_API_KEY" in str(exc)
        assert "SUPERAPI_OPENAI_BASE_URL" in str(exc)
    else:
        raise AssertionError("load_settings should require superapi fields")


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
    task_columns = {
        row["name"] for row in conn.execute("pragma table_info(tasks)").fetchall()
    }
    assert {"screen_width_px", "screen_height_px"}.issubset(task_columns)


def test_init_db_sets_schema_version_and_is_idempotent(tmp_path):
    conn = connect(tmp_path / "app.db")

    init_db(conn)
    init_db(conn)

    row = conn.execute("pragma user_version").fetchone()
    assert row[0] == SCHEMA_VERSION


def test_init_db_with_current_schema_version_ensures_tables(tmp_path):
    conn = connect(tmp_path / "app.db")
    conn.execute(f"pragma user_version = {SCHEMA_VERSION}")

    init_db(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }
    assert {"users", "tasks", "task_images", "task_report_reads"}.issubset(tables)


def test_schema_default_timestamps_use_beijing_time(tmp_path, monkeypatch):
    fixed_time = "2026-05-09 20:15:30"
    monkeypatch.setattr("app.db.beijing_now_text", lambda: fixed_time)
    conn = connect(tmp_path / "app.db")
    init_db(conn)

    user_id = conn.execute(
        """
        insert into users (username, password_hash, role)
        values (?, ?, ?)
        """,
        ("alice", "hash-1", "user"),
    ).lastrowid
    task_id = conn.execute(
        """
        insert into tasks (owner_id, title, status, image_count)
        values (?, ?, ?, ?)
        """,
        (user_id, "Alice task", "queued", 1),
    ).lastrowid
    conn.execute(
        """
        insert into task_report_reads (user_id, task_id)
        values (?, ?)
        """,
        (user_id, task_id),
    )

    user_row = conn.execute(
        "select created_at from users where id = ?", (user_id,)
    ).fetchone()
    task_row = conn.execute(
        "select created_at, updated_at from tasks where id = ?", (task_id,)
    ).fetchone()
    read_row = conn.execute(
        """
        select read_at from task_report_reads
        where user_id = ? and task_id = ?
        """,
        (user_id, task_id),
    ).fetchone()

    assert user_row["created_at"] == fixed_time
    assert task_row["created_at"] == fixed_time
    assert task_row["updated_at"] == fixed_time
    assert read_row["read_at"] == fixed_time


def test_init_db_migrates_v2_tasks_to_screen_size_columns(tmp_path):
    conn = connect(tmp_path / "app.db")
    conn.executescript(
        """
        pragma user_version = 2;

        create table users (
          id integer primary key autoincrement,
          username text not null unique,
          password_hash text not null,
          role text not null check (role in ('admin', 'user')),
          status text not null default 'active' check (status in ('active', 'disabled')),
          created_at text not null default current_timestamp,
          last_login_at text
        );

        create table tasks (
          id integer primary key autoincrement,
          owner_id integer not null references users(id),
          title text not null,
          status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
          image_count integer not null check (image_count > 0),
          summary text,
          report_path text,
          error_message text,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          completed_at text
        );

        create table task_images (
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
          error_message text,
          unique(task_id, sort_order)
        );

        create table task_report_reads (
          user_id integer not null references users(id) on delete cascade,
          task_id integer not null references tasks(id) on delete cascade,
          read_at text not null default current_timestamp,
          primary key (user_id, task_id)
        );
        """
    )
    conn.commit()

    init_db(conn)

    columns = {row["name"] for row in conn.execute("pragma table_info(tasks)").fetchall()}
    assert {"screen_width_px", "screen_height_px"}.issubset(columns)
    assert conn.execute("pragma user_version").fetchone()[0] == SCHEMA_VERSION


def test_init_db_rejects_existing_unversioned_core_schema(tmp_path):
    conn = connect(tmp_path / "app.db")
    conn.execute("create table tasks (id integer primary key)")
    conn.commit()

    try:
        init_db(conn)
    except RuntimeError as exc:
        assert "existing unversioned schema requires migration/recreate" in str(exc)
    else:
        raise AssertionError("init_db should reject existing unversioned core schema")


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
    assert {task.id for task in list_tasks_for_user(conn, admin)} == {
        task_a.id,
        task_b.id,
    }


def test_create_task_requires_existing_owner(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)

    try:
        create_task(conn, owner_id=999, title="Missing owner", image_count=1)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("create_task should fail when owner_id does not exist")


def test_create_task_requires_positive_image_count(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", "hash-1", "user")

    try:
        create_task(conn, owner_id=user.id, title="Empty task", image_count=0)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("create_task should fail when image_count is not positive")


def test_create_task_persists_declared_screen_size(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", "hash-1", "user")

    task = create_task(
        conn,
        owner_id=user.id,
        title="Desktop audit",
        image_count=1,
        screen_width_px=1440,
        screen_height_px=900,
    )
    refreshed = get_task_by_id(conn, task.id)

    assert refreshed is not None
    assert refreshed.screen_width_px == 1440
    assert refreshed.screen_height_px == 900


def test_repository_timestamps_use_beijing_time(tmp_path, monkeypatch):
    fixed_time = "2026-05-09 18:30:45"
    monkeypatch.setattr("app.repositories.beijing_now_text", lambda: fixed_time)
    conn = connect(tmp_path / "app.db")
    init_db(conn)

    user = create_user(conn, "alice", "hash-1", "user")
    task = create_task(conn, owner_id=user.id, title="Alice task", image_count=1)
    update_task_status(conn, task.id, TASK_SUCCEEDED, report_path="uploads/1/report.html")
    mark_task_report_read(conn, user.id, task.id)
    mark_user_login(conn, user.id)

    user_row = conn.execute(
        "select created_at, last_login_at from users where id = ?", (user.id,)
    ).fetchone()
    task_row = conn.execute(
        "select created_at, updated_at, completed_at from tasks where id = ?",
        (task.id,),
    ).fetchone()
    read_row = conn.execute(
        """
        select read_at from task_report_reads
        where user_id = ? and task_id = ?
        """,
        (user.id, task.id),
    ).fetchone()

    assert user_row["created_at"] == fixed_time
    assert user_row["last_login_at"] == fixed_time
    assert task_row["created_at"] == fixed_time
    assert task_row["updated_at"] == fixed_time
    assert task_row["completed_at"] == fixed_time
    assert read_row["read_at"] == fixed_time


def test_bulk_report_read_timestamps_use_beijing_time(tmp_path, monkeypatch):
    fixed_time = "2026-05-09 19:01:02"
    monkeypatch.setattr("app.repositories.beijing_now_text", lambda: fixed_time)
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", "hash-1", "user")
    task = create_task(conn, owner_id=user.id, title="Alice task", image_count=1)
    update_task_status(conn, task.id, TASK_SUCCEEDED, report_path="uploads/1/report.html")

    mark_successful_task_reports_read_for_user(conn, user)

    row = conn.execute(
        """
        select read_at from task_report_reads
        where user_id = ? and task_id = ?
        """,
        (user.id, task.id),
    ).fetchone()
    assert row["read_at"] == fixed_time


def test_add_task_image_rejects_duplicate_sort_order_for_same_task(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", "hash-1", "user")
    task = create_task(conn, owner_id=user.id, title="Alice task", image_count=2)
    add_task_image(
        conn,
        task_id=task.id,
        filename="image-001.png",
        original_path="uploads/a/originals/image-001.png",
        sort_order=0,
    )

    try:
        add_task_image(
            conn,
            task_id=task.id,
            filename="image-002.png",
            original_path="uploads/a/originals/image-002.png",
            sort_order=0,
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("add_task_image should reject duplicate sort_order")


def test_list_task_images_orders_by_sort_order(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", "hash-1", "user")
    task = create_task(conn, owner_id=user.id, title="Alice task", image_count=2)
    add_task_image(
        conn,
        task_id=task.id,
        filename="image-002.png",
        original_path="uploads/a/originals/image-002.png",
        sort_order=1,
    )
    add_task_image(
        conn,
        task_id=task.id,
        filename="image-001.png",
        original_path="uploads/a/originals/image-001.png",
        sort_order=0,
    )

    assert [image.filename for image in list_task_images(conn, task.id)] == [
        "image-001.png",
        "image-002.png",
    ]


def test_deleting_task_cascades_to_task_images(tmp_path):
    conn = connect(tmp_path / "app.db")
    init_db(conn)
    user = create_user(conn, "alice", "hash-1", "user")
    task = create_task(conn, owner_id=user.id, title="Alice task", image_count=1)
    add_task_image(
        conn,
        task_id=task.id,
        filename="image-001.png",
        original_path="uploads/a/originals/image-001.png",
        sort_order=0,
    )

    conn.execute("delete from tasks where id = ?", (task.id,))
    conn.commit()

    assert list_task_images(conn, task.id) == []
