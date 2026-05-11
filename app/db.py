from __future__ import annotations

import sqlite3
from pathlib import Path

from app.time_utils import beijing_now_text


SCHEMA_VERSION = 3
CORE_TABLES = {"users", "tasks", "task_images"}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.create_function("beijing_now", 0, beijing_now_text)
    conn.execute("pragma foreign_keys = on")
    return conn


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("pragma user_version").fetchone()
    return int(row[0])


def _has_core_tables(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        """
        select name from sqlite_master
        where type = 'table' and name in ('users', 'tasks', 'task_images')
        """
    ).fetchall()
    return bool({row["name"] for row in rows} & CORE_TABLES)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if not _has_column(conn, table, column):
        conn.execute(f"alter table {table} add column {ddl}")


def init_db(conn: sqlite3.Connection) -> None:
    version = _user_version(conn)
    if version == 0 and _has_core_tables(conn):
        raise RuntimeError("existing unversioned schema requires migration/recreate")
    if version not in (0, 1, 2, SCHEMA_VERSION):
        raise RuntimeError(f"unsupported database schema version: {version}")

    conn.executescript(
        """
        create table if not exists users (
          id integer primary key autoincrement,
          username text not null unique,
          password_hash text not null,
          role text not null check (role in ('admin', 'user')),
          status text not null default 'active' check (status in ('active', 'disabled')),
          created_at text not null default (beijing_now()),
          last_login_at text
        );

        create table if not exists tasks (
          id integer primary key autoincrement,
          owner_id integer not null references users(id),
          title text not null,
          status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
          image_count integer not null check (image_count > 0),
          screen_width_px integer check (screen_width_px is null or screen_width_px > 0),
          screen_height_px integer check (screen_height_px is null or screen_height_px > 0),
          summary text,
          report_path text,
          error_message text,
          created_at text not null default (beijing_now()),
          updated_at text not null default (beijing_now()),
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
          error_message text,
          unique(task_id, sort_order)
        );

        create table if not exists task_report_reads (
          user_id integer not null references users(id) on delete cascade,
          task_id integer not null references tasks(id) on delete cascade,
          read_at text not null default (beijing_now()),
          primary key (user_id, task_id)
        );

        create index if not exists idx_tasks_owner_created on tasks(owner_id, created_at desc);
        create index if not exists idx_task_report_reads_user
          on task_report_reads(user_id, read_at desc);
        """
    )
    if version in (1, 2):
        _ensure_column(
            conn,
            "tasks",
            "screen_width_px",
            "screen_width_px integer check (screen_width_px is null or screen_width_px > 0)",
        )
        _ensure_column(
            conn,
            "tasks",
            "screen_height_px",
            "screen_height_px integer check (screen_height_px is null or screen_height_px > 0)",
        )
    if version == 1:
        conn.execute(
            """
            insert or ignore into task_report_reads (user_id, task_id, read_at)
            select users.id, tasks.id, beijing_now()
            from users
            join tasks
            where tasks.status = 'succeeded'
              and tasks.report_path is not null
              and (users.role = 'admin' or users.id = tasks.owner_id)
            """
        )
    conn.execute(f"pragma user_version = {SCHEMA_VERSION}")
    conn.commit()
