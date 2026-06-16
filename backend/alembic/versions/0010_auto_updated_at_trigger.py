# backend/alembic/versions/0010_auto_updated_at_trigger.py
"""Create reusable updated_at trigger and apply to contacts.

The trigger function set_updated_at() can be reused on any table that has
an updated_at column. Just CREATE TRIGGER ... on the table.
"""

from alembic import op

revision = "0010_auto_updated_at_trigger"
down_revision = "0009_contact_opt_out_events"
branch_labels = None
depends_on = None


def upgrade():
    # Reusable trigger function
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Apply to contacts
    op.execute(
        """
        CREATE TRIGGER trg_contacts_updated_at
            BEFORE UPDATE ON contacts
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_contacts_updated_at ON contacts;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")