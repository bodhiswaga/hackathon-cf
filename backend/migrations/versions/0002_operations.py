"""Session lifecycle, distributed throttling and audit history."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'


def upgrade():
    op.add_column('auth_sessions', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('auth_sessions', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    # Legacy sessions have no trustworthy expiry. Require login after this upgrade.
    op.execute(sa.text('UPDATE auth_sessions SET revoked = true'))
    op.create_index('ix_auth_sessions_expires_at', 'auth_sessions', ['expires_at'])
    op.create_table('rate_buckets', sa.Column('key', sa.String(64), primary_key=True), sa.Column('window', sa.BigInteger, nullable=False), sa.Column('count', sa.Integer, nullable=False))
    op.create_table('audit_events', sa.Column('id', sa.Integer, primary_key=True), sa.Column('actor_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True), sa.Column('action', sa.String(60), nullable=False), sa.Column('entity_id', sa.Integer, nullable=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_audit_events_created_at', 'audit_events', ['created_at'])
    op.create_index('ix_booking_user_date', 'bookings', ['user_id', 'date'])


def downgrade():
    op.drop_index('ix_booking_user_date', table_name='bookings')
    op.drop_table('audit_events')
    op.drop_table('rate_buckets')
    op.drop_index('ix_auth_sessions_expires_at', table_name='auth_sessions')
    op.drop_column('auth_sessions', 'expires_at')
    op.drop_column('auth_sessions', 'created_at')
