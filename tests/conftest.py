import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        openai_api_key="test-key",
        app_secret_key="test-secret",
        register_invite_code="invite-123",
        initial_admin_username="admin",
        initial_admin_password="admin-pass",
        data_dir=tmp_path,
        enqueue_background_tasks=False,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
