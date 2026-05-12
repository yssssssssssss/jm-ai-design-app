from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REQUIRED_ENV = [
    "OPENAI_API_KEY",
    "APP_SECRET_KEY",
    "REGISTER_INVITE_CODE",
    "INITIAL_ADMIN_USERNAME",
    "INITIAL_ADMIN_PASSWORD",
]

TRUE_VALUES = {"true", "1", "yes", "on"}
FALSE_VALUES = {"false", "0", "no", "off"}
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
AUDIT_MODEL_PROVIDERS = {"openai", "jdcloud", "superapi"}
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    app_secret_key: str
    register_invite_code: str
    initial_admin_username: str
    initial_admin_password: str
    data_dir: Path
    audit_model_provider: str = "openai"
    openai_base_url: str | None = None
    openai_reasoning_effort: str | None = None
    openai_audit_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: int = 180
    jdcloud_openai_api_key: str | None = None
    jdcloud_openai_base_url: str | None = None
    jdcloud_openai_audit_model: str | None = None
    jdcloud_openai_reasoning_effort: str | None = None
    jdcloud_openai_timeout_seconds: int | None = None
    superapi_openai_api_key: str | None = None
    superapi_openai_base_url: str | None = None
    superapi_openai_audit_model: str | None = None
    superapi_openai_reasoning_effort: str | None = None
    superapi_openai_timeout_seconds: int | None = None
    max_upload_files: int = 8
    max_upload_mb_per_file: int = 10
    secure_cookies: bool = False
    enqueue_background_tasks: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def audit_api_key(self) -> str:
        if self.audit_model_provider == "jdcloud":
            return self.jdcloud_openai_api_key or ""
        if self.audit_model_provider == "superapi":
            return self.superapi_openai_api_key or ""
        return self.openai_api_key

    @property
    def audit_base_url(self) -> str | None:
        if self.audit_model_provider == "jdcloud":
            return self.jdcloud_openai_base_url
        if self.audit_model_provider == "superapi":
            return self.superapi_openai_base_url
        return self.openai_base_url

    @property
    def audit_model(self) -> str:
        if self.audit_model_provider == "jdcloud":
            return self.jdcloud_openai_audit_model or ""
        if self.audit_model_provider == "superapi":
            return self.superapi_openai_audit_model or self.openai_audit_model
        return self.openai_audit_model

    @property
    def audit_reasoning_effort(self) -> str | None:
        if self.audit_model_provider == "jdcloud":
            return self.jdcloud_openai_reasoning_effort
        if self.audit_model_provider == "superapi":
            return self.superapi_openai_reasoning_effort or self.openai_reasoning_effort
        return self.openai_reasoning_effort

    @property
    def audit_timeout_seconds(self) -> int:
        if self.audit_model_provider == "jdcloud":
            return self.jdcloud_openai_timeout_seconds or self.openai_timeout_seconds
        if self.audit_model_provider == "superapi":
            return self.superapi_openai_timeout_seconds or self.openai_timeout_seconds
        return self.openai_timeout_seconds


def _load_data_dir() -> Path:
    data_dir_raw = (os.getenv("DATA_DIR") or "data").strip() or "data"
    return Path(data_dir_raw).expanduser().resolve()


def _load_secure_cookies() -> bool:
    raw_value = os.getenv("SECURE_COOKIES", "false").strip().lower()
    if raw_value in TRUE_VALUES:
        return True
    if raw_value in FALSE_VALUES:
        return False
    raise RuntimeError(
        "Invalid SECURE_COOKIES value. Expected one of: "
        "true, 1, yes, on, false, 0, no, off"
    )


def _load_reasoning_effort() -> str | None:
    return _load_reasoning_effort_env("OPENAI_REASONING_EFFORT")


def _load_reasoning_effort_env(key: str) -> str | None:
    value = (os.getenv(key) or "").strip().lower()
    if not value:
        return None
    if value not in REASONING_EFFORTS:
        raise RuntimeError(
            f"Invalid {key} value. Expected one of: "
            "none, minimal, low, medium, high, xhigh"
        )
    return value


def _load_openai_timeout_seconds() -> int:
    return _load_positive_int("OPENAI_TIMEOUT_SECONDS", "180")


