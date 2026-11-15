from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.engine import make_url
from backend.database import make_engine
from threading import Barrier

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.seed import campus_now


@pytest.fixture
def client(tmp_path):
    url = os.getenv('TEST_DATABASE_URL')
    control, schema = None, None
    if url:
        # Isolate every test in a new namespace; never drop or reset public tables.
        control, schema = make_engine(url), 'test_'+uuid4().hex
        with control.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = str(make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False))
    app = create_app(url or 'sqlite:///'+str(tmp_path/'test.db'), secret='test-secret-at-least-thirty-two-characters')
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        if control:
            with control.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            control.dispose()


def auth(client, login='student1'):
    response = client.post('/api/auth/login', json={'login': login, 'password': 'campus2026'})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer '+response.json()['accessToken']}


def payload(**kwargs):
    return {'roomId': 4, 'date': (campus_now().date()+timedelta(days=1)).isoformat(), 'startTime': '14:00', 'endTime': '15:00', 'comment': 'Приёмка', **kwargs}


def test_all_eight_acceptance_scenarios(client):
    s1, s2, admin = auth(client), auth(client, 'student2'), auth(client, 'admin')
    rooms = client.get('/api/rooms?building=B&minCapacity=20&equipment=projector', headers=s1)
    assert rooms.status_code == 200
    assert {r['name'] for r in rooms.json()} == {'101', '204'}
    assert len(client.get('/api/rooms', headers=s1).json()) >= 10
    data = payload()
    slots_url = f"/api/rooms/4/free-slots?date={data['date']}"
    assert any(s['startTime'] <= '14:00' and s['endTime'] >= '15:00' for s in client.get(slots_url, headers=s1).json()['freeSlots'])
    created = client.post('/api/bookings', headers=s1, json=data)
    assert created.status_code == 201, created.text
    booking_id = created.json()['id']
    assert any(b['id'] == booking_id for b in client.get('/api/bookings/my', headers=s1).json())
    conflict = client.post('/api/bookings', headers=s2, json=data)
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'BOOKING_CONFLICT'
    for method in [client.get, client.delete]:
        assert method(f'/api/bookings/{booking_id}', headers=s2).status_code == 403
    assert client.get(f'/api/bookings/{booking_id}', headers=s1).json()['status'] == 'active'
    assert client.delete(f'/api/bookings/{booking_id}', headers=s1).json()['status'] == 'cancelled'
    assert any(s['startTime'] <= '14:00' and s['endTime'] >= '15:00' for s in client.get(slots_url, headers=s1).json()['freeSlots'])
    assert any(b['id'] == booking_id and b['status'] == 'cancelled' for b in client.get('/api/bookings/my', headers=s1).json())
    other = client.post('/api/bookings', headers=s2, json=data).json()
    assert any(b['id'] == other['id'] for b in client.get('/api/admin/bookings', headers=admin).json())
    assert client.delete(f"/api/admin/bookings/{other['id']}", headers=admin).status_code == 200
    assert client.get('/api/admin/bookings', headers=s1).status_code == 403
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').status_code == 200
    assert client.get('/api/health').json() == {'status': 'ok'}


@pytest.mark.parametrize('start,end,expected', [('13:00','14:00',201),('15:00','16:00',201),('13:30','14:30',409),('14:30','15:30',409),('14:15','14:45',409),('13:00','16:00',409),('14:00','15:00',409)])
def test_half_open_intervals(client, start, end, expected):
    headers = auth(client)
    assert client.post('/api/bookings', headers=headers, json=payload()).status_code == 201
    assert client.post('/api/bookings', headers=headers, json=payload(startTime=start, endTime=end)).status_code == expected


def test_concurrent_requests_only_one_wins(client):
    headers = [auth(client), auth(client, 'student2')]
    barrier = Barrier(2)
    def book(h):
        barrier.wait(timeout=10)
        return client.post('/api/bookings', headers=h, json=payload()).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(book, headers))
    assert sorted(codes) == [201, 409]


@pytest.mark.parametrize('changes', [{'startTime':'15:00','endTime':'14:00'}, {'startTime':'14:00','endTime':'14:00'}, {'startTime':'07:00'}, {'endTime':'23:00'}, {'startTime':'not-time'}, {'date':'2020-01-01'}, {'roomId':0}, {'comment':'a'*301}])
def test_invalid_booking_input(client, changes):
    assert client.post('/api/bookings', headers=auth(client), json=payload(**changes)).status_code == 422


