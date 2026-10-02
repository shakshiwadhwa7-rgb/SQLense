"""Pydantic models for SQL generation requests and responses."""

from pydantic import BaseModel, Field, field_validator


class SQLGenerateRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="Natural language question about the database",
    )
    schema: str = Field(
        ...,
        min_length=1,
        description="Database schema definition (e.g., CREATE TABLE statements)",
    )

    @field_validator("question", "schema")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace-only")
        return stripped


class SQLGenerateResponse(BaseModel):
    sql: str = Field(..., description="Generated SQL query")


class SQLExplainRequest(BaseModel):
    sql: str = Field(
        ...,
        min_length=1,
        description="SQL query to explain",
    )

    @field_validator("sql")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace-only")
        return stripped


class SQLExplainResponse(BaseModel):
    explanation: str = Field(
        ...,
        description="Beginner-friendly explanation of the SQL query",
    )
