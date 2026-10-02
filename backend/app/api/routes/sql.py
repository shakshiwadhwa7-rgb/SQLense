"""SQL generation API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.sql import SQLGenerateRequest, SQLGenerateResponse
from app.services.sql_generator import GroqUnavailableError, generate_sql

router = APIRouter()


@router.post("/generate", response_model=SQLGenerateResponse)
async def generate_sql_endpoint(request: SQLGenerateRequest):
    """Generate a SQL query from a natural language question and schema."""
    try:
        sql = generate_sql(question=request.question, schema=request.schema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GroqUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return SQLGenerateResponse(sql=sql)
