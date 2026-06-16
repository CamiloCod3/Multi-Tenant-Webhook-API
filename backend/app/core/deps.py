# backend/app/core/deps.py
import hmac

from fastapi import Header, HTTPException

from .config import settings


def require_admin_token(
    x_admin_token: str = Header(default="", alias="X-Admin-Token"),
):
    """
    Protects admin endpoints.

    Development mode:
    - If TENANT_ADMIN_TOKEN is not set, requests are allowed for local development.

    Production mode:
    - X-Admin-Token must match TENANT_ADMIN_TOKEN.
    """
    if settings.env != "production" and not settings.tenant_admin_token:
        return

    expected = settings.tenant_admin_token
    if not expected:
        raise HTTPException(status_code=401, detail="Unauthorized - admin token not configured")

    if not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized - invalid admin token")
