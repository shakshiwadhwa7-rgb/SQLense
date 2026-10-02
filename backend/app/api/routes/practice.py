"""Practice Mode API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.practice import (
    PracticeEvaluateRequest,
    PracticeEvaluateResponse,
    PracticeGenerateRequest,
    PracticeGenerateResponse,
)
from app.services.practice import evaluate_practice, generate_practice

router = APIRouter()


@router.post("/generate", response_model=PracticeGenerateResponse)
async def practice_generate_endpoint(request: PracticeGenerateRequest):
    """Generate a SQL practice question for a topic and difficulty."""
    try:
        question = generate_practice(
            topic=request.topic,
            difficulty=request.difficulty,
            schema=request.schema,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return PracticeGenerateResponse(question=question, schema=request.schema)


@router.post("/evaluate", response_model=PracticeEvaluateResponse)
async def practice_evaluate_endpoint(request: PracticeEvaluateRequest):
    """Evaluate a learner's SQL against a reference solution (no execution)."""
    try:
        correct, feedback, reference_sql = evaluate_practice(
            question=request.question,
            schema=request.schema,
            user_sql=request.user_sql,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return PracticeEvaluateResponse(
        correct=correct,
        feedback=feedback,
        reference_sql=reference_sql,
    )
