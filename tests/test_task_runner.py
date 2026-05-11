from PIL import Image

from app.config import Settings
from app.db import connect, init_db
from app.repositories import (
    add_task_image,
    create_task,
    create_user,
    get_task_by_id,
    list_task_images,
)
from app.security import hash_password
from app.storage import ensure_task_dirs, relative_to_data
import app.task_runner as task_runner
from app.task_runner import run_task


def test_run_task_generates_report_for_successful_images(tmp_path):
    settings = Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
    )
    conn = connect(settings.db_path)
    init_db(conn)
    user = create_user(conn, "alice", hash_password("secret123"), "user")
    task = create_task(conn, user.id, "Audit", 1)
    dirs = ensure_task_dirs(settings, task.id)
    image_path = dirs.originals / "image-001.png"
    Image.new("RGB", (20, 20), color=(107, 54, 250)).save(image_path)
    add_task_image(conn, task.id, "image-001.png", relative_to_data(settings, image_path), 0)

    def fake_auditor(path):
        return {
            "screen_context": "测试页",
            "overall_conclusion": "基本符合",
            "major_issues": [],
            "passes": ["主色接近规范"],
            "issues": [],
            "sample_points": [{"label": "center", "x": 10, "y": 10}],
            "regions": [],
            "distances": [],
            "checklist": [{"item": "AI 主色", "status": "通过", "evidence": ""}],
            "cannot_verify": [],
        }

    run_task(settings, task.id, auditor=fake_auditor)

    refreshed = get_task_by_id(conn, task.id)
    images = list_task_images(conn, task.id)

    assert refreshed is not None
    assert refreshed.status == "succeeded"
    assert refreshed.report_path == "uploads/1/report.html"
    assert (tmp_path / refreshed.report_path).exists()
    assert images[0].status == "succeeded"
    assert images[0].tokens_path.endswith("tokens.json")


def test_run_task_includes_declared_screen_size_in_report(tmp_path):
    settings = Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
    )
    conn = connect(settings.db_path)
    init_db(conn)
    user = create_user(conn, "alice", hash_password("secret123"), "user")
    task = create_task(
        conn,
        user.id,
        "Audit",
        1,
        screen_width_px=1440,
        screen_height_px=900,
    )
    dirs = ensure_task_dirs(settings, task.id)
    image_path = dirs.originals / "image-001.png"
    Image.new("RGB", (20, 20), color=(107, 54, 250)).save(image_path)
    add_task_image(conn, task.id, "image-001.png", relative_to_data(settings, image_path), 0)

    def fake_auditor(path):
        return {
            "screen_context": "测试页",
            "overall_conclusion": "基本符合",
            "major_issues": [],
            "passes": [],
            "issues": [],
            "sample_points": [],
            "regions": [],
            "distances": [],
            "checklist": [],
            "cannot_verify": [],
        }

    run_task(settings, task.id, auditor=fake_auditor)

    refreshed = get_task_by_id(conn, task.id)
    assert refreshed is not None
    assert refreshed.report_path is not None
    report_html = (tmp_path / refreshed.report_path).read_text(encoding="utf-8")
    assert "稿件基准尺寸：1440 × 900 px" in report_html


def test_run_task_marks_task_failed_when_all_images_fail(tmp_path):
    settings = Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
    )
    conn = connect(settings.db_path)
    init_db(conn)
    user = create_user(conn, "alice", hash_password("secret123"), "user")
    task = create_task(conn, user.id, "Audit", 1)
    dirs = ensure_task_dirs(settings, task.id)
    image_path = dirs.originals / "image-001.png"
    Image.new("RGB", (20, 20), color=(107, 54, 250)).save(image_path)
    add_task_image(conn, task.id, "image-001.png", relative_to_data(settings, image_path), 0)

    def failing_auditor(path):
        raise RuntimeError("model failed")

    run_task(settings, task.id, auditor=failing_auditor)

    refreshed = get_task_by_id(conn, task.id)
    images = list_task_images(conn, task.id)

    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.error_message == "全部图片审核失败"
    assert images[0].status == "failed"
    assert images[0].error_message == "model failed"


def test_default_auditor_sets_openai_timeout(monkeypatch, tmp_path):
    settings = Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
        openai_timeout_seconds=12,
    )
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(task_runner, "OpenAI", FakeClient)
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("spec", encoding="utf-8")
    monkeypatch.setattr(task_runner, "SPEC_PATH", spec_path)

    auditor = task_runner._default_auditor(settings)

    assert callable(auditor)
    assert captured == {
        "api_key": "key",
        "base_url": None,
        "timeout": 12,
        "max_retries": 0,
    }


def test_default_auditor_uses_jdcloud_chat_when_configured(monkeypatch, tmp_path):
    settings = Settings(
        openai_api_key="key",
        app_secret_key="secret",
        register_invite_code="invite",
        initial_admin_username="admin",
        initial_admin_password="password123",
        data_dir=tmp_path,
        audit_model_provider="jdcloud",
        jdcloud_openai_api_key="jd-key",
        jdcloud_openai_base_url="https://modelservice.jdcloud.com/v1/",
        jdcloud_openai_audit_model="Kimi-K2.6",
        jdcloud_openai_timeout_seconds=60,
    )
    captured_client = {}
    captured_audit = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured_client.update(kwargs)

    def fake_chat_audit(
        client,
        model,
        image_path,
        spec_text,
        reasoning_effort=None,
        declared_screen_size=None,
    ):
        captured_audit.update(
            {
                "client": client,
                "model": model,
                "image_path": image_path,
                "spec_text": spec_text,
                "reasoning_effort": reasoning_effort,
                "declared_screen_size": declared_screen_size,
            }
        )
        return {}

    monkeypatch.setattr(task_runner, "OpenAI", FakeClient)
    monkeypatch.setattr(task_runner, "audit_image_with_chat", fake_chat_audit)
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("spec", encoding="utf-8")
    monkeypatch.setattr(task_runner, "SPEC_PATH", spec_path)

    auditor = task_runner._default_auditor(settings, declared_screen_size=(1440, 900))
    image_path = tmp_path / "screen.png"
    auditor(image_path)

    assert captured_client == {
        "api_key": "jd-key",
        "base_url": "https://modelservice.jdcloud.com/v1/",
        "timeout": 60,
        "max_retries": 0,
    }
    assert captured_audit["model"] == "Kimi-K2.6"
    assert captured_audit["image_path"] == image_path
    assert captured_audit["spec_text"] == "spec"
    assert captured_audit["reasoning_effort"] is None
    assert captured_audit["declared_screen_size"] == (1440, 900)
