from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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
            raise UploadValidationError(
                f"单张图片不能超过 {settings.max_upload_mb_per_file}MB"
            )


def save_upload_file(settings: Settings, file_obj, output_path: Path) -> None:
    max_bytes = settings.max_upload_mb_per_file * 1024 * 1024
    written = 0
    try:
        with output_path.open("wb") as out:
            while True:
                chunk = file_obj.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UploadValidationError(
                        f"单张图片不能超过 {settings.max_upload_mb_per_file}MB"
                    )
                out.write(chunk)
    except UploadValidationError:
        output_path.unlink(missing_ok=True)
        raise


def ensure_task_dirs(settings: Settings, task_id: int) -> TaskDirs:
    root = settings.uploads_dir / str(task_id)
    originals = root / "originals"
    artifacts = root / "artifacts"
    originals.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    return TaskDirs(
        root=root,
        originals=originals,
        artifacts=artifacts,
        report=root / "report.html",
    )


def relative_to_data(settings: Settings, path: Path) -> str:
    return path.resolve().relative_to(settings.data_dir.resolve()).as_posix()


def resolve_data_path(settings: Settings, relative_path: str) -> Path:
    candidate = (settings.data_dir / relative_path).resolve()
    root = settings.data_dir.resolve()
    if root not in candidate.parents and candidate != root:
        raise UploadValidationError("非法文件路径")
    return candidate


def safe_artifact_path(dirs: TaskDirs, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    relative = PurePosixPath(normalized)
    raw_parts = normalized.split("/")
    if not normalized or relative.is_absolute() or ".." in raw_parts or "" in raw_parts:
        raise UploadValidationError("非法文件路径")
    parts = tuple(raw_parts)
    if parts[:1] == ("artifacts",):
        parts = parts[1:]
    if parts[:1] == ("originals",) or parts == ("report.html",) or not parts:
        raise UploadValidationError("非法文件路径")

    root = dirs.artifacts.resolve()
    candidate = dirs.artifacts.joinpath(*parts).resolve()
    if root not in candidate.parents and candidate != root:
        raise UploadValidationError("非法文件路径")
    return candidate
