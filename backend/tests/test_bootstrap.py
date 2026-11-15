import pytest
from sqlalchemy import select, func
from backend.database import make_engine, session_factory
from backend.migrate import upgrade
from backend.models import User
from backend.launch import bootstrap
from backend.security import verify_password


def test_bootstrap_restart_preserves_password(tmp_path, monkeypatch):
    engine = make_engine('sqlite:///'+str(tmp_path/'bootstrap.db'))
    upgrade(engine)
    monkeypatch.setenv('BOOTSTRAP_ADMIN_LOGIN', 'operator')
    monkeypatch.setenv('BOOTSTRAP_ADMIN_PASSWORD', 'initial-long-password')
    bootstrap(engine)
    monkeypatch.setenv('BOOTSTRAP_ADMIN_PASSWORD', 'different-long-password')
    bootstrap(engine)
    with session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        user = session.scalar(select(User))
        assert user.role == 'admin'
        assert verify_password('initial-long-password', user.password_hash)
        user.role = 'student'
        session.commit()
    with pytest.raises(RuntimeError, match='non-admin'):
        bootstrap(engine)
    engine.dispose()
