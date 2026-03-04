# Backend API — Deployment Guide

**AI Employee Vault – Platinum Tier FastAPI Backend**
Version: 1.0.0 | Port: 7860 (HuggingFace Spaces default)

---

## Quick Local Run

```bash
# From repo root
cd backend_api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 7860
```

Interactive docs: http://localhost:7860/docs

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VAULT_ROOT` | Parent of `backend_api/` | Absolute path to the repo root. Must contain `vault/` and `Evidence/`. |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins, e.g. `https://your-vercel-app.vercel.app` |
| `PORT` | `7860` | Server port |

Set via `.env` or shell export:

```bash
export VAULT_ROOT=/home/ubuntu/AI_Employee_Vault_Platinum
export ALLOWED_ORIGINS=https://your-dashboard.vercel.app
export PORT=7860
```

---

## Deploy to HuggingFace Spaces (Docker SDK)

### Step 1 — Create a Space

1. Go to https://huggingface.co/spaces
2. Click **Create new Space**
3. Choose **Docker** as the SDK
4. Note your Space URL: `https://huggingface.co/spaces/<org>/<space-name>`

### Step 2 — Add Secrets (optional)

In Space **Settings → Repository secrets**, add:

| Secret | Value |
|---|---|
| `ALLOWED_ORIGINS` | Your Vercel frontend URL, e.g. `https://vault-dashboard.vercel.app` |
| `VAULT_ROOT` | `/app` (the default when using the Dockerfile below) |

### Step 3 — Push to the Space repo

```bash
# Clone your Space repo
git clone https://huggingface.co/spaces/<org>/<space-name>
cd <space-name>

# Copy repo files into the Space
rsync -av /path/to/AI_Employee_Vault_Platinum/ . --exclude='.git'

# The Dockerfile at backend_api/Dockerfile is used automatically by HF Spaces
# You can also place it at the repo root if required by your Space config
cp backend_api/Dockerfile Dockerfile

git add .
git commit -m "Deploy Platinum Tier backend API"
git push
```

HuggingFace Spaces builds the Docker image and exposes port 7860 automatically.

---

## API Endpoints Reference

### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns `{status:"ok", time, version}` |
| `GET` | `/status` | Vault queue counts + last heartbeat + last execution |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/redoc` | ReDoc documentation |

### Queues

| Method | Path | Description |
|---|---|---|
| `GET` | `/queue/{name}` | List tasks in a queue. `name`: `needs_action`, `pending_approval`, `approved`, `done`, `retry_queue` |
| `GET` | `/task/{queue}/{filename}` | Full JSON of a specific task |

### Logs

| Method | Path | Description |
|---|---|---|
| `GET` | `/logs/execution?tail=50` | Tail vault/Logs/execution_log.json |
| `GET` | `/logs/health?tail=50` | Tail vault/Logs/health_log.json |
| `GET` | `/logs/prompt?tail=20` | Tail history/prompt_log.json (SHA-256 chain) |

### Evidence

| Method | Path | Description |
|---|---|---|
| `GET` | `/evidence/judge-proof` | Return Evidence/JUDGE_PROOF.md as plain text |
| `GET` | `/evidence/list` | List all files in Evidence/ |
| `POST` | `/evidence/generate?n=20` | Run generate_evidence_pack.py and return result |

### HITL

| Method | Path | Description |
|---|---|---|
| `POST` | `/approve/{filename}` | Move task from Waiting_Approval → Pending_Approval |
| `POST` | `/reject/{filename}` | Move task from Waiting_Approval → Rejected |

---

## Quick curl Test Suite

```bash
BASE=http://localhost:8000

# 1. Health check
curl -s $BASE/health | python -m json.tool

# 2. Vault status summary
curl -s $BASE/status | python -m json.tool

# 3. List pending_approval queue
curl -s "$BASE/queue/pending_approval" | python -m json.tool

# 4. List done queue (last 10)
curl -s "$BASE/queue/done?limit=10" | python -m json.tool

# 5. Tail execution log (last 5 entries)
curl -s "$BASE/logs/execution?tail=5" | python -m json.tool

# 6. Tail health log (last 3 entries)
curl -s "$BASE/logs/health?tail=3" | python -m json.tool

# 7. Tail prompt log (last 5 entries)
curl -s "$BASE/logs/prompt?tail=5" | python -m json.tool

# 8. List evidence files
curl -s "$BASE/evidence/list" | python -m json.tool

# 9. Read JUDGE_PROOF.md
curl -s "$BASE/evidence/judge-proof"

# 10. Generate evidence pack
curl -s -X POST "$BASE/evidence/generate?n=20" | python -m json.tool

# 11. Approve a task (replace filename with actual task filename)
curl -s -X POST "$BASE/approve/task_abc123.json" | python -m json.tool

# 12. Reject a task
curl -s -X POST "$BASE/reject/task_xyz456.json" | python -m json.tool
```

---

## Local Docker Test

```bash
# Build
docker build -t vault-api -f backend_api/Dockerfile .

# Run (mount local vault for live state)
docker run -p 7860:7860 \
  -v "$(pwd)/vault:/app/vault" \
  -v "$(pwd)/Evidence:/app/Evidence" \
  -v "$(pwd)/history:/app/history" \
  -e ALLOWED_ORIGINS=http://localhost:3000 \
  vault-api

# Test
curl http://localhost:7860/health
```

---

## Security Notes

- **Filename validation:** `_safe_filename()` blocks path traversal (`..`, `/`, `\`)
- **CORS:** Set `ALLOWED_ORIGINS` to your specific frontend URL in production
- **Read-only vault:** GET endpoints never write to the vault
- **Approval endpoints:** Only `.json` and `.md` files can be moved
- **No credentials in API:** No secrets are exposed through any endpoint
- **DRY_RUN:** Set `DRY_RUN=true` in the vault agent environment to prevent all vault writes during testing

---

*AI Employee Vault – Platinum Tier | backend_api v1.0.0*
