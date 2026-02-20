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

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask run --port 5000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:3000` and the backend on `http://localhost:5000`.
