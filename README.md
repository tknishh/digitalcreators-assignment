# Video Regenerator API

AI-assisted video regeneration for The Digital Creators backend assessment.

Upload source videos → Hugging Face CLIP scores clips against your prompt → FFmpeg assembles a cohesive output with crossfade transitions → synthetic audio is added → result stored locally or in Firebase with SQLite job persistence and resumable checkpoints.

---

## Quick start (Docker — recommended)

Everything runs in one container: Python, FFmpeg, CLIP, and the API. No local Python or FFmpeg install required.

### 1. Install Docker

Install **Docker Desktop** (includes Docker Compose):

| OS | Download |
|----|----------|
| **macOS** | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| **Windows** | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |
| **Linux** | [Docker Engine](https://docs.docker.com/engine/install/) + [Compose plugin](https://docs.docker.com/compose/install/linux/) |

Verify:

```bash
docker --version
docker compose version
```

### 2. Run with one command

From the project root:

```bash
cp -n .env.example .env && docker compose up --build
```

- `cp -n .env.example .env` creates `.env` on first run only (won't overwrite yours later)
- First start downloads Hugging Face CLIP (~600MB) into `./data/hf_cache` — may take a few minutes
- When you see `Uvicorn running on http://0.0.0.0:8000`, open **http://localhost:8000**

Stop with `Ctrl+C`. Run again anytime:

```bash
docker compose up --build
```

### 3. Verify

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok","ffmpeg_available":true,"storage_backend":"local","version":"2.0.0"}
```

Then upload videos in the browser, or use the [API examples](#api) below.

### Default settings (`.env.example`)

| Setting | Default | Notes |
|---------|---------|-------|
| Storage | Local (`data/storage/`) | No Firebase account needed |
| MusicGen | Off | Faster; FFmpeg generates ambient audio |
| Quality | `fast` | 720p, quick encode |
| Duration | 15s | Adjustable in UI |

To enable MusicGen locally (slower, more RAM):

```env
ENABLE_MUSICGEN=true
```

---

## Optional: Firebase Storage

To store uploads and outputs in Firebase instead of `data/storage/`:

1. Firebase Console → **Storage** → note your bucket name
2. Project settings → **Service accounts** → **Generate new private key**
3. Save the JSON as `firebase-service-account.json` in the project root
4. Update `.env`:

```env
USE_LOCAL_STORAGE=false
FIREBASE_CREDENTIALS_PATH=/app/firebase-service-account.json
FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
```

5. Start with the Firebase compose overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.firebase.yml up --build
```

Check `/health` — `storage_backend` should be `"firebase"`. Files appear in Firebase Console under `jobs/{job-id}/`.

---

## Web UI

The homepage lets you:

- Set **target duration** (10–120s, default **15s**)
- Choose **quality**: Fast / Balanced / High
- Pick **landscape** or **portrait**
- Optionally enter a **prompt** to guide clip selection and audio mood
- Upload videos and poll job progress

---

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

---

## Quality profiles

| Profile | Resolution | CRF | Preset | Typical job time* |
|---------|------------|-----|--------|-------------------|
| `fast` | 720p | 23 | veryfast | ~1–2 min |
| `balanced` | 720p | 20 | fast | ~3–5 min |
| `high` | 1080p | 18 | medium | ~8–15 min |

\*Depends on clip count, source length, and hardware.

---

## Alternative: run without Docker

For development without containers:

**Prerequisites:** Python 3.12+, FFmpeg (`brew install ffmpeg`)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

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

---

## Tests

```bash
pytest -v
```

With Docker (one-off):

```bash
docker compose run --rm api pytest -v
```

---

## Docs

- [WALKTHROUGH.md](./WALKTHROUGH.md) — architecture, clip selection, transitions, trade-offs
- [TOOLS.md](./TOOLS.md) — technology choices
- [DEPLOYMENT.md](./DEPLOYMENT.md) — cloud deploy notes (Render, etc.)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Port 8000 in use | Change `"8000:8000"` to `"8080:8000"` in `docker-compose.yml`, open http://localhost:8080 |
| Out of memory | Set `ENABLE_MUSICGEN=false`, use `quality_profile=fast` in UI |
| `storage_backend: local` but expected Firebase | Check credentials path, use `docker-compose.firebase.yml` overlay |
| Slow first job | CLIP model download on first run; cached in `./data/hf_cache` after that |
