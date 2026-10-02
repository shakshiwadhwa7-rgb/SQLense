"""Pydantic models for Practice Mode requests and responses."""

from pydantic import BaseModel, Field, field_validator


class PracticeGenerateRequest(BaseModel):
    topic: str = Field(
        ...,
        min_length=1,
        description="Topic for the practice question (e.g. JOINs)",
    )
    difficulty: str = Field(
        ...,
        min_length=1,
        description="Difficulty level (e.g. easy, medium, hard)",
    )
    schema: str = Field(
        ...,
        min_length=1,
        description="Database schema the question must use",
    )

    @field_validator("topic", "difficulty", "schema")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace-only")
        return stripped


class PracticeGenerateResponse(BaseModel):
    question: str = Field(..., description="Generated practice question")
    schema: str = Field(..., description="Schema the question applies to")


class PracticeEvaluateRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="The practice question being answered",
    )
    schema: str = Field(
        ...,
        min_length=1,
        description="Database schema for the question",
    )
    user_sql: str = Field(
        ...,
        min_length=1,
        description="The learner's SQL answer",
    )

    @field_validator("question", "schema", "user_sql")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace-only")
        return stripped


class PracticeEvaluateResponse(BaseModel):
    correct: bool = Field(..., description="Whether the learner's SQL is correct")
    feedback: str = Field(..., description="Beginner-friendly feedback")
    reference_sql: str = Field(..., description="Reference solution for the question")
