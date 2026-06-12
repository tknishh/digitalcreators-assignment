import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import init_db
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    storage_path = tmp_path / "storage"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "local_storage_dir", storage_path)
    monkeypatch.setattr(settings, "use_local_storage", True)
    monkeypatch.setattr(settings, "enable_musicgen", False)
    init_db()

    mock_storage = MagicMock()
    mock_storage.upload.side_effect = lambda local, key, **kw: key
    mock_storage.download.side_effect = lambda key, local: local.write_bytes(b"fake")
    mock_storage.exists.return_value = True
    mock_storage.delete.return_value = None
    mock_storage.get_public_url.return_value = None

    with patch("app.routes.jobs.get_object_storage", return_value=mock_storage), patch(
        "app.services.object_storage.get_object_storage", return_value=mock_storage
    ), patch("app.services.pipeline.get_object_storage", return_value=mock_storage), patch(
        "app.routes.health.check_ffmpeg_available", return_value=True
    ), patch(
        "app.main.worker.run_forever", return_value=None
    ):
        with TestClient(app) as test_client:
            yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["storage_backend"] == "local"


def test_create_job_requires_files(client):
    response = client.post(
        "/api/jobs",
        data={"duration_sec": 30, "orientation": "landscape"},
    )
    assert response.status_code == 422


def test_create_job_rejects_bad_duration(client):
    response = client.post(
        "/api/jobs",
        data={"duration_sec": 5, "orientation": "landscape"},
        files=[("files", ("test.mp4", io.BytesIO(b"fake"), "video/mp4"))],
    )
    assert response.status_code == 400


def test_create_job_rejects_unsupported_extension(client):
    response = client.post(
        "/api/jobs",
        data={"duration_sec": 30, "orientation": "landscape"},
        files=[("files", ("test.txt", io.BytesIO(b"not video"), "text/plain"))],
    )
    assert response.status_code == 400


def test_create_job_accepts_valid_request(client):
    with patch("app.routes.jobs.probe_duration", return_value=12.0):
        response = client.post(
            "/api/jobs",
            data={
                "duration_sec": 30,
                "orientation": "portrait",
                "quality_profile": "balanced",
                "prompt": "energetic product launch video",
            },
            files=[("files", ("clip.mp4", io.BytesIO(b"fake video"), "video/mp4"))],
        )
    assert response.status_code == 202
    data = response.json()
    assert data["orientation"] == "portrait"
    assert data["duration_sec"] == 30
    assert data["quality_profile"] == "balanced"


def test_create_job_rejects_bad_quality(client):
    response = client.post(
        "/api/jobs",
        data={"duration_sec": 30, "orientation": "landscape", "quality_profile": "ultra"},
        files=[("files", ("test.mp4", io.BytesIO(b"fake"), "video/mp4"))],
    )
    assert response.status_code == 400


def test_get_job_not_found(client):
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404
