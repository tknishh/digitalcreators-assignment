# Submission — Backend Engineer Skill Assessment

**Candidate:** Tanish Khandelwal  
**Submitted to:** ankit@thedigitalcreators.io  
**Deadline:** Friday, 12 June 2026, 6:00 PM IST

---

## 1. Live feature

**URL:** _[ADD YOUR DEPLOYED URL HERE, e.g. https://video-stitcher-api.onrender.com]_

**How to test:**
1. Open the URL in a browser
2. Set duration (default 15s), quality, orientation; optionally add a prompt
3. Upload 2+ short video files (mp4/mov/webm)
4. Wait for processing to complete (status polls automatically)
5. Click **Download final video**

**API alternative (curl):**
```bash
# Create job
curl -X POST https://YOUR_URL/api/jobs \
  -F "duration_sec=15" \
  -F "quality_profile=fast" \
  -F "prompt=energetic product reel" \
  -F "files=@a.mp4" \
  -F "files=@b.mp4"

# Poll status
curl https://YOUR_URL/api/jobs/{job_id}

# Download
curl -OJ https://YOUR_URL/api/jobs/{job_id}/download
```

---

## 2. Tools used

See [TOOLS.md](./TOOLS.md).

**Summary:** Python, FastAPI, FFmpeg, Docker, Oracle Cloud (deployment), Firebase Storage, pytest.

---

## 3. Source code

**Repository:** _[ADD YOUR GITHUB REPO URL HERE]_

Clone and run locally:
```bash
git clone <repo-url>
cd digitalcreators-assignment
docker compose up --build
```

---

## 4. Walkthrough document

See [WALKTHROUGH.md](./WALKTHROUGH.md) for:
- Architecture and async job design
- Clip selection and duration logic
- Validation, error handling, cleanup
- Trade-offs and future improvements

---

## 5. Local one-command fallback

```bash
docker compose up --build
# → http://localhost:8000
```

Requires Docker. FFmpeg is included in the image.
