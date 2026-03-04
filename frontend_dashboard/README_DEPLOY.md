# Frontend Dashboard — Deployment Guide

**AI Employee Vault – Platinum Tier Web Dashboard**
Next.js 14 App Router | Tailwind CSS | Dark Futuristic UI

---

## Local Development

```bash
cd frontend_dashboard
npm install
cp .env.example .env.local   # edit NEXT_PUBLIC_BACKEND_URL
npm run dev
# Open: http://localhost:3000
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:7860` | FastAPI backend base URL (no trailing slash) |

Create `.env.local` in `frontend_dashboard/`:
```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:7860
```

For production (Vercel), set this as an Environment Variable in the project settings.

---

## Deploy to Vercel

### Step 1 — Import the project

1. Go to https://vercel.com/new
2. Import from GitHub: select `Mehreen676/AI_Employee_Vault_Platinum`
3. Set **Root Directory** to `frontend_dashboard`
4. Framework preset: **Next.js** (auto-detected)

### Step 2 — Set environment variable

In **Project Settings → Environment Variables**, add:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | Your HuggingFace Spaces backend URL, e.g. `https://mehreen676-vault-api.hf.space` |

### Step 3 — Deploy

Click **Deploy**. Vercel builds and deploys automatically on every push to `main`.

---

## Pages

| Route | Description |
|---|---|
| `/` | Overview — queue counts, Cloud Agent heartbeat, last executions, actions |
| `/approvals` | HITL Approvals — task list, detail panel, approve/reject buttons |
| `/logs` | System Logs — execution log, health log, prompt chain (tabbed, auto-refresh) |
| `/evidence` | Evidence Artifacts — file grid, JUDGE_PROOF.md preview, generate button |

---

## UI Features

- **Auto-refresh:** Polls backend every 8–10 seconds for live data
- **Backend status indicator:** Sidebar shows online/offline state
- **Dark futuristic theme:** Neon cyan/green/purple/gold accents on dark navy background
- **HITL Approve/Reject:** One-click task approval or rejection with API confirmation
- **Log streaming:** Terminal-style monospace display with tail-N selector
- **Search & filter:** Approvals page has text search + task type filter
- **Evidence preview:** Click any file card to preview (Markdown shown inline)
- **Error states:** Offline banner when backend unreachable

---

## Production Build

```bash
cd frontend_dashboard
npm run build    # type-checks + builds
npm run start    # serve production build at :3000
```

---

## File Tree

```
frontend_dashboard/
├── app/
│   ├── globals.css          # Dark theme + utility classes
│   ├── layout.tsx           # Root layout with sidebar
│   ├── page.tsx             # Overview (/)
│   ├── approvals/
│   │   └── page.tsx         # HITL Approvals (/approvals)
│   ├── logs/
│   │   └── page.tsx         # System Logs (/logs)
│   └── evidence/
│       └── page.tsx         # Evidence Artifacts (/evidence)
├── components/
│   └── Sidebar.tsx          # Navigation sidebar with backend status
├── lib/
│   ├── api.ts               # Typed API client (all backend calls)
│   └── types.ts             # TypeScript interfaces + queue metadata
├── .env.example             # Environment variable template
├── next.config.js           # Next.js config
├── tailwind.config.js       # Dark theme + vault colour palette
├── package.json
├── tsconfig.json
└── README_DEPLOY.md         # This file
```

---

*AI Employee Vault – Platinum Tier | frontend_dashboard v1.0.0*
