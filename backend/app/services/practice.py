"""Practice Mode services: question generation and SQL evaluation."""

import sqlglot
from sqlglot.errors import ErrorLevel
from sqlglot.optimizer.qualify import qualify

from app.services import sql_generator, sql_validator
from app.services.sql_validator import validate_sql, validate_sql_against_schema

GENERATE_SYSTEM_PROMPT = """You are an expert SQL instructor creating practice questions for beginners.

Given a topic, a difficulty level, and a database schema, write ONE clear practice question that a learner can answer with a single read-only SQL query.

CRITICAL RULES:
1. Use only tables and columns that are present in the provided schema.
2. The question must be answerable with a single SELECT query.
3. Match the requested difficulty: easy = simple filtering; medium = joins or aggregation; hard = CTEs, subqueries, or window functions.
4. Return ONLY the question text — no markdown, no code fences, no solution, no extra commentary."""

REFERENCE_SYSTEM_PROMPT = """You are an expert SQL writer. Answer the given practice question with a single read-only SQL query.

CRITICAL RULES:
1. Use ONLY the tables and columns that are explicitly defined in the provided schema.
2. Do NOT invent tables or columns not present in the schema.
3. Return ONLY the SQL query — no markdown code fences, no explanations, no comments.
4. The query must be syntactically correct and ready to execute."""

FEEDBACK_SYSTEM_PROMPT = """You are a friendly SQL instructor reviewing a learner's attempt at a practice question.

Given the practice question, the database schema, the reference solution, and the learner's SQL attempt, write beginner-friendly, step-by-step feedback:
1. Point out what the learner got right.
2. Explain what is wrong or missing and why, in simple terms.
3. Give a clear hint or explanation that leads toward the reference solution.
4. Plain text only — no markdown code fences."""

SUCCESS_FEEDBACK = (
    "Correct! Your query is logically equivalent to the reference solution. "
    "Well done — you solved the practice question!"
)
SYNTAX_FEEDBACK = (
    "Your SQL could not be parsed, so there is a syntax error. Check keywords, "
    "commas, parentheses, and that every table and column matches the schema, "
    "then try again."
)
EMPTY_FEEDBACK_FALLBACK = (
    "Your query differs from the reference solution. Compare them clause by "
    "clause to see where they diverge."
)


def _chat(system_prompt: str, user_content: str, max_tokens: int) -> str:
    """One Groq chat completion using the existing client/model configuration."""
    try:
        client = sql_generator._get_client()
    except Exception as e:
        raise RuntimeError(f"Groq client initialization failed: {e}") from e

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed: {e}") from e

    return response.choices[0].message.content or ""


def generate_practice(topic: str, difficulty: str, schema: str) -> str:
    """Generate a practice question for a topic, difficulty, and schema.

    Args:
        topic: The SQL topic to practice (e.g. "JOINs").
        difficulty: The difficulty level (e.g. "medium").
        schema: The database schema the question must use.

    Returns:
        The generated question text.

    Raises:
        ValueError: If any input is empty.
        RuntimeError: If Groq fails or returns an empty question.
    """
    if not topic.strip():
        raise ValueError("Topic cannot be empty")
    if not difficulty.strip():
        raise ValueError("Difficulty cannot be empty")
    if not schema.strip():
        raise ValueError("Schema cannot be empty")

    user_content = f"Topic: {topic}\nDifficulty: {difficulty}\nSchema: {schema}"
    question = sql_generator._strip_markdown_fences(
        _chat(GENERATE_SYSTEM_PROMPT, user_content, max_tokens=500)
    ).strip()

    if not question:
        raise RuntimeError("Groq returned an empty practice question")
    return question


def _canonicalize(sql: str, sqlglot_schema: dict) -> str | None:
    """Canonical form of a SQL string for logical comparison.

    Uses sqlglot's qualify to expand stars and fully qualify columns against
    the schema, falling back to the raw parse tree if qualification fails.
    Returns None if the SQL cannot be parsed. Never executes anything.
    """
    try:
        expr = sqlglot.parse_one(sql, error_level=ErrorLevel.RAISE)
    except Exception:
        return None
    try:
        expr = qualify(expr, schema=sqlglot_schema, validate_qualify_columns=False)
    except Exception:
        pass  # fall back to the raw parse tree
    return expr.sql()


def _feedback(question: str, schema: str, reference_sql: str, user_sql: str) -> str:
    """Get beginner-friendly feedback from the LLM for a wrong attempt."""
    user_content = (
        f"Practice question:\n{question}\n\n"
        f"Schema:\n{schema}\n\n"
        f"Reference solution:\n{reference_sql}\n\n"
        f"Learner's SQL:\n{user_sql}"
    )
    feedback = sql_generator._strip_markdown_fences(
        _chat(FEEDBACK_SYSTEM_PROMPT, user_content, max_tokens=1024)
    ).strip()
    return feedback or EMPTY_FEEDBACK_FALLBACK


def evaluate_practice(question: str, schema: str, user_sql: str) -> tuple[bool, str, str]:
    """Evaluate a learner's SQL against a reference solution — no execution.

    The reference solution is produced by the LLM and validated with the
    existing validators. Correctness is decided logically by comparing
    sqlglot-canonical forms of the reference and the learner's SQL.

    Args:
        question: The practice question being answered.
        schema: The database schema for the question.
        user_sql: The learner's SQL answer.

    Returns:
        A tuple of (correct, feedback, reference_sql).

    Raises:
        ValueError: If inputs are empty or the schema cannot be parsed.
        RuntimeError: If Groq fails or returns invalid reference SQL.
    """
    if not question.strip():
        raise ValueError("Question cannot be empty")
    if not schema.strip():
        raise ValueError("Schema cannot be empty")
    if not user_sql.strip():
        raise ValueError("User SQL cannot be empty")

    schema_map = sql_validator._parse_schema(schema)
    if not schema_map:
        raise ValueError("Could not parse schema into tables and columns")
    sqlglot_schema = {
        table: {col: "TEXT" for col in sorted(cols)}
        for table, cols in schema_map.items()
    }

    # 1. Reference solution from the LLM, validated with existing validators.
    raw_reference = _chat(
        REFERENCE_SYSTEM_PROMPT,
        f"Practice question:\n{question}\n\nSchema:\n{schema}",
        max_tokens=500,
    )
    reference_sql = sql_generator._strip_markdown_fences(raw_reference).strip()
    try:
        validate_sql(reference_sql)
        validate_sql_against_schema(reference_sql, schema)
    except ValueError as e:
        raise RuntimeError(f"Groq returned invalid reference SQL: {e}") from e

    # 2. Logical comparison with sqlglot (never executing SQL).
    user_canonical = _canonicalize(user_sql, sqlglot_schema)
    if user_canonical is None:
        return False, SYNTAX_FEEDBACK, reference_sql

    reference_canonical = _canonicalize(reference_sql, sqlglot_schema)
    if user_canonical == reference_canonical:
        return True, SUCCESS_FEEDBACK, reference_sql

    # 3. Not equivalent — beginner-friendly feedback from the LLM.
    feedback = _feedback(question, schema, reference_sql, user_sql)
    return False, feedback, reference_sql
