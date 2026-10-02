"""SQL explanation API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.sql import SQLExplainRequest, SQLExplainResponse
from app.services.sql_explainer import explain_sql

router = APIRouter()


@router.post("/explain", response_model=SQLExplainResponse)
async def explain_sql_endpoint(request: SQLExplainRequest):
    """Explain a SQL query in beginner-friendly, step-by-step language."""
    try:
        explanation = explain_sql(sql=request.sql)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return SQLExplainResponse(explanation=explanation)
