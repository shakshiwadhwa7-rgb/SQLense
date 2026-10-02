"""Tests for the SQL explanation endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_explain_success():
    """Test successful SQL explanation with valid input (mocked Groq)."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        "Step 1: The SELECT clause picks the columns. Step 2: ..."
    )

    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/explain",
            json={"sql": "SELECT name FROM employee WHERE salary > 1000;"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "explanation" in data
    assert isinstance(data["explanation"], str)
    assert len(data["explanation"]) > 0


def test_explain_strips_markdown_fences():
    """Fences around the explanation are stripped."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "```This query selects rows.```"

    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/explain",
            json={"sql": "SELECT name FROM employee;"},
        )

    assert response.status_code == 200
    assert response.json()["explanation"] == "This query selects rows."


def test_explain_rejects_write_statement():
    """Non-read-only SQL is rejected before any explanation."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        response = client.post(
            "/api/v1/sql/explain",
            json={"sql": "DROP TABLE employee"},
        )

    assert response.status_code == 400
    mock_get_client.assert_not_called()


def test_explain_rejects_invalid_sql():
    """Syntactically invalid SQL is rejected."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        response = client.post(
            "/api/v1/sql/explain",
            json={"sql": "SELECT * FROM"},
        )

    assert response.status_code == 400
    mock_get_client.assert_not_called()


def test_explain_empty_sql():
    """Empty SQL fails request validation."""
    response = client.post("/api/v1/sql/explain", json={"sql": ""})
    assert response.status_code == 422


def test_explain_whitespace_sql():
    """Whitespace-only SQL fails request validation."""
    response = client.post("/api/v1/sql/explain", json={"sql": "   "})
    assert response.status_code == 422


def test_explain_missing_field():
    """Missing sql field fails request validation."""
    response = client.post("/api/v1/sql/explain", json={})
    assert response.status_code == 422


def test_explain_groq_failure():
    """Groq API failure returns 502."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/explain",
            json={"sql": "SELECT name FROM employee;"},
        )

    assert response.status_code == 502
