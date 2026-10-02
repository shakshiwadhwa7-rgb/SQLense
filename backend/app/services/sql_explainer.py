"""SQL explanation service using Groq API."""

from app.services import sql_generator
from app.services.sql_validator import validate_sql

EXPLAIN_SYSTEM_PROMPT = """You are an expert SQL instructor. Explain the given SQL query to a beginner.

CRITICAL RULES:
1. Explain what the query does in plain language, step by step.
2. Walk through each clause (SELECT, FROM, WHERE, JOIN, GROUP BY, HAVING, ORDER BY, LIMIT, etc.) in the order it is logically evaluated.
3. Explain any functions, operators, and conditions that are used.
4. Keep the language clear and beginner-friendly; avoid unexplained jargon.
5. Do NOT execute the query and do not claim to have run it.
6. Return only the explanation as plain text — no markdown code fences."""


def explain_sql(sql: str) -> str:
    """Generate a beginner-friendly, step-by-step explanation of a SQL query.

    The SQL is validated (read-only, parseable) before any explanation is
    requested. No SQL is executed against any database.

    Args:
        sql: The SQL query to explain.

    Returns:
        A plain-text explanation of the query.

    Raises:
        ValueError: If the SQL is empty, invalid, or not read-only.
        RuntimeError: If the Groq API call fails.
    """
    sql = validate_sql(sql)

    try:
        client = sql_generator._get_client()
    except Exception as e:
        raise RuntimeError(f"Groq client initialization failed: {e}") from e

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
                {"role": "user", "content": sql},
            ],
            temperature=0,
            max_tokens=1024,
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed: {e}") from e

    explanation = response.choices[0].message.content or ""
    return sql_generator._strip_markdown_fences(explanation)
