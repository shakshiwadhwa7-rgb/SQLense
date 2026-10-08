"""Tests for Practice Mode endpoints (all Groq calls mocked)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SCHEMA = "employee(emp_id INT, name VARCHAR, department VARCHAR, salary INT)"
REF_SQL = "SELECT name FROM employee WHERE salary > 1000"


def _groq_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = text
    return resp


# --- POST /api/v1/practice/generate ---


def test_practice_generate_success():
    """One structured-output Groq call returns the question + reference SQL."""
    save_mock = AsyncMock(return_value=uuid.uuid4())
    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            json.dumps(
                {
                    "question": "Which employees earn more than 1000?",
                    "reference_sql": REF_SQL,
                }
            )
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/generate",
            json={"topic": "JOINs", "difficulty": "medium", "schema": SCHEMA},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "Which employees earn more than 1000?"
    assert data["schema"] == SCHEMA

    # Exactly one Groq call, strict structured output, temperature 0.
    create = mock_client.chat.completions.create
    assert create.call_count == 1
    kwargs = create.call_args.kwargs
    assert kwargs["temperature"] == 0
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True

    sent = kwargs["messages"][1]["content"]
    assert "JOINs" in sent
    assert "medium" in sent
    assert SCHEMA in sent


def test_practice_generate_strips_fences():
    """Fences inside the structured question field are stripped."""
    save_mock = AsyncMock(return_value=uuid.uuid4())
    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            json.dumps(
                {
                    "question": "```What is the average salary?```",
                    "reference_sql": REF_SQL,
                }
            )
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/generate",
            json={"topic": "aggregates", "difficulty": "easy", "schema": SCHEMA},
        )

    assert response.status_code == 200
    assert response.json()["question"] == "What is the average salary?"


def test_practice_generate_malformed_output_returns_502():
    """Unparseable structured output -> RuntimeError -> 502."""
    save_mock = AsyncMock(return_value=uuid.uuid4())
    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            "this is not JSON at all"
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/generate",
            json={"topic": "JOINs", "difficulty": "medium", "schema": SCHEMA},
        )

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_practice_generate_incomplete_output_returns_502():
    """Structured output missing a required field -> 502."""
    save_mock = AsyncMock(return_value=uuid.uuid4())
    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            json.dumps({"question": "Which employees earn more than 1000?"})
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/generate",
            json={"topic": "JOINs", "difficulty": "medium", "schema": SCHEMA},
        )

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_practice_generate_groq_failure():
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/generate",
            json={"topic": "JOINs", "difficulty": "medium", "schema": SCHEMA},
        )

    assert response.status_code == 502


def test_practice_generate_empty_topic():
    response = client.post(
        "/api/v1/practice/generate",
        json={"topic": "   ", "difficulty": "medium", "schema": SCHEMA},
    )
    assert response.status_code == 422


def test_practice_generate_missing_field():
    response = client.post("/api/v1/practice/generate", json={})
    assert response.status_code == 422


# --- POST /api/v1/practice/evaluate ---


def test_practice_evaluate_correct():
    """Equivalent SQL (case/whitespace differences) is marked correct."""
    user_sql = "select name from employee\nwhere salary > 1000;"

    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(REF_SQL)
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={
                "question": "Which employees earn more than 1000?",
                "schema": SCHEMA,
                "user_sql": user_sql,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["correct"] is True
    assert data["reference_sql"] == REF_SQL
    assert len(data["feedback"]) > 0
    # Only the reference call — no feedback call needed when correct.
    assert mock_client.chat.completions.create.call_count == 1


def test_practice_evaluate_incorrect_gets_llm_feedback():
    user_sql = "SELECT name FROM employee WHERE salary > 2000"

    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _groq_response(REF_SQL),
            _groq_response("You compared against 2000, but the question asks for 1000."),
        ]
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={
                "question": "Which employees earn more than 1000?",
                "schema": SCHEMA,
                "user_sql": user_sql,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["correct"] is False
    assert data["feedback"] == (
        "You compared against 2000, but the question asks for 1000."
    )
    assert data["reference_sql"] == REF_SQL
    assert mock_client.chat.completions.create.call_count == 2


def test_practice_evaluate_syntax_error():
    """Unparseable user SQL -> incorrect with syntax feedback, one LLM call."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(REF_SQL)
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={
                "question": "Which employees earn more than 1000?",
                "schema": SCHEMA,
                "user_sql": "SELECT * FROM",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["correct"] is False
    assert "syntax" in data["feedback"].lower()
    assert mock_client.chat.completions.create.call_count == 1


def test_practice_evaluate_write_user_sql():
    """A write statement is never executed; it is simply not equivalent."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _groq_response(REF_SQL),
            _groq_response("Practice answers must be SELECT queries."),
        ]
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={
                "question": "Which employees earn more than 1000?",
                "schema": SCHEMA,
                "user_sql": "DELETE FROM employee",
            },
        )

    assert response.status_code == 200
    assert response.json()["correct"] is False


def test_practice_evaluate_invalid_reference():
    """LLM reference SQL failing validation -> 502."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            "DROP TABLE employee"
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={
                "question": "Which employees earn more than 1000?",
                "schema": SCHEMA,
                "user_sql": "SELECT name FROM employee WHERE salary > 1000",
            },
        )

    assert response.status_code == 502
    assert mock_client.chat.completions.create.call_count == 1


def test_practice_evaluate_unparseable_schema():
    """Bad schema -> 400 before any LLM call."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        response = client.post(
            "/api/v1/practice/evaluate",
            json={
                "question": "Anything?",
                "schema": "not a schema at all",
                "user_sql": "SELECT 1",
            },
        )

    assert response.status_code == 400
    mock_get_client.assert_not_called()


def test_practice_evaluate_empty_user_sql():
    response = client.post(
        "/api/v1/practice/evaluate",
        json={
            "question": "q",
            "schema": SCHEMA,
            "user_sql": "   ",
        },
    )
    assert response.status_code == 422


def test_practice_evaluate_missing_fields():
    response = client.post("/api/v1/practice/evaluate", json={})
    assert response.status_code == 422
