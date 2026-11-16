"""Fail-open attendance enforcement: uncertainty always preserves the reservation."""
import secrets
from datetime import datetime, timedelta
from sqlalchemy import select
from .models import Plan, Booking, AuditEvent
from .seed import campus_now


def attendance_json(session, booking):
    p=session.scalar(select(Plan).where(Plan.token=='attendance-'+str(booking.id)))
    return p.data if p else {}


def process(session, *, now=None, failure=None, startup=False, reachable=True):
    from .planning import refresh_queue
    from .notifications import enqueue, recipients
    now=now or campus_now()
    bookings=list(session.scalars(select(Booking).where(Booking.status=='active',Booking.checked_in.is_(False),Booking.date==now.date())))
    held={p.data.get('bookingId') for p in session.scalars(select(Plan).where(Plan.kind=='queue')) if p.data.get('state')=='offered'}
    cancelled=0
    for b in bookings:
        if b.id in held:
            continue
        start=now.replace(hour=int(b.start_time[:2]),minute=int(b.start_time[3:]),second=0,microsecond=0)
        end=now.replace(hour=int(b.end_time[:2]),minute=int(b.end_time[3:]),second=0,microsecond=0)
        opening,deadline=start-timedelta(minutes=10),min(start+timedelta(minutes=10),end)
        if now<opening or now>=end:
            continue
        p=session.scalar(select(Plan).where(Plan.token=='attendance-'+str(b.id)))
        if not p:
            p=Plan(kind='attendance',user_id=b.user_id,token='attendance-'+str(b.id),data={'bookingId':b.id,'deadline':deadline.isoformat(),'lastSeen':now.isoformat(),'state':'pending'})
            if now>opening+timedelta(seconds=60):
                p.data={**p.data,'state':'protected','reason':'late-monitor'}
            session.add(p)
            for uid in recipients(session,b):
                enqueue(session,uid,'meeting','Подтверди начало встречи',f'{b.date} {b.start_time}. Подтверди начало в «Моих бронированиях» до {deadline:%H:%M}, иначе аудитория может быть освобождена.',f'attendance-warning:{b.id}:{uid}')
        data=dict(p.data)
        last=datetime.fromisoformat(data['lastSeen'])
        gap=(now-last).total_seconds()
        if not reachable or startup or gap>90 or gap<0 or (failure and failure>=opening):
            data.update(state='protected',reason='service-interruption')
        data['lastSeen']=now.isoformat()
        if data['state']=='pending' and now>=deadline:
            # Never catch up missed cancellations, or cancel short meetings already ended.
            if now>deadline+timedelta(seconds=90):
                data.update(state='protected',reason='late-job')
            else:
                b.status='cancelled'
                data.update(state='cancelled',cancelledAt=now.isoformat(),reason='no-check-in')
                session.add(AuditEvent(actor_id=None,action='booking.no_show',entity_id=b.id))
                for uid in recipients(session,b):
                    enqueue(session,uid,'meeting','Аудитория освобождена: начало не подтверждено',f'{b.date} {b.start_time}–{b.end_time}. Бронь №{b.id} отменена; проверь свободное время в CampusFlow.',f'attendance-cancel:{b.id}:{uid}')
                transfer_remaining(session,b,now)
                cancelled+=1
        p.data=data
    session.flush()
    refresh_queue(session)
    return cancelled


def transfer_remaining(session, booking, now):
    """Waiting requests keep FIFO order; offer only the unused future remainder."""
    from .models import Room
    room=session.get(Room,booking.room_id)
    start=(now+timedelta(minutes=1)).strftime('%H:%M')
    for p in session.scalars(select(Plan).where(Plan.kind=='queue').order_by(Plan.id)):
        d=dict(p.data)
        if d.get('state')!='waiting' or room.capacity<d['capacity'] or (d['building'] and d['building']!=room.building) or not set(d['equipment']).issubset(room.equipment):
            continue
        slots=[]
        for slot in d['slots']:
            if slot['date']==str(booking.date) and slot['startTime']<start<slot['endTime']<=booking.end_time:
                slots.append({**slot,'startTime':start})
            else:
                slots.append(slot)
        p.data={**d,'slots':slots}
