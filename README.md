# Video Regenerator API

AI-assisted video regeneration for The Digital Creators backend assessment.

Upload source videos → Hugging Face CLIP scores clips against your prompt → FFmpeg assembles a cohesive output with crossfade transitions → synthetic audio is added → result stored in Firebase (or local mirror) with SQLite job persistence and resumable checkpoints.

## Local setup

### Prerequisites

- Python 3.12+
- FFmpeg (`brew install ffmpeg`)

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

First run downloads Hugging Face CLIP (~600MB). MusicGen is optional (`ENABLE_MUSICGEN=false` speeds up local dev).

### 2. Configure environment

```bash
cp .env.example .env
```

For local dev without Firebase:

```env
USE_LOCAL_STORAGE=true
ENABLE_MUSICGEN=false
```

For Firebase Storage:

1. Create a Firebase project → Storage → get bucket name
2. Project settings → Service accounts → Generate private key
3. Save as `firebase-service-account.json`
4. Set in `.env`:

```env
USE_LOCAL_STORAGE=false
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
```

### 3. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

Or with Docker:

```bash
docker compose up --build
```

## Web UI

The homepage lets you:

- Set **target duration** (10–120s, default **15s**)
- Choose **quality**: Fast / Balanced / High
- Pick **landscape** or **portrait**
- Optionally enter a **prompt** to guide clip selection and audio mood
- Upload videos and poll job progress

## API

### Create job

```bash
curl -X POST http://localhost:8000/api/jobs \
  -F "duration_sec=15" \
  -F "orientation=landscape" \
  -F "quality_profile=balanced" \
  -F "prompt=energetic product launch reel" \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4"
```

| Field | Values | Default |
|-------|--------|---------|
| `duration_sec` | 10–120 | 15 |
| `orientation` | `landscape`, `portrait` | `landscape` |
| `quality_profile` | `fast`, `balanced`, `high` | `fast` |
| `prompt` | optional text | — |

### Poll status

```bash
curl http://localhost:8000/api/jobs/{job_id}
```

### Download

```bash
curl -OJ http://localhost:8000/api/jobs/{job_id}/download
```

## Quality profiles

| Profile | Resolution | CRF | Preset | Typical job time* |
|---------|------------|-----|--------|-------------------|
| `fast` | 720p | 23 | veryfast | ~1–2 min |
| `balanced` | 720p | 20 | fast | ~3–5 min |
| `high` | 1080p | 18 | medium | ~8–15 min |

\*Depends on clip count, source length, and hardware. Each transition merge re-encodes video, so higher quality is multiplicatively slower.

## Architecture

| Component | Technology |
|-----------|------------|
| API | FastAPI |
| Job DB | SQLite (SQLAlchemy) |
| Object storage | Firebase Storage (local mirror fallback) |
| AI clip scoring | Hugging Face CLIP |
| Audio | MusicGen (optional) or FFmpeg ambient fallback |
| Video assembly | FFmpeg (crossfade transitions, color normalization) |
| Worker | Background asyncio worker, 1 job at a time |
| Resume | Checkpointed pipeline in SQLite |

### Checkpoints

`uploaded → analyzed → clips_selected → clips_extracted → stitched → audio_added → completed`

If the server restarts mid-job, the worker resumes from the last checkpoint.

## Tests

```bash
pytest -v
```

## Docs

- [WALKTHROUGH.md](./WALKTHROUGH.md) — architecture, clip selection, transitions, trade-offs
- [TOOLS.md](./TOOLS.md) — technology choices
- [DEPLOYMENT.md](./DEPLOYMENT.md) — Render / Railway deploy guide
