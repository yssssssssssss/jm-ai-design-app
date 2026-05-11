from __future__ import annotations

import sqlite3

from app.models import (
    ROLE_ADMIN,
    ROLE_USER,
    STATUS_ACTIVE,
    STATUS_DISABLED,
    TASK_QUEUED,
    TASK_RUNNING,
    TASK_FAILED,
    TASK_SUCCEEDED,
    Task,
    TaskImage,
    User,
)
from app.time_utils import beijing_now_text


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
        screen_width_px=row["screen_width_px"],
        screen_height_px=row["screen_height_px"],
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


def _ensure_user_updated(cur: sqlite3.Cursor) -> None:
    if cur.rowcount == 0:
        raise ValueError("user not found")


def create_user(
    conn: sqlite3.Connection, username: str, password_hash: str, role: str
) -> User:
    now = beijing_now_text()
    cur = conn.execute(
        """
        insert into users (username, password_hash, role, created_at)
        values (?, ?, ?, ?)
        """,
        (username, password_hash, role, now),
    )
    conn.commit()
    user = get_user_by_id(conn, int(cur.lastrowid))
    if user is None:
        raise RuntimeError("created user not found")
    return user


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
    return _user(row) if row else None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> User | None:
    row = conn.execute("select * from users where username = ?", (username,)).fetchone()
    return _user(row) if row else None


def list_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute("select * from users order by created_at desc, id desc").fetchall()
    return [_user(row) for row in rows]


def get_user_required_by_username(conn: sqlite3.Connection, username: str) -> User:
    user = get_user_by_username(conn, username)
    if user is None:
        raise ValueError("user not found")
    return user


def count_active_admins(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "select count(*) as count from users where role = ? and status = ?",
        (ROLE_ADMIN, STATUS_ACTIVE),
    ).fetchone()
    return int(row["count"])


def create_task(
    conn: sqlite3.Connection,
    owner_id: int,
    title: str,
    image_count: int,
    screen_width_px: int | None = None,
    screen_height_px: int | None = None,
) -> Task:
    now = beijing_now_text()
    cur = conn.execute(
        """
        insert into tasks (
            owner_id,
            title,
            status,
            image_count,
            screen_width_px,
            screen_height_px,
            created_at,
            updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_id,
            title,
            TASK_QUEUED,
            image_count,
            screen_width_px,
            screen_height_px,
            now,
            now,
        ),
    )
    conn.commit()
    task = get_task_by_id(conn, int(cur.lastrowid))
    if task is None:
        raise RuntimeError("created task not found")
    return task


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
    image = get_task_image_by_id(conn, int(cur.lastrowid))
    if image is None:
        raise RuntimeError("created task image not found")
    return image


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
    return list_tasks_by_status_for_user(conn, user)


def list_tasks_by_status_for_user(
    conn: sqlite3.Connection,
    user: User,
    statuses: set[str] | None = None,
) -> list[Task]:
    status_filter = ""
    params: list[object] = []
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        status_filter = f" and tasks.status in ({placeholders})"
        params.extend(sorted(statuses))

    if user.is_admin:
        rows = conn.execute(
            f"""
            select tasks.*, users.username as owner_username
            from tasks
            join users on users.id = tasks.owner_id
            where 1 = 1
            {status_filter}
            order by tasks.created_at desc, tasks.id desc
            """,
            params,
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            select tasks.*, users.username as owner_username
            from tasks
            join users on users.id = tasks.owner_id
            where tasks.owner_id = ?
            {status_filter}
            order by tasks.created_at desc, tasks.id desc
            """,
            [user.id, *params],
        ).fetchall()
    return [_task(row) for row in rows]


def list_active_tasks_for_user(conn: sqlite3.Connection, user: User) -> list[Task]:
    return list_tasks_by_status_for_user(conn, user, {TASK_QUEUED, TASK_RUNNING})


def list_successful_tasks_for_user(conn: sqlite3.Connection, user: User) -> list[Task]:
    return list_tasks_by_status_for_user(conn, user, {TASK_SUCCEEDED})


def list_unread_successful_task_ids_for_user(
    conn: sqlite3.Connection, user: User
) -> set[int]:
    owner_filter = "" if user.is_admin else "and tasks.owner_id = ?"
    params: list[object] = [user.id]
    if not user.is_admin:
        params.append(user.id)
    rows = conn.execute(
        f"""
        select tasks.id
        from tasks
        left join task_report_reads
          on task_report_reads.task_id = tasks.id
         and task_report_reads.user_id = ?
        where tasks.status = ?
          and tasks.report_path is not null
          and task_report_reads.task_id is null
          {owner_filter}
        order by tasks.completed_at desc, tasks.created_at desc, tasks.id desc
        """,
        [*params[:1], TASK_SUCCEEDED, *params[1:]],
    ).fetchall()
    return {int(row["id"]) for row in rows}


