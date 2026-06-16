# app/core/dead_letter.py

import logging
from sqlalchemy.orm import Session
from ..models.metrics import FailedEvent

logger = logging.getLogger(__name__)


def store_failed_event(
    db: Session,
    tenant_id: str,
    event_id: str | None,
    raw_payload: dict,
    error_message: str,
) -> None:
    """
    Sparar ett misslyckat event för senare analys/retry.
    """
    try:
        failed = FailedEvent(
            tenant_id=tenant_id,
            event_id=event_id,
            raw_payload=raw_payload,
            error_message=error_message[:2000],  # Trunkera långa errors
        )
        db.add(failed)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to store dead letter: {e}")
        db.rollback()