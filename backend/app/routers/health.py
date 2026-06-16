# backend/app/routers/health.py
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..core.db import get_db
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

@router.get("/healthz")
def healthz():
    """
    Basic liveness check.
    Returnerar 200 om processen är igång.
    Används av Docker/K8s för att avgöra om containern lever.
    """
    return {"ok": True}


@router.get("/livez")
def livez():
    """
    Kubernetes liveness probe.
    Om denna failar kommer K8s restarta podden.
    Håll den enkel - bara "är processen igång?"
    """
    return {"ok": True}


@router.get("/readyz")
async def readyz(db: Session = Depends(get_db)):
    """
    Readiness check - är alla dependencies redo?
    K8s använder detta för att avgöra om podden kan ta trafik.
    
    Kollar:
    - Database connectivity
    - Redis connectivity (endast i produktion)
    """
    checks = {}

    # 1) Database check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        checks["database"] = "unhealthy"

    # 2) Redis check (endast i produktion där det används)
    if settings.env == "production":
        try:
            from ..core.redis import redis_health_check
            redis_ok = await redis_health_check()
            checks["redis"] = "healthy" if redis_ok else "unhealthy"
        except Exception as e:
            logger.error("Redis health check failed: %s", e)
            checks["redis"] = "unhealthy"

    # Evaluera overall health
    all_healthy = all("unhealthy" not in str(v) for v in checks.values())

    if not all_healthy:
        raise HTTPException(
            status_code=503,
            detail={"ok": False, "checks": checks},
        )

    return {"ok": True, "checks": checks}