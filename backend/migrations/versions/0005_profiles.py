"""Split names and store normalized avatar thumbnails; preserve legacy display names."""
from alembic import op
import sqlalchemy as sa
revision='0005'
down_revision='0004'

def upgrade():
    op.add_column('users',sa.Column('first_name',sa.String(50),nullable=False,server_default=''))
    op.add_column('users',sa.Column('last_name',sa.String(50),nullable=False,server_default=''))
    op.add_column('users',sa.Column('avatar',sa.String(40000),nullable=False,server_default=''))
    connection=op.get_bind()
    for uid,name in connection.execute(sa.text('SELECT id,display_name FROM users')).all():
        first,_,last=name.partition(' ')
        connection.execute(sa.text('UPDATE users SET first_name=:first,last_name=:last WHERE id=:id'),{'first':first[:50],'last':last[:50],'id':uid})

def downgrade():
    op.drop_column('users','avatar')
    op.drop_column('users','last_name')
    op.drop_column('users','first_name')
