from __future__ import annotations

from sqlite3 import Connection

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from app.db import connect
from app.main import ensure_csrf, templates
from app.models import User
from app.repositories import (
    add_task_image,
    create_task,
    get_task_by_id,
    get_user_by_id,
    list_active_tasks_for_user,
    list_task_images,
    list_tasks_for_user,
    list_unread_successful_task_ids_for_user,
    mark_successful_task_reports_read_for_user,
    mark_task_report_read,
    user_can_access_task,
)
from app.security import CsrfError, ForbiddenError, require_login, verify_csrf
from app.storage import (
    UploadValidationError,
    ensure_task_dirs,
    relative_to_data,
    resolve_data_path,
    safe_artifact_path,
    save_upload_file,
    stored_image_name,
    validate_upload_batch,
)
from app.task_queue import enqueue_task


router = APIRouter()


def _current_user_and_conn(request: Request) -> tuple[User, Connection]:
    conn = connect(request.app.state.settings.db_path)
    try:
        user_id = request.session.get("user_id")
        user = get_user_by_id(conn, int(user_id)) if user_id else None
        return require_login(user), conn
    except Exception:
        conn.close()
        raise


def _redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def _error_response(message: str, status_code: int = 400) -> HTMLResponse:
    return HTMLResponse(message, status_code=status_code)


def _has_history_updates(conn: Connection, user: User) -> bool:
    return bool(list_unread_successful_task_ids_for_user(conn, user))


def _validate_screen_size(
    width: str | None,
    height: str | None,
) -> tuple[int | None, int | None]:
    width_value = (width or "").strip()
    height_value = (height or "").strip()
    if not width_value and not height_value:
        return None, None
    if not width_value or not height_value:
        raise UploadValidationError("截图宽度和高度需要同时填写")
    try:
        parsed_width = int(width_value)
        parsed_height = int(height_value)
    except ValueError:
        raise UploadValidationError("截图宽度和高度必须填写整数")
    if str(parsed_width) != width_value or str(parsed_height) != height_value:
        raise UploadValidationError("截图宽度和高度必须填写整数")
    if not 1 <= parsed_width <= 20000 or not 1 <= parsed_height <= 20000:
        raise UploadValidationError("截图宽度和高度必须在 1 到 20000 px 之间")
    return parsed_width, parsed_height


def _authorized_task(request: Request, task_id: int):
    user, conn = _current_user_and_conn(request)
    try:
        task = get_task_by_id(conn, task_id)
        if task is None or not user_can_access_task(user, task):
            return None, _error_response("Forbidden", status_code=403)
        return task, None
    finally:
        conn.close()


@router.get("/", response_class=HTMLResponse)
def upload_page(request: Request):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return _redirect_to_login()
    try:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "user": user,
                "csrf_token": ensure_csrf(request),
                "error": None,
                "title": "新建任务",
                "nav_active": "new",
                "hide_page_title": True,
                "has_history_updates": _has_history_updates(conn, user),
            },
        )
    finally:
        conn.close()


@router.post("/tasks")
async def create_task_route(
    request: Request,
    title: str = Form(...),
    csrf_token: str = Form(...),
    screen_width_px: str | None = Form(None),
    screen_height_px: str | None = Form(None),
    files: list[UploadFile] = File(...),
):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return _error_response("Login required", status_code=403)

    try:
        try:
            verify_csrf(request.session, csrf_token)
            validate_upload_batch(request.app.state.settings, files)
            screen_width_px, screen_height_px = _validate_screen_size(
                screen_width_px,
                screen_height_px,
            )
        except CsrfError:
            return _error_response("Invalid CSRF token")
        except UploadValidationError as exc:
            return _error_response(str(exc))

        clean_title = title.strip() or "未命名审核任务"
        task = create_task(
            conn,
            owner_id=user.id,
            title=clean_title,
            image_count=len(files),
            screen_width_px=screen_width_px,
            screen_height_px=screen_height_px,
        )
        dirs = ensure_task_dirs(request.app.state.settings, task.id)

        for index, upload in enumerate(files):
            filename = stored_image_name(index, upload.filename or "")
            output_path = dirs.originals / filename
            save_upload_file(request.app.state.settings, upload.file, output_path)
            add_task_image(
                conn,
                task_id=task.id,
                filename=filename,
                original_path=relative_to_data(request.app.state.settings, output_path),
                sort_order=index,
            )
        if request.app.state.settings.enqueue_background_tasks:
            enqueue_task(request.app.state.settings, task.id)
    except UploadValidationError as exc:
        return _error_response(str(exc))
    finally:
        conn.close()

    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.get("/tasks", response_class=HTMLResponse)
