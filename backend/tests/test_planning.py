from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from backend.models import Plan
from backend.seed import campus_now
from backend.tests.test_acceptance import client, auth, payload


def plan_data(**changes):
    b = payload()
    return {'title': 'Командная встреча', 'building': 'B', 'capacity': 20,
            'equipment': ['projector'],
            'slots': [{k: b[k] for k in ('date', 'startTime', 'endTime')}], **changes}


def test_queue_hold_confirm_and_access(client):
    first, second = auth(client), auth(client, 'student2')
    p = client.post('/api/plans/queue', json=plan_data(), headers=first)
    assert p.status_code == 201, p.text
    p = p.json()
    assert p['state'] == 'offered'
    b = p['booking']
    assert client.post('/api/bookings', headers=second, json=payload(roomId=b['roomId'])).status_code == 409
    choice = {'slot': 0, 'roomId': b['roomId']}
    assert client.post(f"/api/plans/{p['id']}/confirm", headers=second, json=choice).status_code == 404
    assert client.post(f"/api/plans/{p['id']}/confirm", headers=first, json=choice).status_code == 200
    assert client.post(f"/api/plans/{p['id']}/confirm", headers=first, json=choice).status_code == 409
    assert client.delete(f"/api/plans/{p['id']}", headers=first).status_code == 200
    assert client.get(f"/api/bookings/{b['id']}", headers=first).json()['status'] == 'active'


def test_expiration_hands_slot_to_next_waiter(client):
    a, b = auth(client), auth(client, 'student2')
    # A dedicated room makes FIFO independent of the demo timetable.
    assert client.post('/api/admin/rooms', headers=auth(client, 'admin'), json={'name': 'FIFO', 'building': 'Q', 'floor': 1, 'capacity': 30, 'equipment': ['projector']}).status_code == 201
    data = plan_data(building='Q')
    first = client.post('/api/plans/queue', headers=a, json=data).json()
    second = client.post('/api/plans/queue', headers=b, json=data).json()
    assert first['state'] == 'offered'
    assert second['state'] == 'waiting'
    with client.app.state.sessions() as session:
        row = session.get(Plan, first['id'])
        row.data = {**row.data, 'expiresAt': (campus_now()-timedelta(minutes=1)).isoformat()}
        session.commit()
    assert client.get('/api/plans', headers=b).json()[0]['state'] == 'offered'
    assert client.get('/api/plans', headers=a).json()[0]['state'] == 'expired'


def test_shared_meeting_vote_update_and_confirm(client):
    headers = auth(client)
    p = client.post('/api/plans/meeting', headers=headers, json=plan_data()).json()
    url = '/api/meetings/'+p['token']
    public = client.get(url).json()
    assert 'token' not in public and 'booking' not in public
    vote = client.post(url+'/votes', json={'name': 'Участник', 'choices': [0]}).json()
    assert client.post(url+'/votes', json={'name': 'Участник', 'choices': [], **vote}).status_code == 200
    assert client.get(url).json()['voters'] == 1
    assert client.get(url).json()['options'][0]['votes'] == 0
    assert client.post(url+'/votes', json={'name': 'Участник', 'choices': [5]}).status_code == 422
    room = public['options'][0]['rooms'][0]['id']
    confirmed = client.post(f"/api/plans/{p['id']}/confirm", headers=headers, json={'slot': 0, 'roomId': room})
    assert confirmed.status_code == 200
    assert client.post(url+'/votes', json={'name': 'Поздний', 'choices': [0]}).status_code == 409
    public = client.get(url).json()
    assert public['booking']['confirmed'] is True
    assert 'user' not in public['booking'] and 'userId' not in public['booking']
    booking_id = confirmed.json()['id']
    client.delete(f'/api/bookings/{booking_id}', headers=headers)
    alternatives = client.get(f'/api/bookings/{booking_id}/alternatives', headers=headers).json()
    assert alternatives
    replacement = client.post(f'/api/bookings/{booking_id}/replace', headers=headers, json={'slot': 0, 'roomId': alternatives[0]['id']})
    assert replacement.status_code == 201
    assert client.get(url).json()['booking']['room']['id'] == alternatives[0]['id']


def test_replacement_permissions_and_conflict(client):
    headers, other = auth(client), auth(client, 'student2')
    booking = client.post('/api/bookings', headers=headers, json=payload()).json()
    assert client.get(f"/api/bookings/{booking['id']}/alternatives", headers=other).status_code == 404
    client.delete(f"/api/bookings/{booking['id']}", headers=auth(client, 'admin'))
    rooms = client.get(f"/api/bookings/{booking['id']}/alternatives", headers=headers).json()
    assert all(r['capacity'] >= booking['room']['capacity'] for r in rooms)
    assert rooms and all(set(booking['room']['equipment']).issubset(r['equipment']) for r in rooms)
    replacement = payload(roomId=rooms[0]['id'])
    assert client.post(f"/api/bookings/{booking['id']}/replace", headers=headers, json={'slot': 0, 'roomId': rooms[0]['id']}).status_code == 201
    assert client.post(f"/api/bookings/{booking['id']}/replace", headers=headers, json={'slot': 0, 'roomId': rooms[0]['id']}).status_code == 409
    assert client.post('/api/bookings', headers=other, json=replacement).status_code == 409


def test_plan_validation_and_duplicate(client):
    h = auth(client)
    assert client.post('/api/plans/queue', headers=h, json=plan_data(equipment=['unknown'])).status_code == 422
    assert client.post('/api/plans/queue', headers=auth(client, 'admin'), json=plan_data()).status_code == 403
    assert client.post('/api/plans/queue', headers=h, json=plan_data()).status_code == 201
    assert client.post('/api/plans/queue', headers=h, json=plan_data()).status_code == 409


def test_simultaneous_meeting_confirmation(client):
    h = auth(client)
    p = client.post('/api/plans/meeting', headers=h, json=plan_data()).json()
    choice = {'slot': 0, 'roomId': p['options'][0]['rooms'][0]['id']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: client.post(f"/api/plans/{p['id']}/confirm", headers=h, json=choice).status_code, range(2)))
    assert sorted(statuses) == [200, 409]
