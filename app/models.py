from __future__ import annotations

from dataclasses import dataclass


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
    created_at: str | None = None
    last_login_at: str | None = None

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
    screen_width_px: int | None
    screen_height_px: int | None
    summary: str | None
    report_path: str | None
    error_message: str | None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
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
