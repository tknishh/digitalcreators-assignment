# Q&A Questions for Thursday Walkthrough

Prepared questions for the call with Ankit. Grouped by theme.

---

## Scope & expectations

1. **Evaluation weighting** — Which matters most: API design, processing robustness, or deployment? Should I prioritize polish in one area if time is tight?

2. **Live URL strictness** — If deployment hits a blocker (e.g. free-tier cold starts, disk limits), is a Docker one-command local run acceptable as a fallback?

3. **Stretch goals** — For optional items (queue, progress, Docker, tests), do any of these strongly differentiate candidates, or is a working core feature enough?

---

## Product & behavior

4. **Clip selection intent** — Implemented prompt-driven CLIP scoring with interleaved sources for pacing. Without a prompt, round-robin variety. Is this aligned with “regenerate from given footage based on prompt”?

5. **Target duration** — User selects duration via UI/API (10–120s, default 15s). Confirmed this matches the updated brief.

6. **Minimum source requirements** — If a user uploads one 3-second video, producing a 10s output requires repeating/padding clips. Is that acceptable, or should we reject jobs that can't naturally reach 10s?

7. **Transitions** — Implemented rotating crossfade transitions (`fade`, `smoothleft`, `dissolve`, `wipeleft`). Any preferred styles for social vs cinematic output?

---

## Technical constraints

8. **Upload size limits** — I set 100 MB per file and 500 MB total. Are there expected real-world file sizes I should optimize for?

9. **Video formats** — I'm accepting mp4, mov, webm, avi, mkv. Any formats you specifically want supported or excluded?

10. **Concurrent jobs** — Should the service handle multiple simultaneous generation jobs, or is single-job-at-a-time acceptable for the assessment?

11. **Persistence** — Jobs are in-memory with filesystem storage; a restart loses job metadata (files may remain on disk). Is that acceptable for the assessment scope?

---

## Architecture & infrastructure

12. **Background processing** — I used FastAPI BackgroundTasks + thread-pool FFmpeg (no Redis/Celery). At what scale would you expect a proper job queue, and is my approach sufficient to demonstrate async API thinking?

13. **Hosting choice** — Deployed on Oracle Cloud Always Free (ARM, 24 GB RAM) with Docker + Firebase Storage.

14. **Storage lifecycle** — I auto-delete jobs after 24 hours. What retention window would you use in a real product?

15. **Horizontal scaling** — If we ran multiple API instances, shared object storage (S3) would be required. Is discussing that trade-off valuable in the walkthrough?

---

## API design

16. **Polling vs webhooks** — Status polling every 2s is implemented. Would you consider webhooks a must-have for production, or is polling fine for MVP?

17. **Error responses** — Should failed jobs expose raw FFmpeg stderr to the client, or sanitized user-facing messages only?

18. **Idempotency** — Should `POST /api/jobs` support idempotency keys for retry safety, or is that out of scope?

---

## Testing & quality

19. **Test expectations** — Are unit tests + API tests sufficient, or do you expect end-to-end tests with real video fixtures?

20. **Manual test assets** — Can you share sample videos of varying formats/durations for consistent testing, or should I generate synthetic fixtures with FFmpeg?

---

## Submission & process

21. **Walkthrough format** — Is the written WALKTHROUGH.md sufficient, or do you want a short Loom/video demo as well?

22. **Repo visibility** — Should the GitHub repo be public or private with collaborator access?

23. **Post-submission** — After Friday's deadline, is there a follow-up technical deep-dive, or does the written submission + Thursday call cover it?

---

## My proposed talking points (for the call)

- Why async job pattern instead of blocking uploads
- Clip selection algorithm and duration guarantees
- FFmpeg pipeline: probe → extract → concat with re-encode fallback
- Resource cleanup and upload validation edge cases
- What I'd add next: Redis queue, S3, webhooks, configurable parameters
