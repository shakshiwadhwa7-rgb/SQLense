"""SQL generation API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.sql import SQLGenerateRequest, SQLGenerateResponse
from app.services.history import HistoryPersistenceError, save_generation
from app.services.sql_generator import GroqUnavailableError, generate_sql

router = APIRouter()


@router.post("/generate", response_model=SQLGenerateResponse)
async def generate_sql_endpoint(request: SQLGenerateRequest):
    """Generate a SQL query from a natural language question and schema.

    Successful generations are persisted to ``sql_history`` before the
    response is returned; persistence failures surface as HTTP 500.
    """
    try:
        sql = generate_sql(question=request.question, schema=request.schema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GroqUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        await save_generation(
            question=request.question,
            schema=request.schema,
            sql=sql,
        )
    except HistoryPersistenceError as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist the generated SQL history",
        ) from e

    return SQLGenerateResponse(sql=sql)
