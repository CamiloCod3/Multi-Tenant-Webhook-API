from alembic import op
import sqlalchemy as sa

revision = "0008_contacts_identity_uniques"
down_revision = "0007_contacts_and_message_logs"
branch_labels = None
depends_on = None


def upgrade():
    # Säkerställ att det inte redan finns dubbletter innan unika index skapas.
    # Om denna migration failar här finns befintlig data som måste dedupliceras först.

    op.create_index(
        "contacts_tenant_email_uq",
        "contacts",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_index(
        "contacts_tenant_normalized_phone_uq",
        "contacts",
        ["tenant_id", "normalized_phone"],
        unique=True,
        postgresql_where=sa.text("normalized_phone IS NOT NULL"),
    )

    # De gamla icke-unika indexen blir överflödiga när de unika partial-indexen finns.
    op.drop_index("contacts_tenant_email_idx", table_name="contacts")
    op.drop_index("contacts_tenant_phone_idx", table_name="contacts")


def downgrade():
    op.create_index("contacts_tenant_email_idx", "contacts", ["tenant_id", "email"])
    op.create_index(
        "contacts_tenant_phone_idx",
        "contacts",
        ["tenant_id", "normalized_phone"],
    )

    op.drop_index("contacts_tenant_normalized_phone_uq", table_name="contacts")
    op.drop_index("contacts_tenant_email_uq", table_name="contacts")