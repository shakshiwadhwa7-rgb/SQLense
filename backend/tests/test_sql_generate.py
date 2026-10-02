"""Tests for the SQL generation endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_generate_sql_success():
    """Test successful SQL generation with valid input (mocked Groq)."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        "SELECT * FROM employee WHERE department = 'Sales';"
    )

    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/generate",
            json={
                "question": "Find all employees in the Sales department.",
                "schema": "employee(emp_id INT, name VARCHAR, department VARCHAR, salary INT)",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "sql" in data
    assert isinstance(data["sql"], str)
    assert len(data["sql"]) > 0


def test_generate_sql_empty_question():
    """Test validation error for empty question."""
    response = client.post(
        "/api/v1/sql/generate",
        json={
            "question": "",
            "schema": "employee(emp_id INT, name VARCHAR)",
        },
    )
    assert response.status_code == 422


def test_generate_sql_empty_schema():
    """Test validation error for empty schema."""
    response = client.post(
        "/api/v1/sql/generate",
        json={
            "question": "Find all employees.",
            "schema": "",
        },
    )
    assert response.status_code == 422


def test_generate_sql_whitespace_question():
    """Test validation error for whitespace-only question."""
    response = client.post(
        "/api/v1/sql/generate",
        json={
            "question": "   ",
            "schema": "employee(emp_id INT, name VARCHAR)",
        },
    )
    assert response.status_code == 422


def test_generate_sql_missing_fields():
    """Test validation error when required fields are missing."""
    response = client.post("/api/v1/sql/generate", json={})
    assert response.status_code == 422


def test_generate_sql_groq_failure():
    """Test error handling when Groq API fails."""
    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/generate",
            json={
                "question": "Find all employees.",
                "schema": "employee(emp_id INT, name VARCHAR)",
            },
        )

    assert response.status_code == 502


def test_generate_sql_retry_success():
    """Test that a retry succeeds after a transient 503 error."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "SELECT * FROM employee;"

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.services.sql_generator.time.sleep"),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("503 Service Unavailable"),
            mock_response,
        ]
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/generate",
            json={
                "question": "Find all employees.",
                "schema": "employee(emp_id INT, name VARCHAR)",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "sql" in data
    assert len(data["sql"]) > 0


def test_generate_sql_retry_exhausted():
    """Test that exhausted retries return 503."""
    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.services.sql_generator.time.sleep"),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception(
            "503 Service Unavailable"
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/sql/generate",
            json={
                "question": "Find all employees.",
                "schema": "employee(emp_id INT, name VARCHAR)",
            },
        )

    assert response.status_code == 503
