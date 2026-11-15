import hashlib
from datetime import timedelta
import json

from backend.models import Plan
from backend.seed import campus_now
from backend.tests.test_acceptance import client, auth, payload


def data(**changes):
    return {**payload(date=(campus_now().date()+timedelta(days=20)).isoformat()), 'weeks': 3, **changes}


def test_team_roles_series_and_rsvp(client):
    a, b = auth(client), auth(client, 'student2')
    team = client.post('/api/teams', headers=a, json={'name': 'Команда'}).json()
    assert client.post('/api/teams/join', headers=b, json={'token': team['inviteToken']}).status_code == 200
    assert client.post('/api/series', headers=b, json=data(teamId=team['id'])).status_code == 403
    uid = client.get('/api/auth/me', headers=b).json()['id']
    assert client.patch(f"/api/teams/{team['id']}/members/{uid}", headers=a, json={'role': 'organizer'}).status_code == 200
    created = client.post('/api/series', headers=b, json=data(teamId=team['id']))
    assert created.status_code == 201, created.text
    sid = created.json()['id']
    assert len(client.get('/api/series', headers=a).json()[0]['bookings']) == 3
    assert client.post(f'/api/series/{sid}/rsvp', headers=a, json={'answer': 'yes'}).status_code == 200
    assert client.delete(f'/api/series/{sid}', headers=a).status_code == 404
    assert client.delete(f'/api/series/{sid}', headers=b).status_code == 200
    assert all(x['status'] == 'cancelled' for x in client.get('/api/series', headers=a).json()[0]['bookings'])


def test_series_atomic_conflicts_skip_edit(client):
    h = auth(client)
    assert client.post('/api/bookings', headers=h, json=data(weeks=3) | {}).status_code == 422  # Strict booking schema.
    occupied = payload(date=data()['date'])
    client.post('/api/bookings', headers=h, json=occupied)
    before = len(client.get('/api/bookings/my', headers=h).json())
    assert client.post('/api/series', headers=h, json=data()).status_code == 409
    assert len(client.get('/api/bookings/my', headers=h).json()) == before
    preview = client.post('/api/series/preview', headers=h, json=data()).json()
    assert preview[0]['conflict'] and not preview[1]['conflict']
    created = client.post('/api/series', headers=h, json=data(skip=[0])).json()
    assert len(created['bookingIds']) == 2
    updated = client.put('/api/series/'+str(created['id']), headers=h, json=data(roomId=1,weeks=2))
    assert updated.status_code == 200, updated.text
    assert len(updated.json()['bookingIds']) == 2
    assert client.post('/api/series', headers=h, json=data(weeks=13)).status_code == 422


def test_invite_rotation_and_removal(client):
    a, b = auth(client), auth(client, 'student2')
    t = client.post('/api/teams', headers=a, json={'name': 'Проект'}).json()
    new = client.post(f"/api/teams/{t['id']}/invite", headers=a).json()
    assert client.post('/api/teams/join', headers=b, json={'token': t['inviteToken']}).status_code == 404
    client.post('/api/teams/join', headers=b, json={'token': new['inviteToken']})
    assert client.get('/api/teams', headers=b).json()[0]['inviteToken'] == ''
    uid = client.get('/api/auth/me', headers=b).json()['id']
    assert client.patch(f"/api/teams/{t['id']}/members/{uid}", headers=b, json={'role':'organizer'}).status_code == 403
    assert client.patch(f"/api/teams/{t['id']}/members/{uid}", headers=b, json={'role':'remove'}).status_code == 200
    assert not client.get('/api/teams', headers=b).json()


def test_team_poll_requires_organizer(client):
    from backend.tests.test_planning import plan_data
    a,b = auth(client),auth(client,'student2')
    team = client.post('/api/teams', headers=a, json={'name':'Голосование'}).json()
    client.post('/api/teams/join', headers=b, json={'token':team['inviteToken']})
    assert client.post('/api/plans/meeting', headers=b, json=plan_data(teamId=team['id'])).status_code == 403
    poll = client.post('/api/plans/meeting', headers=a, json=plan_data(teamId=team['id']))
    assert poll.status_code == 201
    assert client.get('/api/teams', headers=b).json()[0]['meetings'][0]['token'] == poll.json()['token']


def test_concurrent_series_never_partially_books(client):
    from concurrent.futures import ThreadPoolExecutor
    h = auth(client)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _:client.post('/api/series', headers=h, json=data()), range(2)))
    assert sorted(r.status_code for r in responses) == [201,409]
    assert len(client.get('/api/series', headers=h).json()) == 1


def test_email_unconfigured_and_protected_job(client, monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    assert not client.get('/api/email', headers=auth(client)).json()['configured']
    assert client.put('/api/email', headers=auth(client), json={'email':'test@example.com'}).status_code == 503
    assert client.post('/api/jobs/notifications').status_code == 401


def test_email_verify_outbox_retry_and_preferences(client, monkeypatch):
    for k, v in {'RESEND_API_KEY':'fake-test-key','MAIL_FROM':'Campus <test@example.com>','PUBLIC_URL':'https://campus.example','NOTIFICATIONS_JOB_SECRET':'x'*40}.items():
        monkeypatch.setenv(k,v)
    h = auth(client)
    assert client.put('/api/email', headers=h, json={'email':'student@example.com'}).status_code == 200
    with client.app.state.sessions() as session:
        mail = next(p for p in session.query(Plan).filter_by(kind='outbox'))
        token = mail.data['body'].split('=')[-1]
    jobs={'Authorization':'Bearer '+'x'*40}
    def unavailable(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr('backend.notifications.urllib.request.urlopen', unavailable)
    assert client.post('/api/jobs/notifications', headers=jobs).json()['sent'] == 0
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"id":"provider-test-id"}'
    monkeypatch.setattr('backend.notifications.urllib.request.urlopen', lambda *args,**kwargs:Response())
    assert client.post('/api/jobs/notifications', headers=jobs).json()['sent'] == 1
    assert client.post('/api/jobs/notifications', headers=jobs).json()['sent'] == 0
    assert client.post('/api/email/verify', json={'token':token}).status_code == 200
    assert client.post('/api/email/verify', json={'token':token}).status_code == 400
    assert client.get('/api/email', headers=h).json()['verified']
    assert client.put('/api/email', headers=h, json={'email':'student@example.com','meeting':False}).status_code == 200
    client.post('/api/bookings', headers=h, json=payload())
    with client.app.state.sessions() as session:
        assert len(session.query(Plan).filter_by(kind='outbox').all()) == 1