def _load_positive_int(key: str, default: str) -> int:
    raw_value = os.getenv(key, default).strip()
    try:
        timeout = int(raw_value)
    except ValueError:
        raise RuntimeError(f"Invalid {key} value. Expected a positive integer")
    if timeout <= 0:
        raise RuntimeError(f"Invalid {key} value. Expected a positive integer")
    return timeout


def _load_audit_model_provider() -> str:
    provider = (os.getenv("AUDIT_MODEL_PROVIDER") or "openai").strip().lower()
    if provider not in AUDIT_MODEL_PROVIDERS:
        raise RuntimeError(
            "Invalid AUDIT_MODEL_PROVIDER value. Expected openai, jdcloud, or superapi"
        )
    return provider


def _load_optional_env(key: str) -> str | None:
    return (os.getenv(key) or "").strip() or None


def _load_jdcloud_required_values(provider: str) -> dict[str, str | None]:
    keys = [
        "JDCLOUD_OPENAI_API_KEY",
        "JDCLOUD_OPENAI_BASE_URL",
        "JDCLOUD_OPENAI_AUDIT_MODEL",
    ]
    values = {key: _load_optional_env(key) for key in keys}
    if provider == "jdcloud":
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
    return values


def _load_superapi_required_values(provider: str) -> dict[str, str | None]:
    keys = [
        "SUPERAPI_OPENAI_API_KEY",
        "SUPERAPI_OPENAI_BASE_URL",
    ]
    values = {key: _load_optional_env(key) for key in keys}
    if provider == "superapi":
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
    return values


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    env = {key: (os.getenv(key) or "").strip() for key in REQUIRED_ENV}
    missing = [key for key, value in env.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    audit_model_provider = _load_audit_model_provider()
    jdcloud_values = _load_jdcloud_required_values(audit_model_provider)
    superapi_values = _load_superapi_required_values(audit_model_provider)

    return Settings(
        openai_api_key=env["OPENAI_API_KEY"],
        app_secret_key=env["APP_SECRET_KEY"],
        register_invite_code=env["REGISTER_INVITE_CODE"],
        initial_admin_username=env["INITIAL_ADMIN_USERNAME"],
        initial_admin_password=env["INITIAL_ADMIN_PASSWORD"],
        data_dir=_load_data_dir(),
        audit_model_provider=audit_model_provider,
        openai_base_url=(os.getenv("OPENAI_BASE_URL") or "").strip() or None,
        openai_reasoning_effort=_load_reasoning_effort(),
        openai_audit_model=os.getenv("OPENAI_AUDIT_MODEL", "gpt-4.1-mini"),
        openai_timeout_seconds=_load_openai_timeout_seconds(),
        jdcloud_openai_api_key=jdcloud_values["JDCLOUD_OPENAI_API_KEY"],
        jdcloud_openai_base_url=jdcloud_values["JDCLOUD_OPENAI_BASE_URL"],
        jdcloud_openai_audit_model=jdcloud_values["JDCLOUD_OPENAI_AUDIT_MODEL"],
        jdcloud_openai_reasoning_effort=_load_reasoning_effort_env(
            "JDCLOUD_OPENAI_REASONING_EFFORT"
        ),
        jdcloud_openai_timeout_seconds=_load_positive_int(
            "JDCLOUD_OPENAI_TIMEOUT_SECONDS", str(_load_openai_timeout_seconds())
        ),
        superapi_openai_api_key=superapi_values["SUPERAPI_OPENAI_API_KEY"],
        superapi_openai_base_url=superapi_values["SUPERAPI_OPENAI_BASE_URL"],
        superapi_openai_audit_model=_load_optional_env("SUPERAPI_OPENAI_AUDIT_MODEL"),
        superapi_openai_reasoning_effort=_load_reasoning_effort_env(
            "SUPERAPI_OPENAI_REASONING_EFFORT"
        ),
        superapi_openai_timeout_seconds=_load_positive_int(
            "SUPERAPI_OPENAI_TIMEOUT_SECONDS", str(_load_openai_timeout_seconds())
        ),
        max_upload_files=int(os.getenv("MAX_UPLOAD_FILES", "8")),
        max_upload_mb_per_file=int(os.getenv("MAX_UPLOAD_MB_PER_FILE", "10")),
        secure_cookies=_load_secure_cookies(),
        enqueue_background_tasks=True,
    )
