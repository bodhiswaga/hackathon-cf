"""Persist waiting lists and shared meeting polls."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'


def upgrade():
    op.create_table('plans', sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('kind', sa.String(20), nullable=False),
                    sa.Column('token', sa.String(64), nullable=False, unique=True),
                    sa.Column('data', sa.JSON, nullable=False))
    op.create_index('ix_plans_user_id', 'plans', ['user_id'])


def downgrade():
    op.drop_table('plans')
