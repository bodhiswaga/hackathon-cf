from alembic import context
from backend.database import Base
from backend import models  # noqa: F401

connection = context.config.attributes['connection']
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
