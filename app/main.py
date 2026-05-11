from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, load_settings
from app.db import connect, init_db
from app.repositories import count_active_admins, create_user
from app.security import hash_password, new_csrf_token


APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=APP_DIR / "templates")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(settings.db_path)
    try:
        init_db(conn)
        if count_active_admins(conn) == 0:
            create_user(
                conn,
                settings.initial_admin_username,
                hash_password(settings.initial_admin_password),
                "admin",
            )
    finally:
        conn.close()

    app = FastAPI()
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
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
