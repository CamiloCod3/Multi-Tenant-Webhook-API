# backend/alembic/versions/0014_update_negative_feedback_threshold.py
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS feedback_requests_pending_review_idx")

    op.create_index(
        "feedback_requests_pending_review_idx",
        "feedback_requests",
        ["google_review_due_at"],
        postgresql_where=sa.text(
            "google_review_sent_at IS NULL "
            "AND score IS NOT NULL "
            "AND score <= 3"
        ),
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS feedback_requests_pending_review_idx")

    op.create_index(
        "feedback_requests_pending_review_idx",
        "feedback_requests",
        ["google_review_due_at"],
        postgresql_where=sa.text(
            "google_review_sent_at IS NULL "
            "AND score IS NOT NULL "
            "AND score <= 2"
        ),
    )