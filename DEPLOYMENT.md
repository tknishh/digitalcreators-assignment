# Deployment Guide — Oracle Cloud (Always Free)

Deploy the Video Regenerator API on **Oracle Cloud Infrastructure (OCI) Always Free** — **4 ARM CPUs + 24 GB RAM**, $0 forever. Enough for CLIP, FFmpeg, crossfade transitions, and optional MusicGen.

Sign up: [oracle.com/cloud/free](https://www.oracle.com/cloud/free/)

---

## What you need

| Item | Notes |
|------|-------|
| Oracle Cloud account | Free tier, no credit card charges for Always Free resources |
| GitHub repo | Code pushed (or upload via `scp`) |
| Firebase project | Storage + service account JSON (recommended) |
| SSH private key | Generated when creating the VM |

---

## Part 1 — Create the VM

### 1. Open Oracle Console

1. Log in to [Oracle Cloud Console](https://cloud.oracle.com/)
2. Menu → **Compute** → **Instances** → **Create instance**

### 2. Configure the instance

| Setting | Value |
|---------|-------|
| **Name** | `video-regenerator` |
| **Image** | **Ubuntu 22.04** (must be **aarch64** / Arm) |
| **Shape** | `VM.Standard.A1.Flex` — **Always Free-eligible** |
| **OCPUs** | **4** |
| **Memory (GB)** | **24** |
| **Boot volume** | **50 GB** |
| **Public IP** | Assign a public IPv4 address |

### 3. SSH keys

- Click **Generate a key pair for me** (or upload your own)
- Download the **private key** (`.key` file) — you need this to SSH in

### 4. Networking (ingress rules)

Under **Primary VNIC** → **Subnet** → ensure a public subnet, then add **Ingress rules**:

| Source | Protocol | Port | Purpose |
|--------|----------|------|---------|
| `0.0.0.0/0` | TCP | **22** | SSH |
| `0.0.0.0/0` | TCP | **8000** | App |

For production you can restrict SSH to your IP instead of `0.0.0.0/0`.

### 5. Create

Click **Create**. Wait until **State** = `Running`. Copy the **Public IP address**.

> **Out of host capacity?** Try another **availability domain**, region (e.g. **Mumbai** `ap-mumbai-1`), or retry later. This is common on Oracle free tier.

---

## Part 2 — Connect and install Docker

### 1. SSH into the instance

From your laptop:

```bash
chmod 400 ~/Downloads/ssh-key-YYYY-MM-DD.key
ssh -i ~/Downloads/ssh-key-YYYY-MM-DD.key ubuntu@YOUR_PUBLIC_IP
```

### 2. Install Docker

On the VM:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu

exit
```

SSH back in (required for docker group):

```bash
ssh -i ~/Downloads/ssh-key-YYYY-MM-DD.key ubuntu@YOUR_PUBLIC_IP
docker --version
docker compose version
```

---

## Part 3 — Deploy the application

### 1. Clone the repository

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/digitalcreators-assignment.git
cd digitalcreators-assignment
```

Private repo or no git? Upload from your laptop:

```bash
scp -i ~/Downloads/ssh-key-YYYY-MM-DD.key -r \
  /path/to/digitalcreators-assignment \
  ubuntu@YOUR_PUBLIC_IP:~/digitalcreators-assignment
```

### 2. Create `.env`

```bash
cp deploy/oracle.env.example .env
nano .env
```

Set your Firebase bucket:

```env
FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`.

### 3. Upload Firebase credentials

From your **laptop**:

```bash
scp -i ~/Downloads/ssh-key-YYYY-MM-DD.key \
  /path/to/firebase-service-account.json \
  ubuntu@YOUR_PUBLIC_IP:~/digitalcreators-assignment/firebase-service-account.json
```

### 4. Build and start

On the VM:

```bash
cd ~/digitalcreators-assignment
docker compose -f docker-compose.yml -f docker-compose.firebase.yml up --build -d
docker compose logs -f
```

First build takes **10–20 minutes** (PyTorch + dependencies on ARM). Wait for:

```
Uvicorn running on http://0.0.0.0:8000
```

### 5. Verify

From your laptop:

```bash
curl http://YOUR_PUBLIC_IP:8000/health
```

Expected:

```json
{"status":"ok","ffmpeg_available":true,"storage_backend":"firebase","version":"2.0.0"}
```

Open **http://YOUR_PUBLIC_IP:8000** → upload videos → download result.

---

## Part 4 — Recommended settings on 24 GB RAM

Oracle’s free VM has plenty of RAM. You can use stronger settings in `.env`:

```env
ENABLE_MUSICGEN=true
VIDEO_QUALITY_PROFILE=balanced
PARALLEL_EXTRACT_WORKERS=4
PARALLEL_ANALYZE_WORKERS=4
```

Restart after changes:

```bash
docker compose -f docker-compose.yml -f docker-compose.firebase.yml down
docker compose -f docker-compose.yml -f docker-compose.firebase.yml up --build -d
```

---

## Part 5 — Keep it running

Docker Compose uses `restart: unless-stopped`. Enable Docker on boot:

```bash
sudo systemctl enable docker
```

After a VM reboot:

```bash
cd ~/digitalcreators-assignment
docker compose -f docker-compose.yml -f docker-compose.firebase.yml up -d
```

### Useful commands

```bash
docker compose logs -f          # live logs
docker compose ps               # container status
docker stats                    # CPU / memory
free -h                         # system memory
df -h                           # disk space
du -sh ~/digitalcreators-assignment/data/*
docker compose down             # stop app
```

---

## Part 6 — Optional: nginx on port 80

If you have a domain pointing to your Oracle VM public IP:

```bash
sudo apt-get install -y nginx

sudo tee /etc/nginx/sites-available/video-regenerator << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/video-regenerator /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Add ingress rule **TCP 80** in Oracle networking. Optional HTTPS:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN
```

---

## Part 7 — Submission

Add your live URL to `SUBMISSION.md`:

```
http://YOUR_PUBLIC_IP:8000
```

**How reviewers test:**

1. Open the URL
2. Set duration (default 15s), quality, optional prompt
3. Upload 2+ short mp4 files
4. Wait for status `completed`
5. Download final video

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Out of host capacity** | Try another availability domain, region, or retry later |
| Can't SSH | Ingress rule TCP 22; check key permissions (`chmod 400`) |
| Can't open `:8000` | Ingress rule TCP 8000; confirm VM is Running |
| `storage_backend: local` | Upload `firebase-service-account.json`; use `docker-compose.firebase.yml` |
| Build fails on ARM | Ensure Ubuntu **aarch64** image; Docker builds natively on ARM |
| First job very slow | CLIP downloads to `./data/hf_cache` on first run (~600 MB) |
| `connection refused` | Run `docker compose ps` and `docker compose logs` |
| Out of disk | Boot volume 50 GB; run `docker system prune -a` if needed |

---

## Checklist

- [ ] Oracle VM: `VM.Standard.A1.Flex`, 4 OCPU, 24 GB RAM, 50 GB disk
- [ ] Ingress: TCP 22 + 8000
- [ ] Docker installed
- [ ] `.env` + Firebase JSON uploaded
- [ ] `docker compose … up -d` running
- [ ] `/health` returns `storage_backend: firebase`
- [ ] End-to-end test passed
- [ ] Live URL in `SUBMISSION.md`

---

## Cost

**$0** — Always Free resources have no time limit. You stay within free tier as long as you use Always Free-eligible shapes and stay under quotas (200 GB block storage total, etc.).
