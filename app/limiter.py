"""Rate limiting por IP con slowapi y Redis.

Si Redis no responde, slowapi usa un almacenamiento en memoria: el límite sigue
aplicándose por proceso y la API no se cae.
"""

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
