from datetime import datetime, timedelta, timezone
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from .test_acceptance import client, auth
from backend.main import create_app
from backend.database import make_engine
from backend.migrate import upgrade, verify
from backend.models import AuthSession


def test_password_change_revokes_all_sessions(client):
    first, second = auth(client), auth(client)
    body = {'currentPassword':'wrong','newPassword':'a-new-long-password'}
    assert client.post('/api/auth/password', headers=first, json=body).status_code == 400
    body['currentPassword'] = 'campus2026'
    assert client.post('/api/auth/password', headers=first, json=body).status_code == 200
    for h in (first, second):
        assert client.get('/api/auth/me', headers=h).status_code == 401
    assert client.post('/api/auth/login', json={'login':'student1','password':'campus2026'}).status_code == 401
    assert client.post('/api/auth/login', json={'login':'student1','password':body['newPassword']}).status_code == 200


def test_logout_all_and_profile(client):
    first, second = auth(client), auth(client)
    result = client.patch('/api/auth/profile', headers=first, json={'displayName':'Новое имя'})
    assert result.json()['displayName'] == 'Новое имя'
    assert client.post('/api/auth/logout-all', headers=first).status_code == 200
    assert client.get('/api/auth/me', headers=second).status_code == 401
    admin = auth(client, 'admin')
    events = client.get('/api/admin/audit', headers=admin).json()
    assert {'profile.update','sessions.revoke_all'} <= {e['action'] for e in events}


def test_rate_limit_persists_and_has_retry_after(client):
    for _ in range(20):
        assert client.post('/api/auth/login', json={'login':'unknown','password':'wrong'}).status_code == 401
    response = client.post('/api/auth/login', json={'login':'unknown','password':'wrong'})
    assert response.status_code == 429
    assert int(response.headers['retry-after']) > 0
    assert 'wrong' not in response.text


def test_body_size_limit(client):
    assert client.post('/api/auth/login', content='x'*20000).status_code == 413


def test_invite_registration(tmp_path, monkeypatch):
    monkeypatch.setenv('REGISTRATION_MODE','invite')
    monkeypatch.setenv('REGISTRATION_INVITE_CODE','test-invitation-code')
    with TestClient(create_app('sqlite:///'+str(tmp_path/'invite.db'))) as c:
        body={'login':'invited','displayName':'Invited Student','password':'long-password'}
        assert c.post('/api/auth/register',json=body).status_code==403
        assert c.post('/api/auth/register',json={**body,'inviteCode':'test-invitation-code'}).status_code==201


def test_production_rejects_unsafe_configuration(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('REGISTRATION_MODE','closed')
    monkeypatch.setenv('SEED_DATA','false')
    with pytest.raises(RuntimeError,match='JWT_SECRET'):
        create_app(secret='short')
    with pytest.raises(RuntimeError,match='PostgreSQL'):
        create_app(database_url='sqlite:///:memory:', secret='x'*40)
    monkeypatch.setenv('SEED_DATA','true')
    with pytest.raises(RuntimeError,match='Demo seed'):
        create_app(secret='x'*40)


def test_migration_adopts_legacy_data(tmp_path):
    engine=make_engine('sqlite:///'+str(tmp_path/'legacy.db'))
    with engine.begin() as c:
        c.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, login VARCHAR(80) NOT NULL UNIQUE, password_hash VARCHAR(200) NOT NULL, role VARCHAR(20) NOT NULL, display_name VARCHAR(100) NOT NULL)'))
        c.execute(text("INSERT INTO users VALUES (1,'legacy','legacy-hash','student','Legacy user')"))
    upgrade(engine)
    upgrade(engine)
    verify(engine)
    with engine.connect() as c:
        assert c.scalar(text('SELECT display_name FROM users WHERE id=1'))=='Legacy user'
    engine.dispose()


def test_session_expiry_enforced_by_database(client):
    headers=auth(client)
    with client.app.state.sessions() as session:
        item=session.scalar(select(AuthSession).where(AuthSession.user_id==1))
        item.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        session.commit()
    assert client.get('/api/auth/me',headers=headers).status_code==401
