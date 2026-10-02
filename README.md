# SQLense

**AI-powered SQL database copilot.** Ask your database questions in natural language — SQLense generates the SQL, explains it, validates it against your schema, and helps you practice with auto-graded exercises.

## Purpose

SQL makes databases powerful, but writing SQL is slow and error-prone — especially for beginners. SQLense turns plain-English questions into trustworthy SQL and explains existing queries in beginner-friendly language, with safety built in at every step: only read-only statements are accepted, and user SQL is **never executed** by the service.

## Current Features

| Feature | Endpoint | What it does |
|---------|----------|--------------|
| Health check | `GET /health` | Service liveness probe |
| SQL generation | `POST /api/v1/sql/generate` | Natural language question + schema → read-only SQL (`{question, schema}` → `{sql}`) |
| SQL explanation | `POST /api/v1/sql/explain` | SQL → plain-English explanation (`{sql}` → `{explanation}`) |
| Schema validation | built in | Two layers: read-only statement checks + schema-aware table/column checks |
| Practice question | `POST /api/v1/practice/generate` | `{topic, difficulty, schema}` → `{question, schema}` |
| Practice evaluation | `POST /api/v1/practice/evaluate` | `{question, schema, user_sql}` → `{correct, feedback, reference_sql}` — compared logically with SQLGlot, never executed |
| Database foundation | `check_connection()` | Async engine, session factory, read-only `SELECT 1` check |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| API framework | FastAPI + Pydantic v2 |
| LLM | Groq — `openai/gpt-oss-120b` |
| SQL analysis | SQLGlot |
| Database | Supabase PostgreSQL (SQLAlchemy 2.x async + asyncpg) |
| Testing | pytest (all external calls mocked) |
| Frontend (planned) | React |

## Architecture

```
SQLense/
├── backend/
│   ├── app/
│   │   ├── api/routes/    # FastAPI endpoints (health, sql, explain, practice)
│   │   ├── core/          # Settings — environment configuration
│   │   ├── db/            # Async engine, session factory, SELECT 1 check
│   │   ├── schemas/       # Pydantic request/response models
│   │   └── services/      # SQL generation, validation, explanation, practice
│   ├── tests/             # 70 tests — no network, no credentials required
│   └── requirements.txt
├── frontend/              # React app (planned)
├── docs/                  # Project documentation
├── .env.example           # Environment template (copy to .env)
├── .gitignore
├── AGENTS.md
└── README.md
```

Requests flow **route → service → (Groq / SQLGlot)** with Pydantic models at the boundaries. Services are decoupled from the LLM provider so it can be swapped later.

## Supabase PostgreSQL

- Connection settings live in `.env` at the repository root (`DATABASE_URL`) — `.env` is git-ignored and must never be committed.
- The database foundation (`backend/app/db/database.py`) converts `postgresql://` URLs to `postgresql+asyncpg://` for SQLAlchemy and enables SSL (`ssl=require`) for Supabase automatically.
- It provides an async engine, an async session factory, and a simple read-only `SELECT 1` connection check.
- No tables, models, or migrations exist yet — this is connection foundation only.

## Groq

- All LLM features (generation, explanation, practice feedback) run on Groq with the `openai/gpt-oss-120b` model.
- The API key is read from `GROQ_API_KEY` in `.env` — never hardcoded.
- Transient failures are retried with exponential backoff; tests mock every Groq call, so the suite runs without a key.

## SQLGlot

SQLGlot is SQLense's safety and analysis layer. It never executes anything:

- **Read-only validation** — only `SELECT` statements (including CTEs) are accepted; DDL/DML are rejected.
- **Schema validation** — unknown tables and columns are caught before SQL is returned.
- **Logical comparison** — Practice Mode canonicalizes both the learner's answer and the reference solution (star expansion, column qualification) to decide correctness without a database.

## Backend Setup

```bash
git clone https://github.com/shakshiwadhwa7-rgb/SQLense.git
cd SQLense
pip install -r backend/requirements.txt

# Create your environment file and fill in the values (never commit it)
cp .env.example .env

cd backend
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000` (interactive docs at `/docs`). The `.env` file stays at the repository root and is found automatically regardless of the working directory.

## Testing

```bash
# from the repository root
python -m pytest backend/tests
```

The full suite (70 tests) runs in about two seconds. Every LLM call is mocked and database tests open no connections — no API keys, no network, no Supabase access required.

## Future Frontend

A React application will live in `frontend/` and consume this backend's API. Only a placeholder README exists today — no frontend application code yet. `docs/` holds future project documentation.
