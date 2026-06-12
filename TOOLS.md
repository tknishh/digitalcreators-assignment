# Tools Used

## Languages & frameworks

| Tool | Why |
|------|-----|
| **Python 3.12** | Strong ecosystem for media tooling and ML inference |
| **FastAPI** | Async-native, automatic OpenAPI docs, multipart upload support |
| **Pydantic / pydantic-settings** | Typed API models and environment configuration |
| **SQLAlchemy** | SQLite job persistence with checkpoint resume |
| **Uvicorn** | ASGI server for local dev and Docker |

## AI & media

| Tool | Why |
|------|-----|
| **Hugging Face Transformers** | CLIP zero-shot image classification for prompt-driven clip scoring |
| **MusicGen** (optional) | Prompt-conditioned background audio when `ENABLE_MUSICGEN=true` |
| **FFmpeg / ffprobe** | Extract, normalize, crossfade stitch, mux, duration probe |
| **xfade / acrossfade** | Rotating crossfade transitions between clips |

## Storage

| Tool | Why |
|------|-----|
| **Firebase Storage** | Durable object storage for inputs, clips, and outputs |
| **Local mirror** (`data/storage/`) | Fallback when Firebase credentials are absent |
| **SQLite** (`data/jobs.db`) | Job metadata, checkpoints, clip selection JSON |
| **aiofiles** | Non-blocking upload streaming |

## Infrastructure

| Tool | Why |
|------|-----|
| **Docker / docker-compose** | Reproducible environment with FFmpeg; one-command reviewer setup |
| **Oracle Cloud Always Free** | Docker on ARM VM (4 OCPU, 24 GB RAM), $0 |

## Testing

| Tool | Why |
|------|-----|
| **pytest** | API and clip-selection unit tests |
| **FastAPI TestClient** | Integration tests without a live server |

## Frontend

| Tool | Why |
|------|-----|
| **Jinja2 + vanilla JS** | Upload UI with duration slider, quality picker, orientation, prompt, and status polling |

## Deliberately not used (and why)

| Skipped | Reason |
|---------|--------|
| Celery / Redis | Single asyncio worker + SQLite checkpoints sufficient for assessment scope |
| BLIP-2 captions | CLIP is faster; BLIP would improve semantic matching at higher latency |
| PostgreSQL | SQLite adequate for single-worker deployment |
| Auth | Out of scope per brief |
