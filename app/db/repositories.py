"""Consultas de persistencia del chat y las preferencias."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatSession, Message, ToolCallRecord, UserPreference


async def create_session(
    db: AsyncSession,
    *,
    location_label: str | None = None,
) -> ChatSession:
    """Crea una conversación y la deja lista para usar."""
    session = ChatSession(location_label=location_label)
    db.add(session)
    await db.flush()
    return session


async def get_session(
    db: AsyncSession,
    session_id: UUID,
) -> ChatSession | None:
    """Busca una conversación por id."""
    return await db.get(ChatSession, session_id)


async def add_message(
    db: AsyncSession,
    *,
    session_id: UUID,
    role: str,
    content: str,
) -> Message:
    """Agrega un mensaje y actualiza la fecha de la conversación."""
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise ValueError("La sesión no existe")

    session.updated_at = datetime.now(UTC)
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.flush()
    return message


async def get_recent_messages(
    db: AsyncSession,
    *,
    session_id: UUID,
    turns: int,
) -> list[Message]:
    """Devuelve los últimos mensajes, del más viejo al más nuevo."""
    limit = turns * 2
    if limit <= 0:
        return []

    statement = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list((await db.scalars(statement)).all())
    return list(reversed(messages))


async def add_tool_call(
    db: AsyncSession,
    *,
    session_id: UUID,
    provider_call_id: str | None,
    name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> ToolCallRecord:
    """Guarda la auditoría de una herramienta ejecutada."""
    record = ToolCallRecord(
        session_id=session_id,
        provider_call_id=provider_call_id,
        name=name,
        arguments=arguments,
        result=result,
    )
    db.add(record)
    await db.flush()
    return record


async def get_tool_calls(
    db: AsyncSession,
    *,
    session_id: UUID,
) -> list[ToolCallRecord]:
    """Devuelve las herramientas ejecutadas, en orden cronológico."""
    statement = (
        select(ToolCallRecord)
        .where(ToolCallRecord.session_id == session_id)
        .order_by(ToolCallRecord.created_at.asc())
    )
    return list((await db.scalars(statement)).all())


async def get_user_preference(
    db: AsyncSession,
    user_id: UUID,
) -> UserPreference | None:
    """Busca la preferencia de comodidad de un usuario."""
    return await db.get(UserPreference, user_id)


async def get_comfort_offset(
    db: AsyncSession,
    user_id: UUID,
) -> float:
    """Devuelve el offset guardado, o 0 si el usuario no tiene preferencia."""
    preference = await get_user_preference(db, user_id)
    return preference.comfort_offset_c if preference else 0.0


async def save_comfort_offset(
    db: AsyncSession,
    user_id: UUID,
    comfort_offset_c: float,
) -> UserPreference:
    """Guarda el offset de comodidad de un usuario."""
    preference = await get_user_preference(db, user_id)
    if preference is None:
        preference = UserPreference(user_id=user_id)
        db.add(preference)

    preference.comfort_offset_c = comfort_offset_c
    preference.updated_at = datetime.now(UTC)
    await db.flush()
    return preference
