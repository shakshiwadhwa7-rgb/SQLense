"""Async database engine, session factory, and connectivity check."""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_ASYNCPG_SCHEME = "postgresql+asyncpg://"


def to_asyncpg_url(database_url: str) -> str:
    """Convert a plain PostgreSQL URL to SQLAlchemy's asyncpg scheme.

    ``postgresql://...`` and ``postgres://...`` become
    ``postgresql+asyncpg://...``. An already-converted URL is returned
    unchanged so the conversion is idempotent.

    Raises:
        ValueError: If the URL is empty or uses an unsupported scheme.
            The error message never includes credentials.
    """
    if not database_url or not database_url.strip():
        raise ValueError("DATABASE_URL is empty")

    url = database_url.strip()
    if url.startswith(_ASYNCPG_SCHEME):
        return url
    if url.startswith("postgresql://"):
        return _ASYNCPG_SCHEME + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return _ASYNCPG_SCHEME + url[len("postgres://"):]

    scheme = url.split("://", 1)[0] if "://" in url else "(no scheme)"
    raise ValueError(
        f"Unsupported DATABASE_URL scheme {scheme!r}; "
        "expected postgresql:// or postgres://"
    )


def build_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given database URL.

    Uses the asyncpg driver and enables SSL with ``ssl=require`` (encrypt
    the connection without certificate verification), which matches
    Supabase's recommended ``sslmode=require``. If the URL already carries
    an ``ssl`` parameter, that value is kept as-is.
    """
    url = make_url(to_asyncpg_url(database_url))
    if "ssl" not in url.query:
        url = url.set(query={**url.query, "ssl": "require"})
    return create_async_engine(url)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, built from Settings on first use.

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not configured.
    """
    global _engine
    if _engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not configured; add it to .env"
            )
        _engine = build_engine(settings.DATABASE_URL)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, built on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = build_session_factory(get_engine())
    return _session_factory


async def check_connection() -> int:
    """Verify database connectivity with a simple read-only ``SELECT 1``.

    Returns:
        1 on success.

    Raises:
        RuntimeError: If the database is unreachable or replies with an
            unexpected value.
    """
    try:
        engine = get_engine()
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            value = result.scalar()
    except Exception as exc:
        raise RuntimeError(f"Database connection check failed: {exc}") from exc

    if value != 1:
        raise RuntimeError(
            f"Database connection check returned {value!r}; expected 1"
        )
    return value
