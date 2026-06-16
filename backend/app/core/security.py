# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
import uuid

ALGO = "HS256"

# Använd CryptContext istället för direkta bcrypt-anrop
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    """
    Hashar lösenord med bcrypt.
    Trunkerar till 72 bytes om nödvändigt (bcrypt-begränsning).
    """
    # Bcrypt kan bara hantera 72 bytes
    password_bytes = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password_bytes)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifierar lösenord mot hash.
    """
    password_bytes = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    try:
        return pwd_context.verify(password_bytes, hashed)
    except Exception:
        return False


def create_jwt(
    sub: str,
    tenant_id: str,
    project_id: str,
    secret: str,
    expires_minutes: int,
    *,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
    not_before_skew_seconds: int = 0,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "nbf": int((now + timedelta(seconds=not_before_skew_seconds)).timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    if issuer:
        payload["iss"] = issuer
    if audience:
        payload["aud"] = audience
    return jwt.encode(payload, secret, algorithm=ALGO)


def decode_jwt(
    token: str,
    secret: str,
    *,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
) -> Optional[dict]:
    options = {"verify_aud": audience is not None}
    try:
        return jwt.decode(
            token, secret, algorithms=[ALGO], issuer=issuer, audience=audience, options=options
        )
    except JWTError:
        return None
