"""Alembic migration environment for SQLense.

Reuses the application's database foundation: the engine comes from
``app.db.database.build_engine`` (asyncpg + SSL ``ssl=require``) and the
URL from ``Settings.DATABASE_URL`` in the repository-root ``.env`` file.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.db.database import build_engine, to_asyncpg_url
from app.db.models import Base

# The Alembic Config object, which provides access to the values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata used by --autogenerate: the SQLense tables.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: render SQL without connecting."""
    url = to_asyncpg_url(settings.DATABASE_URL) if settings.DATABASE_URL else None
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Connect with the application's engine and run migrations."""
    engine = build_engine(settings.DATABASE_URL)

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