def task_list(request: Request):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return _redirect_to_login()
    try:
        mark_successful_task_reports_read_for_user(conn, user)
        return templates.TemplateResponse(
            request,
            "tasks.html",
            {
                "user": user,
                "csrf_token": ensure_csrf(request),
                "tasks": list_tasks_for_user(conn, user),
                "unread_task_ids": set(),
                "has_history_updates": False,
                "title": "历史任务",
                "nav_active": "history",
                "task_mode": "history",
            },
        )
    finally:
        conn.close()


@router.get("/tasks/running", response_class=HTMLResponse)
def running_task_list(request: Request):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return _redirect_to_login()
    try:
        return templates.TemplateResponse(
            request,
            "tasks.html",
            {
                "user": user,
                "csrf_token": ensure_csrf(request),
                "tasks": list_active_tasks_for_user(conn, user),
                "unread_task_ids": set(),
                "has_history_updates": _has_history_updates(conn, user),
                "title": "正在进行",
                "nav_active": "running",
                "task_mode": "running",
            },
        )
    finally:
        conn.close()


@router.get("/tasks/{task_id}/report.html")
def report_html(request: Request, task_id: int):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return _error_response("Login required", status_code=401)
    try:
        task = get_task_by_id(conn, task_id)
        if task is None or not user_can_access_task(user, task):
            return _error_response("Forbidden", status_code=403)
        if not task.report_path:
            return _error_response("Report not ready", status_code=404)

        try:
            path = resolve_data_path(request.app.state.settings, task.report_path)
        except UploadValidationError:
            return _error_response("非法文件路径", status_code=400)
        if not path.exists() or not path.is_file():
            return _error_response("Report not found", status_code=404)
        mark_task_report_read(conn, user.id, task.id)
        return FileResponse(path, media_type="text/html; charset=utf-8")
    finally:
        conn.close()


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return _redirect_to_login()
    try:
        task = get_task_by_id(conn, task_id)
        if task is None or not user_can_access_task(user, task):
            return _error_response("Forbidden", status_code=403)
        return templates.TemplateResponse(
            request,
            "task_detail.html",
            {
                "user": user,
                "csrf_token": ensure_csrf(request),
                "task": task,
                "images": list_task_images(conn, task.id),
                "title": task.title,
                "nav_active": "running"
                if task.status in {"queued", "running"}
                else "history",
                "has_history_updates": _has_history_updates(conn, user),
            },
        )
    finally:
        conn.close()


@router.get("/artifacts/{task_id}/{artifact_path:path}")
def artifact_file(request: Request, task_id: int, artifact_path: str):
    try:
        _, error = _authorized_task(request, task_id)
    except (ForbiddenError, TypeError, ValueError):
        return _error_response("Login required", status_code=401)
    if error:
        return error

    dirs = ensure_task_dirs(request.app.state.settings, task_id)
    try:
        path = safe_artifact_path(dirs, artifact_path)
    except UploadValidationError:
        return _error_response("非法文件路径", status_code=400)
    if not path.exists() or not path.is_file():
        return _error_response("Not found", status_code=404)
    return FileResponse(path)


@router.get("/artifacts/{artifact_path:path}")
def malformed_artifact_file(artifact_path: str):
    return _error_response("Not found", status_code=404)


@router.get("/tasks/{task_id}/status")
def task_status(request: Request, task_id: int):
    try:
        user, conn = _current_user_and_conn(request)
    except (ForbiddenError, TypeError, ValueError):
        return JSONResponse({"error": "login required"}, status_code=401)
    try:
        task = get_task_by_id(conn, task_id)
        if task is None or not user_can_access_task(user, task):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        images = list_task_images(conn, task.id)
        return {
            "id": task.id,
            "status": task.status,
            "summary": task.summary,
            "error_message": task.error_message,
            "images": [
                {
                    "id": image.id,
                    "filename": image.filename,
                    "status": image.status,
                    "error_message": image.error_message,
                }
                for image in images
            ],
        }
    finally:
        conn.close()
