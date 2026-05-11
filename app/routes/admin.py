from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import connect
from app.main import ensure_csrf, templates
from app.models import ROLE_ADMIN, ROLE_USER, STATUS_ACTIVE, STATUS_DISABLED
from app.repositories import (
    get_user_by_id,
    list_users,
    set_user_password,
    set_user_role_preserving_last_admin,
    set_user_status_preserving_last_admin,
)
from app.security import CsrfError, ForbiddenError, hash_password, require_admin, verify_csrf

router = APIRouter(prefix="/admin")

_ROLES = {ROLE_ADMIN, ROLE_USER}
_STATUSES = {STATUS_ACTIVE, STATUS_DISABLED}


def _conn(request: Request):
    return connect(request.app.state.settings.db_path)


def _current_admin(request: Request, conn):
    user_id = request.session.get("user_id")
    try:
        user = get_user_by_id(conn, int(user_id)) if user_id else None
    except (TypeError, ValueError) as exc:
        raise ForbiddenError("Admin role required", status_code=403) from exc
    return require_admin(user)


def _bad_request(message: str) -> HTMLResponse:
    return HTMLResponse(message, status_code=400)


def _forbidden() -> HTMLResponse:
    return HTMLResponse("Forbidden", status_code=403)


def _not_found() -> HTMLResponse:
    return HTMLResponse("User not found", status_code=404)


def _verify_action(request: Request, conn, csrf_token: str | None):
    try:
        admin = _current_admin(request, conn)
    except ForbiddenError:
        return None, _forbidden()
    try:
        verify_csrf(request.session, csrf_token)
    except CsrfError:
        return None, _bad_request("Invalid CSRF token")
    return admin, None


def _target_user(conn, user_id: int):
    user = get_user_by_id(conn, user_id)
    if user is None:
        raise ValueError("user not found")
    return user


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    conn = _conn(request)
    try:
        try:
            user = _current_admin(request, conn)
        except ForbiddenError:
            return _forbidden()
        return templates.TemplateResponse(
            request,
            "admin_users.html",
            {
                "user": user,
                "users": list_users(conn),
                "csrf_token": ensure_csrf(request),
                "title": "用户管理",
            },
        )
    finally:
        conn.close()


@router.post("/users/{user_id}/status")
def update_user_status(
    request: Request,
    user_id: int,
    status: str = Form(...),
    csrf_token: str | None = Form(None),
):
    conn = _conn(request)
    try:
        _, error = _verify_action(request, conn, csrf_token)
        if error:
            return error
        if status not in _STATUSES:
            return _bad_request("Invalid status")
        try:
            _target_user(conn, user_id)
        except ValueError:
            return _not_found()
        try:
            set_user_status_preserving_last_admin(conn, user_id, status)
        except ValueError as exc:
            if str(exc) == "last active admin":
                return _bad_request("不能禁用最后一个管理员")
            return _not_found()
    finally:
        conn.close()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/role")
def update_user_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    csrf_token: str | None = Form(None),
):
    conn = _conn(request)
    try:
        _, error = _verify_action(request, conn, csrf_token)
        if error:
            return error
        if role not in _ROLES:
            return _bad_request("Invalid role")
        try:
            _target_user(conn, user_id)
        except ValueError:
            return _not_found()
        try:
            set_user_role_preserving_last_admin(conn, user_id, role)
        except ValueError as exc:
            if str(exc) == "last active admin":
                return _bad_request("不能降级最后一个管理员")
            return _not_found()
    finally:
        conn.close()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/password")
def update_user_password(
    request: Request,
    user_id: int,
    password: str = Form(...),
    csrf_token: str | None = Form(None),
):
    conn = _conn(request)
    try:
        _, error = _verify_action(request, conn, csrf_token)
        if error:
            return error
        if len(password) < 8:
            return _bad_request("密码至少 8 位")
        try:
            target = _target_user(conn, user_id)
        except ValueError:
            return _not_found()
        try:
            set_user_password(conn, target.id, hash_password(password))
        except ValueError:
            return _not_found()
    finally:
        conn.close()
    return RedirectResponse("/admin/users", status_code=303)
