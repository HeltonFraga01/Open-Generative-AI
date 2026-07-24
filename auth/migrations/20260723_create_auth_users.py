"""
Alembic migration: Create auth_users table.
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'auth_users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(128), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index('ix_auth_users_username', 'auth_users', ['username'])


def downgrade():
    op.drop_index('ix_auth_users_username', table_name='auth_users')
    op.drop_table('auth_users')