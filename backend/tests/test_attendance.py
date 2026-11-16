from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select
from backend.tests.test_acceptance import client, auth, payload
from backend.attendance import process
from backend.models import Booking, Plan
from backend.seed import campus_now


def setup_booking(client):
    headers=auth(client)
    b=client.post('/api/bookings',headers=headers,json=payload()).json()
    start=(campus_now()+timedelta(days=1)).replace(hour=14,minute=0,second=0,microsecond=0)
    return b,headers,start


def tick(client, now, **kwargs):
    from backend.planning import serialize_writes
    with client.app.state.sessions() as s, patch('backend.planning.campus_now',return_value=now):
        serialize_writes(s)
        result=process(s,now=now,**kwargs)
        s.commit()
        return result


def continuous(client,start,end):
    current=start
    while current<=end:
        tick(client,current)
        current+=timedelta(minutes=1)


def test_no_show_deadline_queue_and_idempotence(client):
    b,h,start=setup_booking(client)
    other=auth(client,'student2')
    # Only room 4 is suitable by capacity/equipment in B? use capacity32 projector; B204 blocked explicitly.
    with client.app.state.sessions() as s:
        queue=Plan(kind='queue',user_id=2,token='test-no-show-queue',data={'state':'waiting','title':'Wait','building':'B','capacity':20,'equipment':['projector'],'slots':[{'date':b['date'],'startTime':'14:00','endTime':'15:00'}]})
        s.add(queue);s.commit()
    continuous(client,start-timedelta(minutes=10),start+timedelta(minutes=9))
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['status']=='active'
    assert tick(client,start+timedelta(minutes=10))==1
    assert tick(client,start+timedelta(minutes=10,seconds=30))==0
    item=client.get('/api/bookings/'+str(b['id']),headers=h).json()
    assert item['status']=='cancelled' and item['attendance']['state']=='cancelled'
    with client.app.state.sessions() as s:
        q=s.scalar(select(Plan).where(Plan.token=='test-no-show-queue'))
        assert q.data['state']=='offered'
        offer=s.get(Booking,q.data['bookingId'])
        assert offer.start_time=='14:11' and offer.end_time=='15:00'


def test_checkin_window_and_confirmed_never_cancelled(client):
    b,h,start=setup_booking(client)
    for delta,status in [(-11,409),(-10,200)]:
        with patch('backend.controls.campus_now',return_value=start+timedelta(minutes=delta)):
            assert client.post(f"/api/bookings/{b['id']}/check-in",headers=h).status_code==status
    continuous(client,start-timedelta(minutes=10),start+timedelta(minutes=11))
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['status']=='active'


def test_outage_restart_late_monitor_and_failure_preserve_bookings(client):
    b,h,start=setup_booking(client)
    tick(client,start-timedelta(minutes=10))
    tick(client,start+timedelta(minutes=10))
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['attendance']['state']=='protected'
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['status']=='active'


def test_http_failure_and_restart_protect(client):
    b,h,start=setup_booking(client)
    continuous(client,start-timedelta(minutes=10),start+timedelta(minutes=9))
    tick(client,start+timedelta(minutes=10),failure=start)
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['status']=='active'
    with client.app.state.sessions() as s:
        p=s.scalar(select(Plan).where(Plan.token=='attendance-'+str(b['id'])))
        p.data={**p.data,'state':'pending'};s.commit()
    tick(client,start+timedelta(minutes=10,seconds=30),startup=True)
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['attendance']['state']=='protected'

def test_late_first_observation_is_safe(client):
    b,h,start=setup_booking(client)
    tick(client,start+timedelta(minutes=10))
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['status']=='active'
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['attendance']['state']=='protected'


def test_checkin_and_cancellation_are_serialized(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from backend.planning import serialize_writes
    b,h,start=setup_booking(client)
    continuous(client,start-timedelta(minutes=10),start+timedelta(minutes=9))
    barrier=Barrier(2)
    def cancel():
        barrier.wait()
        return tick(client,start+timedelta(minutes=10))
    def confirm():
        barrier.wait()
        with patch('backend.controls.campus_now',return_value=start+timedelta(minutes=10)):
            return client.post('/api/bookings/'+str(b['id'])+'/check-in',headers=h).status_code
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(cancel);c=pool.submit(confirm)
        cancelled,status=a.result(),c.result()
    item=client.get('/api/bookings/'+str(b['id']),headers=h).json()
    assert (cancelled==0 and status==200 and item['checkedIn'] and item['status']=='active') or (cancelled==1 and status==409 and not item['checkedIn'] and item['status']=='cancelled')


def test_unconfirmed_queue_hold_is_not_a_no_show(client):
    b,h,start=setup_booking(client)
    with client.app.state.sessions() as s:
        s.add(Plan(kind='queue',user_id=1,token='held-no-show',data={'state':'offered','bookingId':b['id'],'expiresAt':(start+timedelta(hours=1)).isoformat(),'title':'Hold','building':'B','capacity':1,'equipment':[],'slots':[]}))
        s.commit()
    assert tick(client,start+timedelta(minutes=10))==0
    item=client.get('/api/bookings/'+str(b['id']),headers=h).json()
    assert item['status']=='active' and item['held']
    assert not item['attendance']


def test_unreachable_site_preserves_booking(client):
    b,h,start=setup_booking(client)
    continuous(client,start-timedelta(minutes=10),start+timedelta(minutes=9))
    tick(client,start+timedelta(minutes=10),reachable=False)
    assert client.get('/api/bookings/'+str(b['id']),headers=h).json()['status']=='active'
