"""Run migrations separately on production releases: python -m backend.migrate."""
import os
from pathlib import Path
from threading import Lock
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from .database import make_engine

HEAD = '0005'
_migration_lock = Lock()


def upgrade(engine):
    # Alembic's global context is not thread-safe; PostgreSQL advisory lock also
    # serializes releases from separate processes against the same database.
    with _migration_lock, engine.begin() as connection:
        if engine.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(438029117)'))
        cfg = Config()
        cfg.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
        cfg.attributes['connection'] = connection
        command.upgrade(cfg, 'head')


def verify(engine):
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT version_num FROM alembic_version'))
        if version != HEAD:
            raise RuntimeError('Database schema is outdated. Run python -m backend.migrate')


if __name__ == '__main__':
    engine = make_engine(os.getenv('DATABASE_URL', 'sqlite:///./campusflow.db'))
    upgrade(engine)
    engine.dispose()
    print('Database schema upgraded to', HEAD)
