"""Endpoint de feedback de comodidad."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.advice.personalization import ComfortFeedback, update_comfort_offset
from app.db.repositories import get_comfort_offset, save_comfort_offset
from app.db.session import get_db_session
from app.limiter import RATE_LIMIT, limiter

router = APIRouter(prefix="/v1", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """Body de POST /v1/feedback."""

    user_id: UUID
    feedback: ComfortFeedback


class FeedbackResponse(BaseModel):
    """Offset actualizado del usuario."""

    user_id: UUID
    comfort_offset_c: float


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit(RATE_LIMIT)
async def submit_feedback(
    request: Request,
    response: Response,
    payload: FeedbackRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> FeedbackResponse:
    """Registra el feedback y devuelve el offset actualizado."""
    current_offset_c = await get_comfort_offset(db, payload.user_id)
    updated_offset_c = update_comfort_offset(current_offset_c, payload.feedback)
    preference = await save_comfort_offset(db, payload.user_id, updated_offset_c)
    await db.commit()

    return FeedbackResponse(
        user_id=payload.user_id,
        comfort_offset_c=preference.comfort_offset_c,
    )
