# Video Stitcher API

Backend service for The Digital Creators backend engineer skill assessment.

Upload up to 50 videos; the service asynchronously stitches random clips into one output video (10 seconds to 2 minutes) that you can download.

## Live URL

> **Deploy before submission.** See [Deployment](#deployment) below.
>
> After deploying to Render/Railway, put the live URL here, e.g. `https://video-stitcher-api.onrender.com`

## Quick start (local)

### Prerequisites

- Python 3.12+
- FFmpeg (`brew install ffmpeg` on macOS)

### One-command run (Docker)

```bash
docker compose up --build
```

Open http://localhost:8000

### Manual run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API usage

### 1. Create a stitching job

```bash
curl -X POST http://localhost:8000/api/jobs \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4"
```

Response (`202 Accepted`):

```json
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Job accepted. Poll GET /api/jobs/{job_id} for status.",
  "video_count": 2,
  "target_duration_sec": 60.0
}
```

### 2. Poll job status

```bash
curl http://localhost:8000/api/jobs/{job_id}
```

Statuses: `pending` → `processing` → `completed` | `failed`

### 3. Download output

```bash
curl -OJ http://localhost:8000/api/jobs/{job_id}/download
```

### 4. Health check

```bash
curl http://localhost:8000/health
```

## Configuration

Copy `.env.example` to `.env`. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_VIDEOS_PER_JOB` | 50 | Max uploads per request |
| `MAX_FILE_SIZE_MB` | 100 | Per-file limit |
| `MAX_TOTAL_SIZE_MB` | 500 | Total upload limit per job |
| `JOB_TTL_HOURS` | 24 | Auto-cleanup of old jobs |

## Project structure

```
app/
├── main.py              # FastAPI app, lifespan, cleanup loop
├── config.py            # Settings
├── models.py            # Job domain models
├── schemas.py           # API response schemas
├── validation.py        # Upload validation
├── routes/
│   ├── health.py
│   └── jobs.py          # Create, status, download, delete
├── services/
│   ├── job_store.py     # In-memory job registry
│   ├── storage.py       # File paths and cleanup
│   └── video_processor.py  # FFmpeg clip logic
└── templates/
    └── index.html       # Minimal test UI
```

## Tests

```bash
pip install -r requirements.txt
pytest -v
```

## Deployment

### Render (recommended)

1. Push repo to GitHub
2. Create a new **Web Service** on [Render](https://render.com)
3. Connect the repo; Render detects `render.yaml` / `Dockerfile`
4. Add a persistent disk mounted at `/app/data` (1 GB is enough for the assessment)
5. Deploy — health check: `/health`

### Railway / Fly.io

Use the included `Dockerfile`. Mount persistent storage to `/app/data`.

## Documentation

- [WALKTHROUGH.md](./WALKTHROUGH.md) — architecture, clip logic, trade-offs
- [TOOLS.md](./TOOLS.md) — tools and rationale
- [QA_QUESTIONS.md](./QA_QUESTIONS.md) — questions for Thursday Q&A

## License

Assessment submission — not for redistribution.
