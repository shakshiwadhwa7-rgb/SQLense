"""Tests for Alembic migration configuration (no DB connection)."""

import importlib.util
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_DIR = BACKEND_DIR / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"


def _revision_files() -> list[Path]:
    return sorted(p for p in VERSIONS_DIR.glob("*.py") if not p.name.startswith("_"))


def test_alembic_ini_layout():
    ini_path = BACKEND_DIR / "alembic.ini"
    assert ini_path.is_file()
    content = ini_path.read_text(encoding="utf-8")

    # script_location resolves relative to the ini file itself
    assert "script_location = %(here)s/alembic" in content
    # No real connection string in a tracked file; env.py supplies the
    # URL from Settings.DATABASE_URL at runtime.
    assert "supabase" not in content.lower()
    assert "driver://user:pass@localhost/dbname" not in content


def test_alembic_scaffold_files():
    assert (ALEMBIC_DIR / "env.py").is_file()
    assert (ALEMBIC_DIR / "script.py.mako").is_file()
    assert VERSIONS_DIR.is_dir()


def test_env_py_wires_models_and_engine():
    env_source = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
    # Alembic diffs against the SQLense model metadata
    assert "from app.db.models import Base" in env_source
    assert "target_metadata = Base.metadata" in env_source
    # Connections reuse the app engine (asyncpg + ssl=require)
    assert "build_engine" in env_source


def test_alembic_in_requirements():
    requirements = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
    assert any(line.startswith("alembic") for line in requirements.splitlines())


def test_single_initial_revision_creates_four_tables():
    revisions = _revision_files()
    assert len(revisions) == 1

    source = revisions[0].read_text(encoding="utf-8")

    # Load the revision module to read its identifiers; only module-level
    # code runs (function bodies are never executed here).
    spec = importlib.util.spec_from_file_location("sqlense_revision", revisions[0])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # It is the initial revision: no predecessor
    assert module.revision
    assert module.down_revision is None
    assert hasattr(module, "upgrade") and hasattr(module, "downgrade")

    # Creates and drops exactly the four SQLense tables
    assert source.count("op.create_table(") == 4
    assert source.count("op.drop_table(") == 4

    # All six indexes (standard ix_<table>_<column> names)
    for index_name in (
        "ix_sql_history_user_id",
        "ix_sql_history_created_at",
        "ix_practice_questions_topic",
        "ix_practice_questions_difficulty",
        "ix_practice_attempts_user_id",
        "ix_practice_attempts_question_id",
    ):
        assert index_name in source, index_name

    # Foreign key targets
    assert "users.id" in source
    assert "practice_questions.id" in source
