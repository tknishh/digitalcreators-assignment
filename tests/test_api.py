import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Job, JobStatus
from app.services.job_store import job_store


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    job_store._jobs.clear()
    yield
    job_store._jobs.clear()


def test_health(client):
    with patch("app.routes.health.check_ffmpeg_available", return_value=True):
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ffmpeg_available"] is True


def test_create_job_rejects_empty_upload(client):
    response = client.post("/api/jobs", files=[])
    assert response.status_code == 422


def test_create_job_accepts_video_avi_mime(client):
    with patch("app.routes.jobs._run_generation"):
        response = client.post(
            "/api/jobs",
            files=[("files", ("clip.avi", io.BytesIO(b"fake avi bytes"), "video/avi"))],
        )
    assert response.status_code == 202


def test_create_job_rejects_unsupported_extension(client):
    response = client.post(
        "/api/jobs",
        files=[("files", ("test.txt", io.BytesIO(b"not video"), "text/plain"))],
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_get_job_not_found(client):
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_job_status_completed(client):
    job = Job(status=JobStatus.COMPLETED)
    job.output_path = None
    await job_store.create(job)

    response = client.get(f"/api/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
