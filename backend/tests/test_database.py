"""Tests for database foundation — no real database connection required."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db import database
from app.db.database import (
    build_engine,
    build_session_factory,
    check_connection,
    to_asyncpg_url,
)


# --- to_asyncpg_url -----------------------------------------------------


def test_to_asyncpg_url_converts_postgresql_scheme():
    converted = to_asyncpg_url(
        "postgresql://user:pass@db.example.com:5432/postgres"
    )
    assert converted == (
        "postgresql+asyncpg://user:pass@db.example.com:5432/postgres"
    )


def test_to_asyncpg_url_converts_postgres_scheme():
    converted = to_asyncpg_url(
        "postgres://user:pass@db.example.com:5432/postgres"
    )
    assert converted == (
        "postgresql+asyncpg://user:pass@db.example.com:5432/postgres"
    )


def test_to_asyncpg_url_is_idempotent():
    url = "postgresql+asyncpg://user:pass@db.example.com:5432/postgres"
    assert to_asyncpg_url(url) == url


def test_to_asyncpg_url_rejects_empty_value():
    with pytest.raises(ValueError):
        to_asyncpg_url("")
    with pytest.raises(ValueError):
        to_asyncpg_url("   ")


def test_to_asyncpg_url_rejects_other_schemes_without_leaking_credentials():
    with pytest.raises(ValueError) as exc_info:
        to_asyncpg_url("mysql://user:supersecret@db.example.com/mydb")

    message = str(exc_info.value)
    assert "mysql" in message
    assert "supersecret" not in message


# --- build_engine / build_session_factory -------------------------------


def test_build_engine_uses_asyncpg_driver_and_ssl_require():
    engine = build_engine("postgresql://user:pass@db.example.com:5432/postgres")
    try:
        assert isinstance(engine, AsyncEngine)
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.url.host == "db.example.com"
        assert engine.url.username == "user"
        assert engine.url.database == "postgres"
        assert engine.url.query.get("ssl") == "require"
    finally:
        asyncio.run(engine.dispose())


def test_build_engine_keeps_existing_ssl_parameter():
    engine = build_engine(
        "postgresql+asyncpg://user:pass@db.example.com/postgres?ssl=verify-full"
    )
    try:
        assert engine.url.query.get("ssl") == "verify-full"
    finally:
        asyncio.run(engine.dispose())


def test_build_session_factory_creates_sessions_without_connecting():
    engine = build_engine("postgresql://user:pass@db.example.com/postgres")
    factory = build_session_factory(engine)

    async def open_session():
        async with factory() as session:
            return session

    try:
        session = asyncio.run(open_session())
        assert isinstance(session, AsyncSession)
    finally:
        asyncio.run(engine.dispose())


# --- Settings-backed accessors -------------------------------------------


def test_get_engine_reads_database_url_from_settings(monkeypatch):
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(
        database.settings,
        "DATABASE_URL",
        "postgresql://user:pass@settings-host:5432/postgres",
    )

    engine = database.get_engine()
    try:
        assert engine.url.host == "settings-host"
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.url.query.get("ssl") == "require"
    finally:
        asyncio.run(engine.dispose())


def test_get_engine_without_database_url_raises(monkeypatch):
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database.settings, "DATABASE_URL", "")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database.get_engine()


# --- check_connection (SELECT 1, fully mocked) ----------------------------


def _mock_engine(scalar_value=1, side_effect=None):
    mock_result = MagicMock()
    mock_result.scalar.return_value = scalar_value

    mock_connection = MagicMock()
    if side_effect is not None:
        mock_connection.execute = AsyncMock(side_effect=side_effect)
    else:
        mock_connection.execute = AsyncMock(return_value=mock_result)

    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=mock_connection)
    connection_context.__aexit__ = AsyncMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = connection_context
    return mock_engine, mock_connection


def test_check_connection_executes_select_1():
    mock_engine, mock_connection = _mock_engine()

    with patch("app.db.database.get_engine", return_value=mock_engine):
        value = asyncio.run(check_connection())

    assert value == 1
    executed_sql = str(mock_connection.execute.call_args.args[0])
    assert executed_sql == "SELECT 1"


def test_check_connection_wraps_connection_failure():
    mock_engine, _ = _mock_engine(side_effect=OSError("connection refused"))

    with patch("app.db.database.get_engine", return_value=mock_engine):
        with pytest.raises(RuntimeError, match="connection check failed"):
            asyncio.run(check_connection())


def test_check_connection_rejects_unexpected_result():
    mock_engine, _ = _mock_engine(scalar_value=5)

    with patch("app.db.database.get_engine", return_value=mock_engine):
        with pytest.raises(RuntimeError, match="expected 1"):
            asyncio.run(check_connection())
