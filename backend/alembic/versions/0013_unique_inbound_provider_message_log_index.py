"""add unique inbound provider message log index

Revision ID: 0013
Revises: 0012_feedback_system
Create Date: 2026-05-24
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012_feedback_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_message_logs_provider_inbound
        ON message_logs(provider, provider_message_id)
        WHERE direction = 'inbound'
          AND provider_message_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_message_logs_provider_inbound;
        """
    )