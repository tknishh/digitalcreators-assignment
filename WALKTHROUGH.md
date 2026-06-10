# Walkthrough — Video Stitcher API

## Problem summary

Build a backend that accepts up to 50 uploaded videos, asynchronously generates one stitched output video (10s–2min) from clips of those uploads, and lets the user download the result.

---

## Architecture

```
Client (curl / minimal HTML)
        │
        ▼
┌───────────────────┐
│   FastAPI (API)   │
│  POST /api/jobs   │──► validate uploads, save to disk
│  GET  /api/jobs/id│──► return status + progress
│  GET  .../download│──► stream output mp4
└─────────┬─────────┘
          │ BackgroundTasks
          ▼
┌───────────────────┐
│  Video processor  │──► ffprobe → select clips → ffmpeg extract → concat
└─────────┬─────────┘
          ▼
   data/uploads/  data/temp/  data/outputs/
```

**Single-process async model:** uploads return immediately (`202 Accepted`) with a `job_id`. Processing runs in a FastAPI background task. FFmpeg calls run in `asyncio.to_thread()` so the event loop stays responsive for status polling.

**Why not block the request?** Video processing can take minutes with 50 files. Blocking would tie up connections, risk gateway timeouts on Render (~30s), and give no progress feedback.

**Why not Celery/Redis yet?** For a single-instance assessment deploy, in-process background tasks are simpler and still demonstrate correct async API design. A queue would be the next step for horizontal scaling.

---

## API design

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Minimal HTML test UI |
| `/health` | GET | Liveness + FFmpeg availability |
| `/api/jobs` | POST | Upload videos, start job |
| `/api/jobs/{id}` | GET | Poll status/progress |
| `/api/jobs/{id}/download` | GET | Download completed video |
| `/api/jobs/{id}` | DELETE | Remove job and files |

**Status lifecycle:** `pending` → `processing` → `completed` | `failed`

**Progress:** 0–100 reported during processing (probe → clip selection → extract → concat → finalize).

---

## Upload validation

- **Count:** 1–50 files per job
- **Extensions:** `.mp4`, `.mov`, `.webm`, `.avi`, `.mkv`
- **MIME types:** checked when provided (browsers send `video/*`; `application/octet-stream` allowed for curl)
- **Per-file max:** 100 MB
- **Total max:** 500 MB per job
- **Empty files:** rejected

Files are saved under `data/uploads/{job_id}/` with indexed safe names.

---

## Clip selection & stitching logic

### Target duration (computed, not user-supplied)

I compute target duration from source material:

```
target = clamp(total_source_duration × 0.4, 10s, 120s)
```

- If sources are very short (< 10s total), target = **10s** (minimum)
- Otherwise use **40% of combined source length**, capped at **120s**
- Rationale: more source material → longer highlight reel, but never outside the required bounds

### Clip length

Default **4 seconds** per clip (`CLIP_DURATION_SEC`), minimum **2 seconds** (`MIN_CLIP_DURATION_SEC`).

### Selection algorithm (round-robin + random start)

1. Probe each upload with `ffprobe` to get duration
2. Calculate how many clips needed: `ceil(target / clip_duration)`
3. **Round-robin** across videos so every upload contributes (when possible)
4. For each clip, pick a **random start time** within the valid range `[0, duration - clip_len]`
5. Skip videos shorter than 2s
6. **Trim** last clips if total exceeds target
7. **Pad** with extra clips if total falls below 10s minimum

### Ordering

Clips are ordered in round-robin sequence: video1 → video2 → … → videoN → video1 → …

This gives variety rather than long contiguous blocks from one file.

### Stitching

1. Extract each clip with FFmpeg (`-ss`, `-t`, re-encode to H.264/AAC for consistency)
2. Write a concat demuxer list file
3. Try **stream copy** concat first (fast); fall back to **re-encode** if codecs/resolutions differ
4. Final duration check; hard-trim if somehow over 120s

### Duration guarantee

| Constraint | Enforcement |
|------------|-------------|
| Min 10s | Pad with extra clips; fail job if still impossible |
| Max 120s | Trim clips during selection; final FFmpeg trim as safety net |
| Target | Computed dynamically per job |

---

## Long-running work & errors

- **Upload response:** immediate `202` with `job_id`
- **Polling:** client polls `GET /api/jobs/{id}` every ~2s (UI does this automatically)
- **Failures:** stored in `error_message` (e.g. corrupt video, FFmpeg error, duration too short)
- **Download:** only when `status == completed`; otherwise `409 Conflict`

---

## Resource awareness

| Concern | Approach |
|---------|----------|
| Large uploads | Streamed to disk in 1 MB chunks; validated before processing |
| Temp files | Per-job `data/temp/{job_id}/` for clip segments |
| Cleanup | `DELETE /api/jobs/{id}` removes all job files; background loop purges jobs older than 24h |
| Disk on Render | 1 GB persistent volume at `/app/data` |
| Memory | No full-file buffering; FFmpeg operates on disk paths |

---

## Key trade-offs

| Decision | Trade-off |
|----------|-----------|
| In-memory job store | Fast, simple; lost on restart (acceptable for assessment; would use Redis/DB in production) |
| Local disk vs S3 | Simpler deploy; doesn't scale to multiple workers without shared storage |
| Re-encode clips | Slower but consistent output; stream-copy concat attempted first |
| Random clip starts | Non-deterministic output; good for “highlight reel” feel; could add seed param later |
| No auth | Per brief; would add API keys or JWT in production |

---

## What I'd improve with more time

1. **Redis + Celery/RQ workers** — durable jobs, horizontal scaling, retries
2. **S3-compatible object storage** — shared storage across instances
3. **Webhooks** instead of polling when job completes
4. **Configurable** target duration, clip length, transitions (crossfade)
5. **Progress granularity** — per-clip ETA based on historical timings
6. **Integration tests** with real short FFmpeg-generated fixtures in CI
7. **Rate limiting** and upload virus scanning for production

---

## How to test end-to-end

1. Start: `docker compose up --build`
2. Open http://localhost:8000
3. Select 2–5 short mp4 files
4. Click Upload & Generate
5. Wait for status `completed` and download link
6. Or use curl commands in README.md
