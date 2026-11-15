"""Baseline schema, including non-destructive adoption of the original MVP."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'users' not in existing:
        op.create_table('users', sa.Column('id', sa.Integer, primary_key=True), sa.Column('login', sa.String(80), nullable=False, unique=True), sa.Column('password_hash', sa.String(200), nullable=False), sa.Column('role', sa.String(20), nullable=False), sa.Column('display_name', sa.String(100), nullable=False))
    if 'rooms' not in existing:
        op.create_table('rooms', sa.Column('id', sa.Integer, primary_key=True), sa.Column('name', sa.String(60), nullable=False), sa.Column('building', sa.String(30), nullable=False), sa.Column('floor', sa.Integer, nullable=False), sa.Column('capacity', sa.Integer, nullable=False), sa.Column('equipment', sa.JSON, nullable=False), sa.Column('description', sa.String(300), nullable=False), sa.Column('active', sa.Boolean, nullable=False), sa.UniqueConstraint('building', 'name'), sa.CheckConstraint('capacity > 0'))
    if 'bookings' not in existing:
        op.create_table('bookings', sa.Column('id', sa.Integer, primary_key=True), sa.Column('room_id', sa.Integer, sa.ForeignKey('rooms.id'), nullable=False), sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False), sa.Column('date', sa.Date, nullable=False), sa.Column('start_time', sa.String(5), nullable=False), sa.Column('end_time', sa.String(5), nullable=False), sa.Column('status', sa.String(20), nullable=False), sa.Column('comment', sa.String(300), nullable=False), sa.CheckConstraint('start_time < end_time'))
        op.create_index('ix_booking_room_date_status', 'bookings', ['room_id', 'date', 'status'])
    if 'auth_sessions' not in existing:
        op.create_table('auth_sessions', sa.Column('id', sa.String(64), primary_key=True), sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False), sa.Column('revoked', sa.Boolean, nullable=False))
        op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])


def downgrade():
    raise RuntimeError('Baseline downgrade would delete user data. Restore a backup instead.')
