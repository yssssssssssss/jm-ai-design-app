from __future__ import annotations

import sqlite3

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
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": ensure_csrf(request), "error": error, "user": None},
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
    try:
        user = get_user_by_username(conn, username.strip())
        if (
            not user
            or user.status != "active"
            or not verify_password(password, user.password_hash)
        ):
            request.session["login_error"] = "用户名或密码错误"
            return RedirectResponse("/login", status_code=303)
        mark_user_login(conn, user.id)
    finally:
        conn.close()

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
            {
                "csrf_token": ensure_csrf(request),
                "error": "用户名至少 3 位，密码至少 8 位",
                "user": None,
            },
            status_code=400,
        )

    conn = _conn(request)
    try:
        if get_user_by_username(conn, clean_username):
            return templates.TemplateResponse(
                request,
                "register.html",
                {
                    "csrf_token": ensure_csrf(request),
                    "error": "用户名已存在",
                    "user": None,
                },
                status_code=400,
            )
        try:
            user = create_user(conn, clean_username, hash_password(password), "user")
        except sqlite3.IntegrityError:
            return templates.TemplateResponse(
                request,
                "register.html",
                {
                    "csrf_token": ensure_csrf(request),
                    "error": "用户名已存在",
                    "user": None,
                },
                status_code=400,
            )
    finally:
        conn.close()

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
