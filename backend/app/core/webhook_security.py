import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request

from .config import settings

MAX_WEBHOOK_BYTES = 1024 * 1024  # 1 MB
WEBHOOK_TIMESTAMP_TOLERANCE = 300  # 5 minuter


async def verify_webhook_signature(
    request: Request,
    x_signature: str = Header(default="", alias="X-Signature"),
    x_timestamp: str = Header(default="", alias="X-Timestamp"),
) -> None:
    """
    HMAC-SHA256 verifiering med replay protection.

    Signature beräknas som: HMAC(secret, timestamp + "." + body)

    Headers som krävs:
    - X-Signature: HMAC hex digest
    - X-Timestamp: Unix timestamp (sekunder)
    """
    if not settings.hmac_secret:
        if settings.env == "production":
            raise HTTPException(status_code=500, detail="HMAC secret not configured")
        return

    if not x_signature or not x_timestamp:
        raise HTTPException(status_code=401, detail="Missing signature headers")

    try:
        ts = int(x_timestamp)
        now = int(time.time())
        if abs(now - ts) > WEBHOOK_TIMESTAMP_TOLERANCE:
            raise HTTPException(status_code=401, detail="Webhook timestamp expired")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp format")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BYTES:
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError:
            pass

    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")

    message = f"{x_timestamp}.".encode() + raw_body
    computed = hmac.new(
        settings.hmac_secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, x_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")