# backend/app/core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .config import settings
from .security import decode_jwt


def tenant_or_ip_key(request: Request) -> str:
    """
    Rate-limit key prioritering:
      1) tenant_id från X-Tenant-ID header (webhooks, n8n, admin-verktyg)
      2) tenant_id från JWT (Authorization: Bearer ...)
      3) fallback till klient-IP
    
    Detta ger per-tenant rate limiting istället för per-IP,
    vilket förhindrar att en aggressiv tenant påverkar andra.
    """
    # 1) Explicit tenant header (används av n8n/webhooks)
    tenant_header = request.headers.get("X-Tenant-ID")
    if tenant_header:
        return f"tenant:{tenant_header}"

    # 2) JWT-baserad tenant (autentiserade klienter)
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            # Lätt decode utan full validering (för rate limiting)
            payload = decode_jwt(token, settings.jwt_secret)
            if payload:
                tid = payload.get("tenant_id")
                if tid:
                    return f"tenant:{tid}"

    # 3) Fallback: IP-adress (healthz, publika endpoints)
    return get_remote_address(request)


def _get_storage_uri() -> str:
    """
    Returnerar Redis URL i produktion, in-memory i development.
    
    In-memory fungerar bara med en worker/process.
    Redis krävs för multi-worker/multi-pod deployment.
    """
    if settings.env == "production":
        return settings.redis_url
    return "memory://"


limiter = Limiter(
    key_func=tenant_or_ip_key,
    default_limits=["100/minute"],
    storage_uri=_get_storage_uri(),
)
