"""Practice Mode API routes."""

from fastapi import APIRouter, HTTPException

from app.schemas.practice import (
    PracticeEvaluateRequest,
    PracticeEvaluateResponse,
    PracticeGenerateRequest,
    PracticeGenerateResponse,
)
from app.services.practice import evaluate_practice, generate_practice
from app.services.practice_persistence import (
    PracticePersistenceError,
    save_practice_attempt,
    save_practice_question,
)

router = APIRouter()


@router.post("/generate", response_model=PracticeGenerateResponse)
async def practice_generate_endpoint(request: PracticeGenerateRequest):
    """Generate a SQL practice question for a topic and difficulty."""
    try:
        question, reference_sql = generate_practice(
            topic=request.topic,
            difficulty=request.difficulty,
            schema=request.schema,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Persist only after generation + reference validation succeeded.
    try:
        question_id = await save_practice_question(
            question=question,
            schema=request.schema,
            reference_sql=reference_sql,
            difficulty=request.difficulty,
            topic=request.topic,
        )
    except PracticePersistenceError:
        raise HTTPException(
            status_code=500, detail="Failed to persist the practice question"
        )

    return PracticeGenerateResponse(
        question=question, schema=request.schema, question_id=question_id
    )


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

    # Persist only after evaluation produced its result.
    try:
        await save_practice_attempt(
            question_id=request.question_id,
            submitted_sql=request.user_sql,
            correct=correct,
            feedback=feedback,
        )
    except PracticePersistenceError:
        raise HTTPException(
            status_code=500, detail="Failed to persist the practice attempt"
        )

    return PracticeEvaluateResponse(
        correct=correct,
        feedback=feedback,
        reference_sql=reference_sql,
    )
