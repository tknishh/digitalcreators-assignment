# Deployment Guide (Render)

## Prerequisites

- GitHub account
- [Render](https://render.com) account (free tier works)

## Steps

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Video stitcher API - skill assessment submission"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/digitalcreators-assignment.git
git push -u origin main
```

### 2. Create Render Web Service

1. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Settings:
   - **Runtime:** Docker
   - **Health Check Path:** `/health`
   - **Plan:** Free (or Starter if you need faster cold starts)

### 3. Add persistent disk

Under **Disks**:
- **Name:** `video-data`
- **Mount Path:** `/app/data`
- **Size:** 1 GB

This keeps uploads and outputs across deploys/restarts.

### 4. Deploy

Render builds from `Dockerfile` automatically. First deploy takes ~5–10 minutes.

### 5. Verify

```bash
curl https://YOUR-SERVICE.onrender.com/health
```

Expected:
```json
{"status":"ok","ffmpeg_available":true,"version":"1.0.0"}
```

### 6. Update submission docs

Add the live URL to:
- `README.md`
- `SUBMISSION.md`

---

## Railway alternative

1. New project → Deploy from GitHub repo
2. Railway auto-detects Dockerfile
3. Add a volume mounted at `/app/data`
4. Set health check to `/health`

---

## Notes

- **Free tier cold starts:** First request after idle may take 30–60s. Mention this in your submission email.
- **Disk limits:** 1 GB is enough for the assessment; jobs auto-expire after 24 hours.
- **FFmpeg:** Included in Docker image — no extra setup needed.
