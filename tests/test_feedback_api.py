"""Tests del endpoint de feedback."""

from uuid import uuid4

from app.db.repositories import get_user_preference
from app.db.session import async_session_factory
from app.limiter import limiter


async def test_feedback_accumulates(db_schema, api_client):
    user_id = uuid4()

    cold = await api_client.post(
        "/v1/feedback",
        json={"user_id": str(user_id), "feedback": "cold"},
    )
    cold_again = await api_client.post(
        "/v1/feedback",
        json={"user_id": str(user_id), "feedback": "cold"},
    )
    hot = await api_client.post(
        "/v1/feedback",
        json={"user_id": str(user_id), "feedback": "hot"},
    )
    just_right = await api_client.post(
        "/v1/feedback",
        json={"user_id": str(user_id), "feedback": "just_right"},
    )

    assert cold.status_code == 200
    assert cold.json()["comfort_offset_c"] == -0.5
    assert cold_again.json()["comfort_offset_c"] == -1.0
    assert hot.json()["comfort_offset_c"] == -0.5
    assert just_right.json()["comfort_offset_c"] == -0.5

    async with async_session_factory() as db:
        preference = await get_user_preference(db, user_id)

    assert preference is not None
    assert preference.comfort_offset_c == -0.5


async def test_feedback_clamps_offset(db_schema, api_client):
    user_id = uuid4()

    for _ in range(25):
        response = await api_client.post(
            "/v1/feedback",
            json={"user_id": str(user_id), "feedback": "hot"},
        )

    assert response.status_code == 200
    assert response.json()["comfort_offset_c"] == 10.0


async def test_feedback_with_rate_limit_headers(db_schema, api_client):
    previous = limiter.enabled
    limiter.enabled = True
    try:
        response = await api_client.post(
            "/v1/feedback",
            json={"user_id": str(uuid4()), "feedback": "hot"},
        )
    finally:
        limiter.enabled = previous

    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Limit")


async def test_invalid_feedback_is_rejected(db_schema, api_client):
    response = await api_client.post(
        "/v1/feedback",
        json={"user_id": str(uuid4()), "feedback": "regular"},
    )

    assert response.status_code == 422
