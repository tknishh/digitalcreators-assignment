# Walkthrough — Video Regenerator API

## Problem summary

Build a backend that accepts uploaded videos, asynchronously generates one cohesive output video (10s–2min) driven by an optional prompt, and lets the user download the result. Output should feel edited — not random hard cuts.

---

## Architecture

```
Client (HTML UI / curl)
        │
        ▼
┌───────────────────┐
│   FastAPI (API)   │
│  POST /api/jobs   │──► validate uploads → Firebase/local storage
│  GET  /api/jobs/id│──► return status + progress
│  GET  .../download│──► stream output mp4
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  SQLite jobs DB   │──► checkpoints, clip metadata, resume state
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Background worker│──► 1 job at a time
└─────────┬─────────┘
          │
          ▼
┌───────────────────────────────────────────────────┐
│  Pipeline (checkpointed)                            │
│  1. CLIP analyze keyframes (parallel)               │
│  2. Select clips (prompt-driven or round-robin)    │
│  3. Extract + normalize clips (parallel)            │
│  4. Stitch with rotating crossfade transitions      │
│  5. Generate audio (MusicGen or FFmpeg fallback)    │
│  6. Mux + upload final                              │
└───────────────────────────────────────────────────┘
```

**Why async worker + checkpoints?** Video + CLIP processing can take minutes. Upload returns immediately (`202 Accepted`). SQLite checkpoints let jobs resume after container restarts without re-analyzing from scratch.

**Why 1 job at a time?** Keeps memory predictable on constrained hosts; Oracle Always Free (24 GB) handles this comfortably.

---

## API design

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Web UI (upload, duration, quality, orientation, prompt) |
| `/health` | GET | Liveness + FFmpeg + storage backend |
| `/api/jobs` | POST | Upload videos, start job |
| `/api/jobs/{id}` | GET | Poll status/progress |
| `/api/jobs/{id}/download` | GET | Download completed video |
| `/api/jobs/{id}` | DELETE | Remove job and storage objects |

**Status lifecycle:** `pending` → `processing` → `completed` | `failed`

**Job parameters:**

| Parameter | Description |
|-----------|-------------|
| `duration_sec` | Target output length (10–120s). UI default: **15s** |
| `orientation` | `landscape` (1280×720) or `portrait` (720×1280) at fast/balanced; 1080p at high |
| `quality_profile` | `fast` \| `balanced` \| `high` — per-job encode settings |
| `prompt` | Optional — drives CLIP scoring, clip pacing, and audio mood |

---

## Clip selection (prompt-driven editing)

### With prompt

1. Extract keyframes every ~2s from each upload
2. Score frames with Hugging Face CLIP against the prompt (+ cinematic variants)
3. Rank candidates by score, **interleave across source videos** for pacing
4. Avoid back-to-back clips from the same source when possible
5. Plan clip count accounting for crossfade overlap

### Without prompt

Round-robin across videos with balanced variety (no CLIP bias toward one file).

### Clip length

Default **4 seconds** per clip. Selection trims or pads to hit the user's target duration (minimum 10s enforced).

---

## Transitions & visual cohesion

- **Crossfade transitions** between clips via FFmpeg `xfade` + `acrossfade`
- **Rotating styles** per boundary: `fade`, `smoothleft`, `dissolve`, `wipeleft` (configurable via `TRANSITION_STYLES`)
- **Color normalization** during extract (`eq` filter) so mixed sources look more uniform
- **No hard cuts** when transitions are enabled

Transition overlap reduces effective output length; clip planning compensates.

---

## Quality profiles

Each job stores `quality_profile`. The worker applies encode settings for that job only:

| Profile | Resolution | CRF | Preset | Scale | Audio |
|---------|------------|-----|--------|-------|-------|
| fast | 720p | 23 | veryfast | default | 192k |
| balanced | 720p | 20 | fast | Lanczos | 256k |
| high | 1080p | 18 | medium | Lanczos+ | 320k |

**Trade-offs:**

| Improvement | Cost |
|-------------|------|
| Lower CRF (better quality) | Larger files, slower encode |
| Slower preset | Better compression, much slower (× per pipeline stage) |
| 1080p vs 720p | ~2× pixels, more RAM, slower |
| Lanczos scaling | Sharper downscales, slightly slower |
| More clips + transitions | More re-encode passes |

The pipeline re-encodes at extract **and** at each transition merge, so `high` quality on a 60s job with 15 clips is significantly slower than `fast` on a 15s job with 4 clips.

---

## Upload validation

- **Count:** 1–50 files per job
- **Extensions:** `.mp4`, `.mov`, `.webm`, `.avi`, `.mkv`
- **MIME types:** `video/*` when provided; `application/octet-stream` allowed for curl
- **Per-file max:** 100 MB
- **Total max:** 500 MB per job

Files upload to Firebase Storage (or `data/storage/` local mirror).

---

## Persistence & resume

| Data | Storage |
|------|---------|
| Job metadata, checkpoints | SQLite (`data/jobs.db`) |
| Input videos, clip segments, outputs | Firebase / local object storage |

Checkpoints: `uploaded → analyzed → clips_selected → clips_extracted → stitched → audio_added → completed`

On restart, the worker picks up from the last checkpoint. Stale jobs whose input files are missing (e.g. from an old container) are auto-failed with a clear message.

---

## Resource awareness

| Concern | Approach |
|---------|----------|
| Large uploads | Streamed to disk in 1 MB chunks |
| Temp files | Per-job work dir under `data/temp/{job_id}/` |
| Parallelism | Thread pools for CLIP keyframe analysis and clip extraction |
| Memory | CLIP loaded once per analyze stage; MusicGen optional |
| Cleanup | `DELETE /api/jobs/{id}`; TTL-based purge (`JOB_TTL_HOURS`) |
| Deploy | Docker with persistent `data/` volume recommended |

---

## Key trade-offs

| Decision | Trade-off |
|----------|-----------|
| CLIP zero-shot vs BLIP-2 captions | CLIP is fast and good enough for prompt matching; BLIP would be slower but more semantic |
| Per-job quality vs global encode | Per-job lets UI pick quality without server restart |
| Incremental xfade merge | Simpler than one giant filter graph; extra re-encodes per boundary |
| SQLite vs Postgres | SQLite is fine for single-worker assessment; Postgres for multi-instance |
| MusicGen optional | Better prompt-driven audio when enabled; FFmpeg ambient fallback is instant |
| No auth | Per brief; API keys in production |

---

## How to test end-to-end

1. `docker compose up --build`
2. Open http://localhost:8000
3. Set duration to **15s** (default), pick quality, add a prompt
4. Upload 2–5 short mp4 files
5. Click **Upload & Regenerate**
6. Wait for `completed` and download

Or use the curl examples in [README.md](./README.md).
