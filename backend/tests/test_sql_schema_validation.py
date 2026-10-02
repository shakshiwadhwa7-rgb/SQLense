"""Tests for schema-aware SQL validation."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.sql_validator import validate_sql_against_schema

SCHEMA = (
    "employee(emp_id INT, name VARCHAR, department VARCHAR, salary INT), "
    "department(name VARCHAR, budget INT)"
)


def test_valid_select():
    sql = "SELECT emp_id, name FROM employee WHERE salary > 1000;"
    assert validate_sql_against_schema(sql, SCHEMA) == sql


def test_valid_alias_and_join():
    sql = (
        "SELECT e.*, d.budget FROM employee e "
        "JOIN department d ON e.department = d.name"
    )
    assert validate_sql_against_schema(sql, SCHEMA) == sql


def test_valid_cte():
    sql = (
        "WITH dept_avg AS (SELECT department, AVG(salary) AS avg_sal "
        "FROM employee GROUP BY department) "
        "SELECT department, avg_sal FROM dept_avg"
    )
    assert validate_sql_against_schema(sql, SCHEMA) == sql


def test_valid_aggregate_window_subquery():
    sql = (
        "SELECT name, RANK() OVER (ORDER BY salary DESC) AS rnk "
        "FROM employee WHERE salary > (SELECT AVG(salary) FROM employee)"
    )
    assert validate_sql_against_schema(sql, SCHEMA) == sql


def test_valid_order_by_alias():
    sql = (
        "SELECT department, AVG(salary) AS avg_salary FROM employee "
        "GROUP BY department ORDER BY avg_salary"
    )
    assert validate_sql_against_schema(sql, SCHEMA) == sql


def test_valid_derived_table():
    sql = (
        "SELECT t.avg_sal FROM "
        "(SELECT AVG(salary) AS avg_sal FROM employee) t"
    )
    assert validate_sql_against_schema(sql, SCHEMA) == sql


def test_create_table_schema_format():
    schema = "CREATE TABLE employee (emp_id INT, name VARCHAR, salary INT)"
    sql = "SELECT name FROM employee"
    assert validate_sql_against_schema(sql, schema) == sql


def test_unknown_table_rejected():
    with pytest.raises(ValueError, match="Unknown table"):
        validate_sql_against_schema("SELECT id FROM nowhere", SCHEMA)


def test_unknown_column_rejected():
    with pytest.raises(ValueError, match="Unknown column"):
        validate_sql_against_schema("SELECT salaryy FROM employee", SCHEMA)


def test_unknown_column_for_qualified_table_rejected():
    # budget exists in department but not in employee
    with pytest.raises(ValueError, match="Unknown column"):
        validate_sql_against_schema(
            "SELECT e.budget FROM employee e JOIN department d ON e.department = d.name",
            SCHEMA,
        )


def test_unknown_alias_rejected():
    with pytest.raises(ValueError, match="Unknown table"):
        validate_sql_against_schema("SELECT x.name FROM employee", SCHEMA)


def test_unparseable_schema_rejected():
    with pytest.raises(ValueError, match="schema"):
        validate_sql_against_schema("SELECT name FROM employee", "not a schema at all")


def test_endpoint_rejects_unknown_table():
    """End-to-end: mocked Groq returns SQL outside the schema -> 400."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "SELECT secret FROM classified"

    with patch("app.services.sql_generator._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        client = TestClient(app)
        response = client.post(
            "/api/v1/sql/generate",
            json={
                "question": "Anything.",
                "schema": "employee(emp_id INT, name VARCHAR, salary INT)",
            },
        )

    assert response.status_code == 400
