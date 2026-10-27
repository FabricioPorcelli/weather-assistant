"""Tests de los repositorios de sesiones y mensajes."""

import asyncio
from uuid import uuid4

import pytest

from app.db.repositories import (
    add_message,
    add_tool_call,
    create_session,
    get_recent_messages,
    get_session,
    get_tool_calls,
)
from app.db.session import async_session_factory


async def test_session_messages_and_history(db_schema):
    async with async_session_factory() as db:
        session = await create_session(db, location_label="Madrid")
        await add_message(
            db,
            session_id=session.id,
            role="user",
            content="uno",
        )
        await add_message(
            db,
            session_id=session.id,
            role="assistant",
            content="dos",
        )
        await asyncio.sleep(0.001)
        await add_message(
            db,
            session_id=session.id,
            role="user",
            content="tres",
        )
        await add_message(
            db,
            session_id=session.id,
            role="assistant",
            content="cuatro",
        )
        await db.commit()

        found = await get_session(db, session.id)
        history = await get_recent_messages(
            db,
            session_id=session.id,
            turns=1,
        )

    assert found is not None
    assert found.location_label == "Madrid"
    assert [message.content for message in history] == ["tres", "cuatro"]


async def test_history_can_be_disabled(db_schema):
    async with async_session_factory() as db:
        session = await create_session(db)
        await add_message(
            db,
            session_id=session.id,
            role="user",
            content="Hola",
        )
        await db.commit()

        history = await get_recent_messages(
            db,
            session_id=session.id,
            turns=0,
        )

    assert history == []


async def test_tool_calls_are_saved(db_schema):
    async with async_session_factory() as db:
        session = await create_session(db)
        await add_tool_call(
            db,
            session_id=session.id,
            provider_call_id="call_1",
            name="get_forecast",
            arguments={"location": {"city": "Madrid"}},
            result={"days": []},
        )
        await db.commit()

        records = await get_tool_calls(db, session_id=session.id)

    assert len(records) == 1
    assert records[0].provider_call_id == "call_1"
    assert records[0].arguments == {"location": {"city": "Madrid"}}


async def test_missing_session_is_reported(db_schema):
    async with async_session_factory() as db:
        with pytest.raises(ValueError):
            await add_message(
                db,
                session_id=uuid4(),
                role="user",
                content="Hola",
            )
