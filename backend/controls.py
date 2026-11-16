"""Shared availability policies used by every booking write path."""
import secrets
from datetime import date, timedelta
from types import SimpleNamespace
from fastapi import Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import select, inspect
from .models import Booking, Plan, Room
from .schemas import Input, EQUIPMENT
from .seed import campus_now


def reject(code, message):
    raise HTTPException(409, detail={'code': code, 'message': message})


def restrictions(session, room_id, day):
    return [p for p in session.scalars(select(Plan).where(Plan.kind == 'restriction'))
            if p.data['roomId'] == room_id and p.data['date'] == str(day) and not p.data.get('closed')]


def blocked(session, room_id, day, start, end, requirements=()):
    return any(p.data['startTime'] < end and p.data['endTime'] > start and
               (not p.data['equipment'] or set(p.data['equipment']) & set(requirements))
               for p in restrictions(session, room_id, day))


def closure_slots(session, room_id, day):
    return [SimpleNamespace(room_id=room_id, start_time=p.data['startTime'], end_time=p.data['endTime'])
            for p in restrictions(session, room_id, day) if not p.data['equipment']]


def policy(session):
    p = session.scalar(select(Plan).where(Plan.kind == 'policy'))
    return p.data if p else Policy().model_dump()


def check(session, b, others=None):
    room = session.get(Room, b.room_id)
    if not room or not room.active or not set(b.requirements or []).issubset(room.equipment):
        reject('ROOM_UNAVAILABLE', 'Аудитория или нужное оборудование недоступны.')
    if blocked(session, b.room_id, b.date, b.start_time, b.end_time, b.requirements or []):
        reject('ROOM_RESTRICTED', 'На этот интервал действует ограничение аудитории или оборудования.')
    rules = policy(session)
    if not any(rules.values()):
        return
    duration = mins(b.end_time)-mins(b.start_time)
    if rules['maxDuration'] and duration > rules['maxDuration']:
        reject('QUOTA_DURATION', f"Максимальная длительность: {rules['maxDuration']} минут.")
    if rules['advanceDays'] and b.date > campus_now().date()+timedelta(days=rules['advanceDays']):
        reject('QUOTA_HORIZON', f"Бронировать можно не далее чем на {rules['advanceDays']} дней.")
    if others is None:
        others = list(session.scalars(select(Booking).where(Booking.status == 'active')))
    others = [x for x in others if x is not b and (not b.id or x.id != b.id) and x.status == 'active']
    week = b.date-timedelta(days=b.date.weekday())
    for field, limit in [('user_id', rules['weeklyMinutes']), ('team_id', rules['teamWeeklyMinutes'])]:
        if limit and getattr(b, field):
            used = sum(mins(x.end_time)-mins(x.start_time) for x in others if getattr(x, field) == getattr(b, field) and week <= x.date < week+timedelta(days=7))
            if used+duration > limit:
                reject('QUOTA_WEEK', f"Лимит {'команды' if field == 'team_id' else 'пользователя'}: {limit} минут за неделю. Новый период: {week+timedelta(days=7)}.")
    if rules['maxConcurrent']:
        # Sweep interval boundaries: adjacent bookings must not count simultaneously.
        points = [(b.start_time, 1), (b.end_time, -1)]
        for x in others:
            if x.user_id == b.user_id and x.date == b.date and x.start_time < b.end_time and x.end_time > b.start_time:
                points += [(max(x.start_time,b.start_time),1),(min(x.end_time,b.end_time),-1)]
        count = 0
        for _, delta in sorted(points):
            count += delta
            if count > rules['maxConcurrent']:
                reject('QUOTA_CONCURRENT', 'Достигнут лимит одновременных бронирований.')


def guard(session, _, __):
    changed = [b for b in session.new | session.dirty if isinstance(b, Booking) and (b.status or 'active') == 'active' and
               (b in session.new or any(inspect(b).attrs[k].history.has_changes() for k in ('date','start_time','end_time','room_id','status','requirements','team_id')))]
    if not changed:
        return
    with session.no_autoflush:
        existing = list(session.scalars(select(Booking).where(Booking.status == 'active')))
        existing += [b for b in session.new if isinstance(b, Booking)]
        for b in changed:
            # End-early operations must remain possible after a policy change.
            hist = inspect(b).attrs.end_time.history
            if b not in session.new and hist.deleted and b.end_time < hist.deleted[0]:
                continue
            check(session, b, existing)


