from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT  # NYTT

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Enable citext extension for case-insensitive email
    op.execute("create extension if not exists citext;")
    
    # Tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('plan', sa.String(length=50), server_default='basic'),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
        ),
    )
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column(
            'tenant_id',
            sa.String(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('email', CITEXT(), nullable=False),  # NYTT: CITEXT typ
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('role', sa.String(length=20), server_default='admin'),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
        ),
    )
    
    # Unique constraint: one email per tenant
    op.create_index('users_tenant_email_uq', 'users', ['tenant_id', 'email'], unique=True)
    
    # Audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'tenant_id',
            sa.String(),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('actor', sa.String(length=320)),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column(
            'meta',
            sa.JSON(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
        ),
    )
    
    # Index på tenant_id för snabbare audit queries
    op.create_index('audit_logs_tenant_id_idx', 'audit_logs', ['tenant_id'])
    
    # Optional: Index på created_at för time-range queries
    op.create_index('audit_logs_created_at_idx', 'audit_logs', ['created_at'])

def downgrade():
    op.drop_index('audit_logs_created_at_idx', table_name='audit_logs')
    op.drop_index('audit_logs_tenant_id_idx', table_name='audit_logs')
    op.drop_table('audit_logs')
    
    op.drop_index('users_tenant_email_uq', table_name='users')
    op.drop_table('users')
    
    op.drop_table('tenants')
    op.execute("drop extension if exists citext;")
