"""Tests for read-only SQL validation."""

import pytest

from app.services.sql_validator import validate_sql


def test_valid_select():
    """A plain SELECT passes and is returned unchanged."""
    sql = "SELECT emp_id, name FROM employee WHERE salary > 1000;"
    assert validate_sql(sql) == sql


def test_valid_cte():
    """A WITH...SELECT (CTE) passes and is returned unchanged."""
    sql = (
        "WITH avg_salary AS (SELECT AVG(salary) AS m FROM employee) "
        "SELECT * FROM employee WHERE salary > (SELECT m FROM avg_salary);"
    )
    assert validate_sql(sql) == sql


def test_invalid_syntax():
    """Syntactically invalid SQL is rejected."""
    with pytest.raises(ValueError):
        validate_sql("SELECT * FROM")


def test_empty_sql():
    """Empty or whitespace-only SQL is rejected."""
    with pytest.raises(ValueError):
        validate_sql("")
    with pytest.raises(ValueError):
        validate_sql("   ")


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO employee (emp_id) VALUES (1)",
        "UPDATE employee SET salary = 0",
        "DELETE FROM employee",
        "DROP TABLE employee",
        "ALTER TABLE employee ADD COLUMN bonus INT",
        "TRUNCATE TABLE employee",
        "CREATE TABLE evil (id INT)",
        "MERGE INTO employee USING src ON employee.emp_id = src.id",
    ],
)
def test_write_and_ddl_rejected(statement):
    """Write and DDL statements are rejected."""
    with pytest.raises(ValueError):
        validate_sql(statement)


def test_multi_statement_rejected():
    """A SELECT followed by a dangerous statement is rejected."""
    with pytest.raises(ValueError):
        validate_sql("SELECT 1; DROP TABLE employee")
