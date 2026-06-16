# app/routers/auth.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..core.db import get_db
from ..core.config import settings
from ..core.security import create_jwt, verify_password, hash_password
# from ..core.auth import get_current_user
from ..core.rate_limit import limiter
from ..core.deps import require_admin_token
from ..core.audit import write_audit_log
from ..models.user import User
from ..schemas.auth import RegisterIn, LoginIn, LoginOut, WhoAmIOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Förgenererad bcrypt-hash för timing-attack skydd vid failed login
# (hashen av "dummy_password" - används aldrig för riktig auth)
DUMMY_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G5FgFN5Rl5H.Zy"


def _normalize_email(e: str) -> str:
    return e.strip().lower()


@router.post("/register")
@limiter.limit("5/minute")
def register(
    request: Request,
    body: RegisterIn,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_admin_token),
):
    """
    Registrera ny användare.
    Skyddad med admin token - endast n8n eller admin-verktyg kan anropa.
    """
    email = _normalize_email(body.email)

    user_exists = db.scalar(
        select(User).where(
            User.email == email,
            User.tenant_id == body.tenant_id,
        )
    )

    if user_exists:
        return {"ok": True, "message": "Registration processed"}

    try:
        u = User(
            tenant_id=body.tenant_id,
            email=email,
            password_hash=hash_password(body.password),
        )
        db.add(u)
        db.flush()  # säkerställer att defaults/PK finns innan audit om det behövs

        write_audit_log(
            db=db,
            tenant_id=body.tenant_id,
            action="user.register",
            actor=email,
            meta={"role": u.role},
            auto_commit=False,
        )

        db.commit()

        return {"ok": True, "message": "Registration processed"}
    except Exception as e:
        db.rollback()
        logger.exception("Registration failed for tenant=%s email=%s", body.tenant_id, email)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")


# ------------------------------------------------------------------
#  JWT-baserad login / me är INAKTIVERAD just nu.
#  Vi kommenterar bort endpoints men lämnar koden kvar
#  ifall vi senare vill ha ett UI med användar-login.
# ------------------------------------------------------------------

# @router.post("/login", response_model=LoginOut)
# @limiter.limit("10/minute")
# def login(
#     request: Request,
#     body: LoginIn,
#     db: Session = Depends(get_db),
# ):
#     """
#     Login endpoint - returnerar JWT token.
#     (Inaktiverad i nuvarande arkitektur – n8n använder X-Admin-Token i stället.)
#     """
#     email = _normalize_email(body.email)
#
#     u = db.scalar(
#         select(User).where(
#             User.email == email,
#             User.tenant_id == body.tenant_id,
#         )
#     )
#
#     if u:
#         pwd_ok = verify_password(body.password, u.password_hash)
#         user_active = u.is_active
#     else:
#         verify_password(body.password, DUMMY_HASH)
#         pwd_ok = False
#         user_active = False
#
#     if not u or not pwd_ok or not user_active:
#         write_audit_log(
#             db=db,
#             tenant_id=body.tenant_id,
#             action="auth.login_failed",
#             actor=email,
#             meta={"reason": "invalid_credentials"},
#             auto_commit=True,
#         )
#         raise HTTPException(status_code=401, detail="Invalid credentials")
#
#     tok = create_jwt(
#         sub=u.email,
#         tenant_id=body.tenant_id,
#         project_id=body.project_id,
#         secret=settings.jwt_secret,
#         expires_minutes=settings.jwt_expires_minutes,
#         issuer="api-core",
#         audience="api-clients",
#     )
#
#     write_audit_log(
#         db=db,
#         tenant_id=body.tenant_id,
#         action="auth.login_success",
#         actor=email,
#         meta={"project_id": body.project_id},
#         auto_commit=True,
#     )
#
#     return LoginOut(access_token=tok)
#
#
# @router.get("/me", response_model=WhoAmIOut)
# def whoami(current_user: User = Depends(get_current_user)):
#     """Returnerar info om inloggad användare. (Inaktiverad just nu.)"""
#     return WhoAmIOut(
#         tenant_id=current_user.tenant_id,
#         email=current_user.email,
#         role=current_user.role,
#         created_at=current_user.created_at,
#     )