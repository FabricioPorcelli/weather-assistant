"""Rate limit por IP con slowapi y Redis."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    headers_enabled=True,
    in_memory_fallback_enabled=True,
)

RATE_LIMIT = settings.rate_limit
