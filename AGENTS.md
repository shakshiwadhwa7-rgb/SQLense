# AGENTS.md

## Project Overview

SQLense is an AI-powered SQL database copilot. Users ask questions about their database in natural language; the system generates, explains, debugs, optimizes, and eventually executes SQL queries.

**Status:** Backend-first MVP. React frontend comes later.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| API Framework | FastAPI |
| LLM | OpenAI API |
| Database | PostgreSQL |
| Vector Store | ChromaDB (for RAG) |
| Frontend (future) | React |

## Architecture Principles

- **Clean & modular** — separate concerns into distinct packages (e.g., `api/`, `services/`, `db/`, `llm/`, `rag/`)
- **Beginner-friendly** — favor explicit, readable code over clever abstractions
- **Production-quality MVP** — write tests, handle errors gracefully, use Pydantic models for I/O
- **RAG pipeline** — use ChromaDB to store and retrieve schema context, query examples, and documentation to improve SQL generation

## Key Directories (planned)

```
SQLense/
├── backend/
│   ├── app/
│   │   ├── api/       # FastAPI routes and endpoints
│   │   ├── core/      # Config, logging, dependencies
│   │   ├── db/        # PostgreSQL connection (async engine, sessions)
│   │   ├── schemas/   # Pydantic request/response models
│   │   ├── services/  # Business logic (generation, explanation, validation, practice)
│   │   ├── llm/       # (planned) LLM client and prompt management
│   │   └── rag/       # (planned) ChromaDB integration, retrieval
│   ├── tests/
│   ├── alembic/       # (planned) Database migrations
│   └── requirements.txt
├── frontend/          # (planned) React app
├── docs/
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

## Conventions

- Use **Pydantic v2** models for all request/response validation
- Use **async** database drivers (e.g., `asyncpg` + SQLAlchemy async)
- Store all LLM prompts as versioned templates, not inline strings
- Use **Alembic** for PostgreSQL schema migrations
- Environment config via `.env` file (see `.env.example`)
- Log structured events; never log raw SQL with sensitive data

## Development Commands

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run the API dev server (run this from backend/)
cd backend
uvicorn app.main:app --reload

# Run tests (run this from the repository root)
pytest

# Run tests with coverage
pytest --cov=app

# Lint & format
ruff check .
ruff format .

# Type check
mypy backend/app

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Important Notes

- **Never execute user-generated SQL in production** without a safety layer (read-only mode, query allowlisting, or dry-run by default)
- ChromaDB collections should be namespaced per database/schema to avoid cross-contamination
- OpenAI API keys and DB credentials must only come from environment variables, never hardcoded
- Keep prompts and RAG retrieval decoupled so the LLM provider can be swapped later