def mins(value):
    h,m = map(int,value.split(':'))
    return h*60+m


class Policy(Input):
    weeklyMinutes: int = Field(0, ge=0, le=10080)
    teamWeeklyMinutes: int = Field(0, ge=0, le=10080)
    maxDuration: int = Field(0, ge=0, le=840)
    advanceDays: int = Field(0, ge=0, le=366)
    maxConcurrent: int = Field(0, ge=0, le=100)


class Restriction(Input):
    roomId: int = Field(gt=0)
    date: date
    startTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    endTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    equipment: list[str] = Field(default_factory=list, max_length=5)
    reason: str = Field(min_length=3, max_length=300)
    cancelAffected: bool = False

    @field_validator('equipment')
    @classmethod
    def known(cls, v):
        if set(v)-EQUIPMENT.keys():
            raise ValueError('Неизвестное оборудование')
        return sorted(set(v))


class EndTime(Input):
    endTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')


def install(app, sessions, current_user, admin, fail, validate_interval, audit, booking_json, room_json, free_intervals):
    from .planning import serialize_writes, refresh_queue

    @app.get('/api/booking-policy')
    def get_policy(user=Depends(current_user)):
        with sessions() as s:
            rules = policy(s)
            week = campus_now().date()-timedelta(days=campus_now().weekday())
            used = sum(mins(b.end_time)-mins(b.start_time) for b in s.scalars(select(Booking).where(Booking.user_id == user.id, Booking.status == 'active', Booking.date >= week, Booking.date < week+timedelta(days=7))))
            return {**rules, 'usedMinutes': used, 'resetsOn': str(week+timedelta(days=7))}

    @app.put('/api/admin/booking-policy')
    def put_policy(data: Policy, user=Depends(admin)):
        with sessions() as s:
            serialize_writes(s)
            p = s.scalar(select(Plan).where(Plan.kind == 'policy'))
            if not p:
                p = Plan(kind='policy', user_id=user.id, token='booking-policy', data={})
                s.add(p)
            p.data = data.model_dump()
            audit(s,user,'policy.update',None)
            s.commit()
            return p.data

    def affected(s, data):
        return [b for b in s.scalars(select(Booking).where(Booking.room_id == data.roomId, Booking.date == data.date, Booking.status == 'active', Booking.start_time < data.endTime, Booking.end_time > data.startTime))
                if not data.equipment or set(data.equipment)&set(b.requirements)]

    @app.post('/api/admin/restrictions/preview')
    def preview(data: Restriction, user=Depends(admin)):
        validate_interval(data.startTime,data.endTime)
        with sessions() as s:
            return [booking_json(s,b) for b in affected(s,data)]

    @app.get('/api/admin/restrictions')
    def list_restrictions(user=Depends(admin)):
        with sessions() as s:
            return [{'id':p.id,**p.data} for p in s.scalars(select(Plan).where(Plan.kind == 'restriction')) if not p.data.get('closed') and p.data['date'] >= str(campus_now().date())]

    @app.post('/api/admin/restrictions', status_code=201)
    def create_restriction(data: Restriction, user=Depends(admin)):
        validate_interval(data.startTime,data.endTime)
        if str(data.date)+'T'+data.endTime <= campus_now().isoformat()[:16]:
            fail(422,'PAST_RESTRICTION','Интервал уже прошёл.')
        with sessions() as s:
            serialize_writes(s)
            room = s.get(Room,data.roomId)
            if not room or not room.active or not set(data.equipment).issubset(room.equipment):
                fail(422,'INVALID_ROOM','Проверьте аудиторию и оборудование.')
            matches = affected(s,data)
            if matches and not data.equipment and not data.cancelAffected:
                fail(409,'AFFECTED_BOOKINGS','Есть брони. Подтвердите их отмену или измените интервал.')
            p = Plan(kind='restriction',user_id=user.id,token=secrets.token_urlsafe(32),data=data.model_dump(mode='json'))
            s.add(p)
            from .notifications import enqueue, recipients
            for b in matches:
                if data.cancelAffected:
                    b.status='cancelled'
                    audit(s,user,'booking.cancel',b.id)
                else:
                    for uid in recipients(s,b):
                        enqueue(s,uid,'meeting','Оборудование недоступно',data.reason,f'restriction:{p.token}:{b.id}:{uid}')
            s.flush()
            audit(s,user,'restriction.create',p.id)
            refresh_queue(s)
            s.commit()
            return {'id':p.id,'affected':len(matches)}

    @app.delete('/api/admin/restrictions/{rid}')
    def remove_restriction(rid:int,user=Depends(admin)):
        with sessions() as s:
            serialize_writes(s)
            p=s.get(Plan,rid)
            if not p or p.kind!='restriction':
                fail(404,'NOT_FOUND','Ограничение не найдено.')
            p.data={**p.data,'closed':True}
            audit(s,user,'restriction.close',p.id)
            s.flush()
            refresh_queue(s)
            s.commit()
            return {'closed':True}

    @app.get('/api/public/rooms/{rid}')
    def public_room(rid:int):
        with sessions() as s:
            room=s.get(Room,rid)
            if not room or not room.active:
                fail(404,'ROOM_NOT_FOUND','Аудитория недоступна.')
            now=campus_now()
            busy=list(s.scalars(select(Booking).where(Booking.room_id==rid,Booking.date==now.date(),Booking.status=='active')))+closure_slots(s,rid,now.date())
            return {'room':room_json(room),'date':str(now.date()),'now':now.strftime('%H:%M'),'freeSlots':free_intervals(busy),'busySlots':[{'startTime':b.start_time,'endTime':b.end_time} for b in busy], 'restrictions':[{'startTime':p.data['startTime'],'endTime':p.data['endTime'],'equipment':p.data['equipment']} for p in restrictions(s,rid,now.date())]}

    @app.post('/api/bookings/{bid}/check-in')
    def check_in(bid:int,user=Depends(current_user)):
        with sessions() as s:
            serialize_writes(s)
            b=owned(s,bid,user)
            now=campus_now()
            if b.date!=now.date() or not b.start_time<=now.strftime('%H:%M')<b.end_time:
                fail(409,'OUTSIDE_MEETING','Подтверждение доступно во время встречи.')
            b.checked_in=True
            audit(s,user,'booking.checkin',bid)
            s.commit()
            return booking_json(s,b)

    def owned(s,bid,user):
        b=s.get(Booking,bid)
        if not b or b.user_id!=user.id:
            fail(403,'FORBIDDEN','Изменять встречу может её организатор.')
        if b.status!='active' or any(p.data.get('state')=='offered' and p.data.get('bookingId')==bid for p in s.scalars(select(Plan).where(Plan.kind=='queue'))):
            fail(409,'BOOKING_INACTIVE','Сначала подтвердите бронь; отменённую изменить нельзя.')
        return b

    @app.patch('/api/bookings/{bid}/end-time')
    def end_time(bid:int,data:EndTime,user=Depends(current_user)):
        with sessions() as s:
            serialize_writes(s)
            refresh_queue(s)
            b=owned(s,bid,user)
            now=campus_now()
            if b.date!=now.date() or not b.start_time<=now.strftime('%H:%M')<b.end_time:
                fail(409,'OUTSIDE_MEETING','Изменение доступно во время встречи.')
            validate_interval(b.start_time,data.endTime)
            if data.endTime<now.strftime('%H:%M'):
                fail(422,'PAST_END','Окончание не может быть в прошлом.')
            conflict=s.scalar(select(Booking.id).where(Booking.id!=bid,Booking.room_id==b.room_id,Booking.date==b.date,Booking.status=='active',Booking.start_time<data.endTime,Booking.end_time>b.start_time))
            if conflict:
                fail(409,'BOOKING_CONFLICT','Продление пересекается со следующей бронью.')
            previous=b.end_time
            s.add(Plan(kind='meeting-log',user_id=user.id,token=secrets.token_urlsafe(32),data={'bookingId':bid,'previousEnd':previous,'newEnd':data.endTime,'changedAt':now.isoformat()}))
            b.end_time=data.endTime
            audit(s,user,'booking.endtime',bid)
            from .notifications import enqueue, recipients
            for uid in recipients(s,b):
                enqueue(s,uid,'meeting','Время встречи изменено',f'{b.date}: окончание {previous} → {b.end_time}',f'endtime:{bid}:{secrets.token_hex(8)}:{uid}')
            s.flush()
            refresh_queue(s)
            s.commit()
            return booking_json(s,b)
