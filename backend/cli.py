"""Operations: python -m backend.cli create-admin / reset-password / cleanup."""
import argparse
import getpass
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select, update
from .database import make_engine, session_factory
from .migrate import verify
from .models import AuditEvent, AuthSession, RateBucket, User
from .schemas import Register
from .security import hash_password


def main():
    parser = argparse.ArgumentParser(description='CampusFlow operations')
    parser.add_argument('command', choices=['create-admin', 'reset-password', 'cleanup'])
    parser.add_argument('--login')
    parser.add_argument('--name')
    args = parser.parse_args()
    engine = make_engine(os.environ['DATABASE_URL'])
    verify(engine)
    with session_factory(engine)() as session:
        if args.command == 'cleanup':
            cutoff = datetime.now(timezone.utc)
            session.execute(delete(AuthSession).where((AuthSession.expires_at < cutoff) | (AuthSession.expires_at.is_(None))))
            session.execute(delete(RateBucket).where(RateBucket.window < int((cutoff-timedelta(days=2)).timestamp())))
            session.commit()
            print('Expired sessions and throttling buckets removed.')
            return
        login = args.login or input('Login: ').strip()
        password = os.getenv('BOOTSTRAP_ADMIN_PASSWORD') or getpass.getpass('New password (12+ characters): ')
        if len(password) < 12:
            raise SystemExit('Password must be at least 12 characters')
        user = session.scalar(select(User).where(User.login == login.lower()).with_for_update())
        if args.command == 'create-admin':
            if user:
                raise SystemExit('Login already exists; no permissions or password changed.')
            data = Register(login=login, displayName=args.name or input('Display name: ').strip(), password=password)
            user = User(login=data.login.lower(), display_name=data.displayName, role='admin', password_hash=hash_password(password))
            session.add(user)
            session.flush()
            action = 'admin.bootstrap'
        else:
            if not user:
                raise SystemExit('User not found')
            user.password_hash = hash_password(password)
            session.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
            action = 'password.operator_reset'
        session.add(AuditEvent(actor_id=user.id, action=action, entity_id=user.id))
        session.commit()
        print('Completed:', args.command, 'for', user.login)
    engine.dispose()


if __name__ == '__main__':
    main()