def test_authorization_matrix(client):
    student, admin = auth(client), auth(client, 'admin')
    assert client.get('/api/bookings/my').status_code == 401
    assert client.post('/api/bookings', headers=admin, json=payload()).status_code == 403
    room = {'name':'999','building':'A','floor':1,'capacity':30,'equipment':['projector']}
    assert client.post('/api/admin/rooms', headers=student, json=room).status_code == 403
    assert client.put('/api/admin/rooms/1', headers=student, json=room).status_code == 403
    assert client.delete('/api/admin/rooms/1', headers=student).status_code == 403
    assert client.get('/api/admin/stats', headers=student).status_code == 403
    assert client.get('/api/admin/bookings.csv', headers=student).status_code == 403
    assert client.get('/api/rooms', headers={'Authorization':'Bearer invalid'}).status_code == 401


def test_registration_and_session(client):
    body = {'login':'new.student','displayName':'Новый Студент','password':'strong-password'}
    result = client.post('/api/auth/register', json=body)
    assert result.status_code == 201
    assert result.json()['user']['role'] == 'student'
    assert 'password' not in result.text
    headers = {'Authorization':'Bearer '+result.json()['accessToken']}
    assert client.get('/api/auth/me', headers=headers).json()['displayName'] == 'Новый Студент'
    assert client.post('/api/auth/register', json=body).status_code == 409
    assert client.post('/api/auth/register', json={**body,'login':'evil','role':'admin'}).status_code == 422
    assert client.post('/api/auth/register', json={**body,'password':'123'}).status_code == 422
    assert client.post('/api/auth/login', json={'login':body['login'],'password':'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'login':body['login'],'password':body['password']}).status_code == 200
    token = jwt.encode({'sub':'1','exp':1}, 'test-secret-at-least-thirty-two-characters', algorithm='HS256')
    assert client.get('/api/auth/me', headers={'Authorization':'Bearer '+token}).status_code == 401


def test_room_crud_and_history(client):
    admin, student = auth(client,'admin'), auth(client)
    body = {'name':'999','building':'D','floor':2,'capacity':25,'equipment':['projector','wifi']}
    result = client.post('/api/admin/rooms', headers=admin, json=body)
    assert result.status_code == 201
    room_id = result.json()['id']
    assert client.post('/api/admin/rooms', headers=admin, json=body).status_code == 409
    assert client.put(f'/api/admin/rooms/{room_id}', headers=admin, json={**body,'capacity':40}).json()['capacity'] == 40
    booking = client.post('/api/bookings', headers=student, json=payload(roomId=room_id)).json()
    assert client.delete(f'/api/admin/rooms/{room_id}', headers=admin).status_code == 409
    assert client.delete(f"/api/admin/bookings/{booking['id']}", headers=admin).status_code == 200
    assert client.delete(f'/api/admin/rooms/{room_id}', headers=admin).status_code == 200
    assert client.get(f'/api/rooms/{room_id}', headers=student).status_code == 404
    assert client.get(f"/api/bookings/{booking['id']}", headers=student).json()['room']['name'] == '999'
    assert client.post('/api/bookings', headers=student, json=payload(roomId=room_id)).status_code == 404


def test_search_availability_privacy_stats_csv(client):
    student, admin = auth(client), auth(client,'admin')
    data = payload(comment='=HYPERLINK("bad")')
    booking = client.post('/api/bookings', headers=student, json=data).json()
    result = client.get('/api/rooms', params={'date':data['date'],'startTime':'14:00','endTime':'15:00'}, headers=student)
    assert result.status_code == 200
    assert 4 not in [r['id'] for r in result.json()]
    busy = client.get('/api/rooms', params={'date':data['date']}, headers=student).json()
    assert all(set(slot) == {'startTime','endTime'} for r in busy for slot in r['busySlots'])
    assert client.get('/api/rooms?startTime=10:00', headers=student).status_code == 422
    assert client.get('/api/rooms?equipment=unknown', headers=student).status_code == 422
    stats = client.get('/api/admin/stats', params={'date':data['date']}, headers=admin).json()
    assert stats['roomCount'] == 12
    assert len(stats['rows']) == 21
    before = stats['occupiedHours']
    csv_result = client.get('/api/admin/bookings.csv', headers=admin)
    assert csv_result.status_code == 200
    assert "'=HYPERLINK" in csv_result.text
    client.delete(f"/api/bookings/{booking['id']}", headers=student)
    after = client.get('/api/admin/stats', params={'date':data['date']}, headers=admin).json()['occupiedHours']
    assert before-after == 1


def test_restart_preserves_seed_and_bookings(tmp_path):
    url = 'sqlite:///'+str(tmp_path/'persistent.db')
    with TestClient(create_app(url)) as first:
        h = auth(first)
        booking = first.post('/api/bookings', headers=h, json=payload()).json()
        count = len(first.get('/api/bookings/my', headers=h).json())
    with TestClient(create_app(url)) as second:
        h = auth(second)
        assert len(second.get('/api/rooms', headers=h).json()) == 12
        assert len(second.get('/api/bookings/my', headers=h).json()) == count
        assert second.get(f"/api/bookings/{booking['id']}", headers=h).json()['status'] == 'active'
