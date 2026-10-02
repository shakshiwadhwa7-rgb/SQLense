# SQLense Backend

FastAPI service powering SQLense: SQL generation, explanation, validation, and Practice Mode — plus the async Supabase database foundation.

## Layout

```
backend/
├── app/
│   ├── api/routes/    # health.py, sql.py, explain.py, practice.py
│   ├── core/          # config.py — Settings loaded from the root .env
│   ├── db/            # database.py — async engine, session factory, SELECT 1 check
│   ├── schemas/       # sql.py, practice.py — Pydantic request/response models
│   └── services/      # sql_generator, sql_validator, sql_explainer, practice
├── tests/             # pytest suite (all external calls mocked)
└── requirements.txt
```

## API Endpoints

| Method | Path | Request → Response |
|--------|------|--------------------|
| GET | `/health` | service liveness |
| POST | `/api/v1/sql/generate` | `{question, schema}` → `{sql}` |
| POST | `/api/v1/sql/explain` | `{sql}` → `{explanation}` |
| POST | `/api/v1/practice/generate` | `{topic, difficulty, schema}` → `{question, schema}` |
| POST | `/api/v1/practice/evaluate` | `{question, schema, user_sql}` → `{correct, feedback, reference_sql}` |

## Running

```bash
# from the repository root
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

Configuration comes from `.env` at the repository root (`GROQ_API_KEY`, `DATABASE_URL`) — see `.env.example`. It is resolved relative to the repository, so the server can be started from any working directory.

## Testing

```bash
# from the repository root
python -m pytest backend/tests
```

## Design Rules

- **Never execute SQL** — queries are parsed and analyzed with SQLGlot only.
- **Read-only by default** — only `SELECT` statements pass validation.
- **Fail closed** — schemas that cannot be parsed are rejected.
- **Mocked LLM calls** — no test performs a real Groq API call.
- **Credentials stay in `.env`** — never in code, tests, or tracked files.
