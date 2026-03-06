# Finance Assistant

A ChatGPT-like chat application with a Flask backend, Next.js frontend, Supabase for authentication and database, and OpenAI thinking model integration with real-time streaming.

## Project Structure

```
finance-clawbot/
├── backend/          # Flask API server
├── frontend/         # Next.js React app
└── .env.example      # Environment variable template
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- Redis
- A Supabase project (cloud)
- An OpenAI API key

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` in the project root and fill in your credentials:

```bash
cp .env.example .env
```

### 2. Database Setup

Run the SQL migration in your Supabase SQL Editor:
- `backend/supabase/migrations/001_initial_schema.sql`

### 3. Install Dependencies

```bash
make install
```

Or manually:

```bash
cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cd frontend && npm install
```

### 4. Run Everything

From the project root, start all services with a single command:

```bash
make dev
```

This launches Redis, the Flask backend (port 5001), the Celery worker + beat scheduler, and the Next.js frontend (port 3000). Ctrl+C stops all processes.

To force-stop any leftover processes:

```bash
make stop
```

## Deployment (Railway + Vercel)

This repo is deployed as two apps:
- Backend services on Railway (`api`, `worker-beat`, and `redis`)
- Frontend on Vercel (using the `frontend/` Next.js app)

### Railway services

Use one Railway project with multiple services, each connected to this repo:

- `api` service
  - Root directory: repository root
  - Start command: `cd backend && gunicorn run:app --bind 0.0.0.0:${PORT:-5001} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-120}`
- `worker-beat` service
  - Root directory: repository root
  - Start command: `cd backend && celery -A celery_app.celery worker --beat --loglevel=${CELERY_LOG_LEVEL:-info} --concurrency=${CELERY_CONCURRENCY:-2}`
- `redis` service
  - Use Railway Redis plugin and wire its URL into `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`.

Config files used by Railway:
- `railway.json`
- `nixpacks.toml`
- `Procfile` (process command reference)

### Vercel frontend

Create a Vercel project from this repo and set project root to `frontend/`.
`vercel.json` in repo root contains install/build/dev commands for monorepo builds.

### Required environment variables

Backend (Railway):
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_MINI_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `FRONTEND_URL` (your Vercel app URL, used for CORS/OAuth redirects)
- `CELERY_BROKER_URL` (Railway Redis URL, usually `/0`)
- `CELERY_RESULT_BACKEND` (Railway Redis URL, usually `/1`)
- `MERGE_API_KEY` (if using accounting integrations)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (if using Gmail)
- Optional: `LOG_LEVEL`, `ENVIRONMENT`

Frontend (Vercel):
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_URL` (your Railway API URL, e.g. `https://<api>.up.railway.app`)

### First rollout smoke test

1. Deploy Railway `api`, `worker-beat`, and `redis`; confirm `/api/health` returns `{"status":"ok"}`.
2. Deploy Vercel frontend and confirm login/chat pages load.
3. Send one chat message and verify API logs show request start/end with request IDs.
4. Trigger a workflow and confirm `worker-beat` logs show task start/completion.
5. Open activity panel in frontend and confirm SSE reconnects and events stream.

### Rollback path

- Keep previous Railway deployment active; rollback from Railway deployment history for `api` and `worker-beat`.
- Roll back Vercel from deployment history.
- If needed, revert env changes (`NEXT_PUBLIC_API_URL`, `FRONTEND_URL`) to last known good values.
