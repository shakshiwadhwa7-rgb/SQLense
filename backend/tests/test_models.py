"""Tests for the SQLense database models (metadata only, no DB connection)."""

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.models import Base, PracticeAttempt, PracticeQuestion, SqlHistory, User

EXPECTED_TABLES = {
    "users",
    "sql_history",
    "practice_questions",
    "practice_attempts",
}


def test_only_expected_tables_exist():
    """Exactly the four SQLense tables; no auth or extra tables."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_uuid_primary_keys():
    for table_name, table in Base.metadata.tables.items():
        id_column = table.c.id
        assert id_column.primary_key, table_name
        assert isinstance(id_column.type, UUID), table_name


def test_timezone_aware_timestamps_with_defaults():
    for table_name, table in Base.metadata.tables.items():
        created = table.c.created_at
        assert isinstance(created.type, DateTime), table_name
        assert created.type.timezone is True, table_name
        assert created.server_default is not None, table_name

    # users uniquely has updated_at, refreshed on update
    updated = Base.metadata.tables["users"].c.updated_at
    assert isinstance(updated.type, DateTime)
    assert updated.type.timezone is True
    assert updated.server_default is not None
    assert updated.onupdate is not None


def test_text_fields():
    tables = Base.metadata.tables

    history = tables["sql_history"]
    for column_name in ("natural_language_query", "schema_text", "generated_sql"):
        assert isinstance(history.c[column_name].type, Text), column_name

    questions = tables["practice_questions"]
    for column_name in ("question", "schema_text", "reference_sql"):
        assert isinstance(questions.c[column_name].type, Text), column_name

    attempts = tables["practice_attempts"]
    assert isinstance(attempts.c.submitted_sql.type, Text)
    assert isinstance(attempts.c.feedback.type, Text)
    assert attempts.c.feedback.nullable is True


def test_varchar_and_boolean_fields():
    tables = Base.metadata.tables

    questions = tables["practice_questions"]
    for column_name in ("difficulty", "topic"):
        column = questions.c[column_name]
        assert isinstance(column.type, String), column_name
        assert column.nullable is False

    is_correct = tables["practice_attempts"].c.is_correct
    assert isinstance(is_correct.type, Boolean)
    assert is_correct.nullable is False


def test_foreign_keys():
    tables = Base.metadata.tables

    history_fks = list(tables["sql_history"].c.user_id.foreign_keys)
    assert len(history_fks) == 1
    assert history_fks[0].target_fullname == "users.id"

    attempt_user_fks = list(tables["practice_attempts"].c.user_id.foreign_keys)
    assert len(attempt_user_fks) == 1
    assert attempt_user_fks[0].target_fullname == "users.id"

    attempt_question_fks = list(tables["practice_attempts"].c.question_id.foreign_keys)
    assert len(attempt_question_fks) == 1
    assert attempt_question_fks[0].target_fullname == "practice_questions.id"


def test_indexes_on_foreign_keys_and_frequently_queried_fields():
    expected = {
        "users": set(),
        "sql_history": {"user_id", "created_at"},
        "practice_questions": {"topic", "difficulty"},
        "practice_attempts": {"user_id", "question_id"},
    }
    for table_name, expected_columns in expected.items():
        table = Base.metadata.tables[table_name]
        indexed_columns = {c.name for c in table.c if c.index}
        assert indexed_columns == expected_columns, table_name
        # Column-level index=True must materialize as Index objects for
        # Alembic autogenerate to pick them up.
        assert len(table.indexes) == len(expected_columns), table_name


def test_relationships():
    user_relationships = User.__mapper__.relationships
    assert "sql_history" in user_relationships
    assert "practice_attempts" in user_relationships

    # Many-to-one sides point at the right classes
    attempt_relationships = PracticeAttempt.__mapper__.relationships
    assert attempt_relationships["user"].mapper.class_ is User
    assert attempt_relationships["question"].mapper.class_ is PracticeQuestion
    assert SqlHistory.__mapper__.relationships["user"].mapper.class_ is User

    # One-to-many side on PracticeQuestion
    assert "attempts" in PracticeQuestion.__mapper__.relationships

    # Both directions are wired via back_populates
    assert user_relationships["sql_history"].back_populates == "user"
    assert user_relationships["practice_attempts"].back_populates == "user"
    assert (
        PracticeQuestion.__mapper__.relationships["attempts"].back_populates
        == "question"
    )
