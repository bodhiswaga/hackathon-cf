"""Free Render has no pre-deploy or Shell: migrate and bootstrap before serving."""
import os
from sqlalchemy import select, text
from .database import make_engine, session_factory
from .migrate import upgrade
from .models import AuditEvent, User
from .schemas import Register
from .security import hash_password


def bootstrap(engine):
    password = os.getenv('BOOTSTRAP_ADMIN_PASSWORD', '')
    if not password:
        return
    login = os.getenv('BOOTSTRAP_ADMIN_LOGIN', 'operator').lower()
    name = os.getenv('BOOTSTRAP_ADMIN_NAME', 'Администратор кампуса')
    data = Register(login=login, displayName=name, password=password)
    if len(password) < 12:
        raise RuntimeError('Bootstrap admin password requires at least 12 characters')
    with session_factory(engine)() as session:
        if engine.dialect.name == 'postgresql':
            session.execute(text('SELECT pg_advisory_xact_lock(438029118)'))
        else:
            session.execute(text('BEGIN IMMEDIATE'))
        existing = session.scalar(select(User).where(User.login == login))
        if existing:
            if existing.role != 'admin':
                raise RuntimeError('Bootstrap login belongs to a non-admin; choose another login')
            return  # Never reset an existing account's password on restart.
        user = User(login=data.login, display_name=data.displayName, role='admin', password_hash=hash_password(password))
        session.add(user)
        session.flush()
        session.add(AuditEvent(actor_id=user.id, action='admin.bootstrap', entity_id=user.id))
        session.commit()
        print('Initial administrator created; remove BOOTSTRAP_ADMIN_PASSWORD from Render Environment.', flush=True)


def main():
    engine = make_engine(os.environ['DATABASE_URL'])
    upgrade(engine)
    bootstrap(engine)
    engine.dispose()
    # Render supplies this exact service hostname; keep localhost for health checks.
    hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
    if hostname:
        hosts = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
        os.environ['ALLOWED_HOSTS'] = ','.join(dict.fromkeys([*hosts, hostname]))
    os.execvp('uvicorn', ['uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', os.getenv('PORT', '8000')])


if __name__ == '__main__':
    main()
