# backend/app/core/redis.py
import logging
from typing import Optional

import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """
    Singleton async Redis-klient.
    Återanvänder samma anslutning genom appens livstid.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info(f"Redis client created for {settings.redis_url}")
    return _redis_client


async def close_redis() -> None:
    """
    Stäng Redis-anslutningen vid shutdown.
    """
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis client closed")


async def redis_health_check() -> bool:
    """
    Enkel health check för Redis.
    Returnerar True om Redis svarar, False annars.
    """
    try:
        client = await get_redis()
        await client.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False