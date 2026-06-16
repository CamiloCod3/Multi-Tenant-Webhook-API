# backend/app/core/auth.py

"""
JWT-baserad auth (PARKERAD)

Just nu används inte dessa funktioner eftersom API:t skyddas via:

- X-Admin-Token (require_admin_token) för interna/admin-endpoints
- HMAC-signatur (verify_webhook_signature) för webhooks

Om vi i framtiden bygger ett riktigt login-flöde/UI kan vi återaktivera
get_current_user / get_current_admin och använda JWT igen.
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from .config import settings
from .security import decode_jwt
from .db import get_db, set_tenant
from ..models.user import User


def get_current_user(
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """
    Central auth-layer för JWT-skyddade endpoints (INTE AKTIVT I NUVARANDE SETUP).

    - Läser Authorization: Bearer <token>
    - Validerar JWT (signatur, exp, iss, aud)
    - Hämtar tenant_id + sub (email) ur token
    - Sätter tenant-context i DB (för framtida RLS)
    - Hämtar användaren och kollar is_active
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_jwt(
        token,
        settings.jwt_secret,
        issuer="api-core",
        audience="api-clients",
    )

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    tenant_id = payload.get("tenant_id")
    email = payload.get("sub")

    if not tenant_id or not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Tenant-context (för framtida RLS, auditering osv)
    set_tenant(db, tenant_id)

    user = db.scalar(
        select(User).where(
            User.tenant_id == tenant_id,
            User.email == email,
        )
    )

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User disabled")

    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """
    Admin-check ovanpå JWT (INTE AKTIV JUST NU).
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