def mark_task_report_read(
    conn: sqlite3.Connection,
    user_id: int,
    task_id: int,
) -> None:
    now = beijing_now_text()
    conn.execute(
        """
        insert into task_report_reads (user_id, task_id, read_at)
        values (?, ?, ?)
        on conflict(user_id, task_id) do update set read_at = excluded.read_at
        """,
        (user_id, task_id, now),
    )
    conn.commit()


def mark_successful_task_reports_read_for_user(
    conn: sqlite3.Connection,
    user: User,
) -> None:
    task_ids = list_unread_successful_task_ids_for_user(conn, user)
    if not task_ids:
        return
    now = beijing_now_text()
    conn.executemany(
        """
        insert into task_report_reads (user_id, task_id, read_at)
        values (?, ?, ?)
        on conflict(user_id, task_id) do update set read_at = excluded.read_at
        """,
        [(user.id, task_id, now) for task_id in task_ids],
    )
    conn.commit()


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
    now = beijing_now_text()
    completed_at = now if status in {TASK_SUCCEEDED, TASK_FAILED} else None
    cur = conn.execute(
        """
        update tasks
        set status = ?,
            summary = coalesce(?, summary),
            report_path = coalesce(?, report_path),
            error_message = ?,
            updated_at = ?,
            completed_at = coalesce(?, completed_at)
        where id = ?
        """,
        (status, summary, report_path, error_message, now, completed_at, task_id),
    )
    if cur.rowcount == 0:
        raise ValueError("task not found")
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
    cur = conn.execute(
        """
        update task_images
        set status = ?,
            annotated_path = coalesce(?, annotated_path),
            tokens_path = coalesce(?, tokens_path),
            measurements_path = coalesce(?, measurements_path),
            issues_path = coalesce(?, issues_path),
            audit_json_path = coalesce(?, audit_json_path),
            error_message = ?
        where id = ?
        """,
        (
            status,
            annotated_path,
            tokens_path,
            measurements_path,
            issues_path,
            audit_json_path,
            error_message,
            image_id,
        ),
    )
    if cur.rowcount == 0:
        raise ValueError("task image not found")
    conn.commit()


def set_user_status(conn: sqlite3.Connection, user_id: int, status: str) -> None:
    cur = conn.execute("update users set status = ? where id = ?", (status, user_id))
    _ensure_user_updated(cur)
    conn.commit()


def set_user_status_preserving_last_admin(
    conn: sqlite3.Connection, user_id: int, status: str
) -> None:
    conn.execute("begin immediate")
    with conn:
        user = get_user_by_id(conn, user_id)
        if user is None:
            raise ValueError("user not found")
        if (
            status == STATUS_DISABLED
            and user.role == ROLE_ADMIN
            and user.status == STATUS_ACTIVE
            and count_active_admins(conn) <= 1
        ):
            raise ValueError("last active admin")
        cur = conn.execute("update users set status = ? where id = ?", (status, user_id))
        _ensure_user_updated(cur)


def set_user_password(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    cur = conn.execute(
        "update users set password_hash = ? where id = ?", (password_hash, user_id)
    )
    _ensure_user_updated(cur)
    conn.commit()


def set_user_role(conn: sqlite3.Connection, user_id: int, role: str) -> None:
    cur = conn.execute("update users set role = ? where id = ?", (role, user_id))
    _ensure_user_updated(cur)
    conn.commit()


def set_user_role_preserving_last_admin(
    conn: sqlite3.Connection, user_id: int, role: str
) -> None:
    conn.execute("begin immediate")
    with conn:
        user = get_user_by_id(conn, user_id)
        if user is None:
            raise ValueError("user not found")
        if (
            role == ROLE_USER
            and user.role == ROLE_ADMIN
            and user.status == STATUS_ACTIVE
            and count_active_admins(conn) <= 1
        ):
            raise ValueError("last active admin")
        cur = conn.execute("update users set role = ? where id = ?", (role, user_id))
        _ensure_user_updated(cur)


def mark_user_login(conn: sqlite3.Connection, user_id: int) -> None:
    now = beijing_now_text()
    cur = conn.execute(
        "update users set last_login_at = ? where id = ?", (now, user_id)
    )
    _ensure_user_updated(cur)
    conn.commit()
