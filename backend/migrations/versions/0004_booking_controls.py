"""Record booking requirements and attendance without changing existing bookings."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'

def upgrade():
    op.add_column('bookings', sa.Column('requirements', sa.JSON, nullable=False, server_default='[]'))
    op.add_column('bookings', sa.Column('team_id', sa.Integer, nullable=True))
    op.add_column('bookings', sa.Column('checked_in', sa.Boolean, nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column('bookings', 'checked_in')
    op.drop_column('bookings', 'team_id')
    op.drop_column('bookings', 'requirements')
