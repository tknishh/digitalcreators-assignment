# Tools Used

## Languages & frameworks

| Tool | Why |
|------|-----|
| **Python 3.12** | Strong ecosystem for media tooling, fast to ship, readable for reviewers |
| **FastAPI** | Async-native, automatic OpenAPI docs, excellent multipart upload support, `BackgroundTasks` for simple job dispatch without extra infra |
| **Pydantic / pydantic-settings** | Typed request/response models and environment-based configuration |
| **Uvicorn** | ASGI server; production-ready with the Docker image |

## Video processing

| Tool | Why |
|------|-----|
| **FFmpeg** | Industry standard for probe, trim, transcode, and concat. Handles mixed codecs/resolutions with a fallback re-encode path |
| **ffprobe** | Reliable duration/metadata probing before clip selection |

## Storage & I/O

| Tool | Why |
|------|-----|
| **Local filesystem** (`data/uploads`, `data/temp`, `data/outputs`) | Simplest correct choice for an assessment MVP; no S3 credentials or extra cost. Persistent disk on Render keeps files across restarts |
| **aiofiles** | Non-blocking file writes during multipart upload streaming |

## Infrastructure

| Tool | Why |
|------|-----|
| **Docker** | Reproducible environment with FFmpeg pre-installed; same image locally and in production |
| **docker-compose** | One-command local run for reviewers |
| **Render** (target) | Free tier, Docker deploy, persistent disk, health checks — low friction for a timed assessment |

## Testing

| Tool | Why |
|------|-----|
| **pytest** | Standard Python test runner |
| **pytest-asyncio** | Async job store tests |
| **httpx / FastAPI TestClient** | API integration tests without a running server |

## Frontend (minimal)

| Tool | Why |
|------|-----|
| **Jinja2 template + vanilla JS** | Bare-minimum UI to upload files and poll status — satisfies “test the feature” without spending time on UI |

## Deliberately not used (and why)

| Skipped | Reason |
|---------|--------|
| Celery / Redis | BackgroundTasks + async FFmpeg in thread pool is sufficient for the assessment scope; queue adds deploy complexity |
| S3 / cloud storage | Local disk + persistent volume is simpler; would add with multi-instance scaling |
| PostgreSQL | In-memory job store is fine for single-instance MVP; job metadata is ephemeral |
| Auth | Out of scope per brief |
