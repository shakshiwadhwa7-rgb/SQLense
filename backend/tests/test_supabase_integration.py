"""Opt-in real-Supabase CRUD integration test for the async session factory.

This is an intentional live-database test (nothing is mocked). It is
SKIPPED by default so the normal offline suite never needs the network.
To run it separately:

    set SQLENSE_INTEGRATION_TESTS=1
    python -m pytest backend/tests/test_supabase_integration.py -v

Flow: insert a clearly test-only ``users`` row (random temporary UUID),
commit, read it back in a fresh session, verify id and timestamps, then
always delete the row again — even when an assertion fails — and confirm
it is gone. No schema, model, or API code is touched; no Groq calls.
"""

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.database import get_session_factory
from app.db.models import User

pytestmark = pytest.mark.skipif(
    not os.getenv("SQLENSE_INTEGRATION_TESTS") or not settings.DATABASE_URL,
    reason=(
        "Opt-in Supabase integration test: set SQLENSE_INTEGRATION_TESTS=1 "
        "(with DATABASE_URL in .env) to run"
    ),
)


async def _crud_flow() -> None:
    session_factory = get_session_factory()
    test_user_id = uuid.uuid4()

    try:
        # 1-2. Insert the temporary test user and commit.
        async with session_factory() as session:
            session.add(User(id=test_user_id))
            await session.commit()

        # 3-5. Read the row back in a NEW session; verify UUID + timestamps.
        async with session_factory() as session:
            result = await session.execute(
                select(User).where(User.id == test_user_id)
            )
            loaded = result.scalar_one()

            assert loaded.id == test_user_id
            assert loaded.created_at is not None
            assert loaded.updated_at is not None
            assert loaded.created_at.tzinfo is not None
            assert loaded.updated_at.tzinfo is not None
            assert loaded.updated_at >= loaded.created_at
    finally:
        # 6-8. ALWAYS clean up: delete the row, commit, verify it is gone.
        async with session_factory() as session:
            await session.execute(delete(User).where(User.id == test_user_id))
            await session.commit()

        async with session_factory() as session:
            remaining = await session.execute(
                select(User.id).where(User.id == test_user_id)
            )
            assert remaining.scalar_one_or_none() is None, (
                "test user row was not cleaned up"
            )


def test_async_session_crud_against_supabase() -> None:
    """Live insert / read-back / cleanup round-trip via the real engine."""
    asyncio.run(_crud_flow())
