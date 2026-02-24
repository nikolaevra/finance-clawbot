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
