from datetime import timedelta
from unittest.mock import patch
from backend.seed import campus_now
from backend.tests.test_acceptance import client, auth, payload


def test_policy_applies_to_normal_series_and_queue(client):
    admin,s=auth(client,'admin'),auth(client)
    assert client.put('/api/admin/booking-policy',headers=s,json={'maxDuration':30}).status_code==403
    assert client.put('/api/admin/booking-policy',headers=admin,json={'maxDuration':30}).status_code==200
    assert client.post('/api/bookings',headers=s,json=payload()).json()['error']['code']=='QUOTA_DURATION'
    assert client.post('/api/series',headers=s,json={**payload(),'weeks':2}).status_code==409
    q=client.post('/api/plans/queue',headers=s,json={'title':'Queue policy','capacity':1,'equipment':[],'building':'','slots':[{k:v for k,v in payload().items() if k in ('date','startTime','endTime')}]})
    assert q.status_code==201,q.text
    plans=client.get('/api/plans',headers=s)
    assert plans.status_code==200,plans.text
    assert plans.json()[0]['state']=='waiting'
    assert client.post('/api/bookings',headers=s,json=payload(endTime='14:30')).status_code==201


def test_restriction_preview_cancel_privacy_and_equipment(client):
    admin,s=auth(client,'admin'),auth(client)
    b=client.post('/api/bookings',headers=s,json=payload(requirements=['projector'])).json()
    restriction={**{k:v for k,v in payload().items() if k in ('roomId','date','startTime','endTime')},'reason':'Projector repair','equipment':['projector']}
    preview=client.post('/api/admin/restrictions/preview',headers=admin,json=restriction)
    assert len(preview.json())==1
    assert client.post('/api/admin/restrictions',headers=admin,json={**restriction,'cancelAffected':True}).status_code==201
    assert client.get('/api/bookings/'+str(b['id']),headers=s).json()['status']=='cancelled'
    assert client.post('/api/bookings',headers=s,json=payload(requirements=['projector'])).status_code==409
    assert client.post('/api/bookings',headers=s,json=payload()).status_code==201
    public=client.get('/api/public/rooms/4')
    assert public.status_code==200
    assert 'userId' not in public.text and 'comment' not in public.text and 'login' not in public.text
    full={**restriction,'equipment':[]}
    assert client.post('/api/admin/restrictions',headers=admin,json=full).status_code==409
    response=client.post('/api/admin/restrictions',headers=admin,json={**full,'cancelAffected':True})
    assert response.status_code==201,response.text
    assert client.post('/api/bookings',headers=s,json=payload()).status_code==409
    assert client.delete('/api/admin/restrictions/'+str(response.json()['id']),headers=admin).status_code==200
    assert client.post('/api/bookings',headers=s,json=payload()).status_code==201


def test_current_meeting_controls_and_boundary(client):
    s,other=auth(client),auth(client,'student2')
    b=client.post('/api/bookings',headers=s,json=payload()).json()
    next_b=client.post('/api/bookings',headers=other,json=payload(startTime='15:00',endTime='16:00'))
    assert next_b.status_code==201
    now=(campus_now()+timedelta(days=1)).replace(hour=14,minute=30,second=0,microsecond=0)
    with patch('backend.controls.campus_now',return_value=now):
        assert client.post(f"/api/bookings/{b['id']}/check-in",headers=other).status_code==403
        assert client.post(f"/api/bookings/{b['id']}/check-in",headers=s).json()['checkedIn']
        assert client.patch(f"/api/bookings/{b['id']}/end-time",headers=s,json={'endTime':'15:30'}).status_code==409
        assert client.patch(f"/api/bookings/{b['id']}/end-time",headers=s,json={'endTime':'14:30'}).status_code==200
    assert client.get(f"/api/bookings/{b['id']}",headers=s).json()['endTime']=='14:30'


def test_weekly_quota_series_rolls_back(client):
    admin,s=auth(client,'admin'),auth(client)
    assert client.put('/api/admin/booking-policy',headers=admin,json={'weeklyMinutes':30}).status_code==200
    before=client.get('/api/bookings/my',headers=s).json()
    result=client.post('/api/series',headers=s,json={**payload(),'weeks':2})
    assert result.status_code==409
    assert client.get('/api/bookings/my',headers=s).json()==before

def test_team_quota_cannot_be_bypassed_by_other_organizer(client):
    admin,s1,s2=auth(client,'admin'),auth(client),auth(client,'student2')
    team=client.post('/api/teams',headers=s1,json={'name':'Quota team'}).json()
    client.post('/api/teams/join',headers=s2,json={'token':team['inviteToken']})
    uid=client.get('/api/auth/me',headers=s2).json()['id']
    assert client.patch(f"/api/teams/{team['id']}/members/{uid}",headers=s1,json={'role':'organizer'}).status_code==200
    assert client.put('/api/admin/booking-policy',headers=admin,json={'teamWeeklyMinutes':60}).status_code==200
    first=client.post('/api/series',headers=s1,json={**payload(),'weeks':1,'teamId':team['id']})
    assert first.status_code==201,first.text
    second=client.post('/api/series',headers=s2,json={**payload(startTime='16:00',endTime='17:00'),'weeks':1,'teamId':team['id']})
    assert second.status_code==409,second.text
    assert second.json()['error']['code']=='QUOTA_WEEK'


def test_concurrent_quota_only_one_booking_wins(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    admin,s=auth(client,'admin'),auth(client)
    # A later week has no seed bookings.
    day=(campus_now().date()+timedelta(days=30)).isoformat()
    client.put('/api/admin/booking-policy',headers=admin,json={'weeklyMinutes':60})
    barrier=Barrier(2)
    def book(room):
        barrier.wait()
        return client.post('/api/bookings',headers=s,json=payload(roomId=room,date=day)).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(book,[3,6]))==[201,409]
