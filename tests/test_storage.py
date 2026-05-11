from app.config import Settings
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


class FakeUpload:
    def __init__(self, filename: str, content_type: str, size: int):
        self.filename = filename
        self.content_type = content_type
        self.size = size


def _settings(tmp_path):
    return Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
        max_upload_files=2,
        max_upload_mb_per_file=1,
    )


def test_validate_upload_batch_rejects_bad_type_and_count(tmp_path):
    settings = _settings(tmp_path)

    try:
        validate_upload_batch(settings, [FakeUpload("a.txt", "text/plain", 12)])
    except UploadValidationError as exc:
        assert "仅支持 PNG/JPG/JPEG/WEBP" in str(exc)
    else:
        raise AssertionError("text upload should be rejected")

    try:
        validate_upload_batch(
            settings,
            [
                FakeUpload("a.png", "image/png", 12),
                FakeUpload("b.png", "image/png", 12),
                FakeUpload("c.png", "image/png", 12),
            ],
        )
    except UploadValidationError as exc:
        assert "最多上传 2 张图片" in str(exc)
    else:
        raise AssertionError("too many files should be rejected")


def test_validate_upload_batch_rejects_empty_file_list(tmp_path):
    settings = _settings(tmp_path)

    try:
        validate_upload_batch(settings, [])
    except UploadValidationError as exc:
        assert "请至少上传 1 张图片" in str(exc)
    else:
        raise AssertionError("empty file list should be rejected")


def test_validate_upload_batch_rejects_oversized_declared_size(tmp_path):
    settings = _settings(tmp_path)
    max_bytes = settings.max_upload_mb_per_file * 1024 * 1024

    try:
        validate_upload_batch(
            settings,
            [FakeUpload("a.png", "image/png", max_bytes + 1)],
        )
    except UploadValidationError as exc:
        assert "单张图片不能超过" in str(exc)
    else:
        raise AssertionError("oversized upload should be rejected")


def test_validate_upload_batch_accepts_valid_images(tmp_path):
    settings = _settings(tmp_path)

    validate_upload_batch(
        settings,
        [
            FakeUpload("a.png", "image/png", 12),
            FakeUpload("b.jpeg", "image/jpeg", 12),
        ],
    )


def test_stored_image_name_ignores_user_filename():
    assert stored_image_name(0, "evil/../../x.png") == "image-001.png"
    assert stored_image_name(1, "mock.JPG") == "image-002.jpg"


def test_task_dirs_and_safe_artifact_paths(tmp_path):
    settings = _settings(tmp_path)
    dirs = ensure_task_dirs(settings, task_id=42)

    assert dirs.root == tmp_path / "uploads" / "42"
    assert dirs.originals.exists()
    assert dirs.artifacts.exists()

    assert (
        safe_artifact_path(dirs, "artifacts/annotated.png")
        == dirs.artifacts / "annotated.png"
    )
    assert safe_artifact_path(dirs, "annotated.png") == (
        dirs.artifacts / "annotated.png"
    )

    try:
        safe_artifact_path(dirs, "../app.db")
    except UploadValidationError as exc:
        assert "非法文件路径" in str(exc)
    else:
        raise AssertionError("path traversal should fail")

    for relative_path in [
        "originals/image-001.png",
        "report.html",
        "../artifacts/foo.png",
        "report/../foo.png",
    ]:
        try:
            safe_artifact_path(dirs, relative_path)
        except UploadValidationError as exc:
            assert "非法文件路径" in str(exc)
        else:
            raise AssertionError(f"{relative_path} should fail")


def test_data_path_helpers_block_traversal_and_return_posix_paths(tmp_path):
    settings = _settings(tmp_path)
    inside = settings.data_dir / "uploads" / "42" / "originals" / "image-001.png"

    assert relative_to_data(settings, inside) == "uploads/42/originals/image-001.png"
    assert resolve_data_path(settings, "uploads/42/report.html") == (
        settings.data_dir / "uploads" / "42" / "report.html"
    ).resolve()

    try:
        resolve_data_path(settings, "../app.db")
    except UploadValidationError as exc:
        assert "非法文件路径" in str(exc)
    else:
        raise AssertionError("data path traversal should fail")


def test_save_upload_file_enforces_size_limit(tmp_path):
    settings = _settings(tmp_path)
    output = tmp_path / "out.png"

    class FileObj:
        def __init__(self):
            self.calls = 0

        def read(self, size=-1):
            self.calls += 1
            if self.calls == 1:
                return b"x"
            if self.calls == 2:
                return b"x" * (settings.max_upload_mb_per_file * 1024 * 1024)
            return b"x" * (settings.max_upload_mb_per_file * 1024 * 1024 + 1)

    try:
        save_upload_file(settings, FileObj(), output)
    except UploadValidationError as exc:
        assert "单张图片不能超过" in str(exc)
        assert not output.exists()
    else:
        raise AssertionError("oversized stream should fail")
