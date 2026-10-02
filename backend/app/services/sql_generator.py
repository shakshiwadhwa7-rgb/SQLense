"""SQL generation service using Groq API."""

import re
import time

import groq

from app.core.config import settings
from app.services.sql_validator import validate_sql, validate_sql_against_schema


SYSTEM_PROMPT = """You are an expert SQL generator. Your task is to convert natural language questions into valid SQL queries.

CRITICAL RULES:
1. Use ONLY the tables and columns that are explicitly defined in the provided schema.
2. Do NOT invent, assume, or reference any tables or columns not present in the schema.
3. Return ONLY the SQL query — no markdown code fences, no explanations, no comments.
4. Ensure the SQL is syntactically correct and ready to execute.
5. If the question cannot be answered with the given schema, return an empty string.

Schema:
{schema}"""

MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 2.0


class GroqUnavailableError(RuntimeError):
    """Raised when Groq is unavailable after all retry attempts."""


def _get_client() -> groq.Groq:
    """Create and return a Groq client."""
    return groq.Groq(api_key=settings.GROQ_API_KEY)


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception represents a temporary 503/UNAVAILABLE error."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 503:
        return True

    code = getattr(exc, "code", None)
    if code == 503:
        return True

    exc_str = str(exc).upper()
    if "503" in exc_str or "UNAVAILABLE" in exc_str:
        return True

    return False


def _strip_markdown_fences(sql: str) -> str:
    """Remove markdown code fences if the model included them."""
    sql = sql.strip()
    match = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", sql, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
    return sql


def generate_sql(question: str, schema: str) -> str:
    """Generate a SQL query from a natural language question and schema.

    Args:
        question: Natural language question about the database.
        schema: Database schema definition.

    Returns:
        A valid SQL query string.

    Raises:
        ValueError: If the question or schema is empty, or if the generated
            SQL is empty, invalid, not read-only, or references tables or
            columns outside the provided schema.
        GroqUnavailableError: If Groq is unavailable after all retries.
        RuntimeError: If the Groq API call fails for a non-retryable reason.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")
    if not schema or not schema.strip():
        raise ValueError("Schema cannot be empty")

    try:
        client = _get_client()
    except Exception as e:
        raise RuntimeError(f"Groq client initialization failed: {e}") from e

    last_exception: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema)},
                    {"role": "user", "content": question},
                ],
                temperature=0,
                max_tokens=500,
            )
            break
        except Exception as e:
            last_exception = e
            if not _is_retryable_error(e):
                raise RuntimeError(f"Groq API call failed: {e}") from e
            if attempt < MAX_RETRIES:
                time.sleep(BASE_BACKOFF_SECONDS * (2**attempt))
    else:
        raise GroqUnavailableError(
            f"Groq unavailable after {MAX_RETRIES + 1} attempts: {last_exception}"
        ) from last_exception

    sql = response.choices[0].message.content or ""
    sql = _strip_markdown_fences(sql)
    sql = validate_sql(sql)
    sql = validate_sql_against_schema(sql, schema)

    return sql
