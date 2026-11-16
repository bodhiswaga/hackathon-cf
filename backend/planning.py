"""Transactional queue and capability-link meeting polls; no external worker needed."""
import secrets
from datetime import date, timedelta

from fastapi import Depends, Request, HTTPException
from .controls import blocked, check
from pydantic import Field
from sqlalchemy import select, text

from .models import Booking, Plan, Room
from .schemas import Input, EQUIPMENT
from .seed import campus_now
from .limiter import consume


class Slot(Input):
    date: date
    startTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    endTime: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')


class PlanInput(Input):
    title: str = Field(min_length=2, max_length=100)
    building: str = Field(default='', max_length=30)
    capacity: int = Field(default=1, ge=1, le=1000)
    equipment: list[str] = Field(default_factory=list, max_length=5)
    slots: list[Slot] = Field(min_length=1, max_length=20)
    teamId: int | None = Field(default=None, gt=0)


class Vote(Input):
    name: str = Field(min_length=2, max_length=80)
    choices: list[int] = Field(max_length=20)
    voterToken: str = Field(default='', max_length=64)


class Choice(Input):
    slot: int = Field(ge=0, le=19)
    roomId: int = Field(gt=0)


def serialize_writes(session):
    if session.bind.dialect.name == 'sqlite':
        session.execute(text('BEGIN IMMEDIATE'))
    else:
        session.execute(text('SELECT pg_advisory_xact_lock(73201841)'))


def refresh_queue(session):
    now = campus_now()
    plans = session.scalars(select(Plan).where(Plan.kind == 'queue').order_by(Plan.id)).all()
    for plan in plans:
        data = dict(plan.data)
        if data.get('state') == 'offered':
            booking = session.get(Booking, data['bookingId'])
            if data['expiresAt'] <= now.isoformat() or booking.status != 'active':
                booking.status = 'cancelled'
                data['state'] = 'expired'
                plan.data = data
    session.flush()
    for plan in plans:
        data = dict(plan.data)
        if data.get('state') != 'waiting':
            continue
        future = [s for s in data['slots'] if s['date']+'T'+s['startTime'] > now.isoformat()[:16]]
        if not future:
            if all(s['date']+'T'+s['endTime'] <= now.isoformat()[:16] for s in data['slots']):
                data['state'] = 'expired'
        else:
            for slot in future:
                available = candidates(session, data, slot)
                if available:
                    booking = Booking(room_id=available[0].id, user_id=plan.user_id,
                                      date=date.fromisoformat(slot['date']), start_time=slot['startTime'],
                                      end_time=slot['endTime'], comment=data['title'], requirements=data['equipment'], team_id=data.get('teamId'))
                    try:
                        check(session,booking)
                    except HTTPException:
                        continue
                    session.add(booking)
                    session.flush()
                    data.update(state='offered', bookingId=booking.id,
                                expiresAt=(now+timedelta(minutes=5)).isoformat())
                    break
        plan.data = data
        session.flush()


def candidates(session, data, slot):
    rooms = session.scalars(select(Room).where(Room.active.is_(True), Room.capacity >= data['capacity']).order_by(Room.capacity, Room.building, Room.name)).all()
    busy = set(session.scalars(select(Booking.room_id).where(Booking.status == 'active', Booking.date == date.fromisoformat(slot['date']), Booking.start_time < slot['endTime'], Booking.end_time > slot['startTime'])))
    return [r for r in rooms if r.id not in busy and (not data['building'] or r.building == data['building']) and set(data['equipment']).issubset(r.equipment) and not blocked(session,r.id,slot['date'],slot['startTime'],slot['endTime'],data['equipment'])]


def install(app, sessions, current_user, fail, validate_interval, room_json, booking_json, audit, secret):
    def student(user=Depends(current_user)):
        if user.role != 'student':
            fail(403, 'FORBIDDEN', 'Планирование доступно студентам.')
        return user

    def owned(session, plan_id, user):
        plan = session.get(Plan, plan_id)
        if not plan or plan.user_id != user.id:
            fail(404, 'PLAN_NOT_FOUND', 'План не найден.')
        return plan

    def public(session, token):
        plan = session.scalar(select(Plan).where(Plan.token == token, Plan.kind == 'meeting'))
        if not plan:
            fail(404, 'PLAN_NOT_FOUND', 'Ссылка недействительна.')
        return plan

    def result(session, plan, private=True):
        data = plan.data
        value = {'id': plan.id, 'kind': plan.kind, 'title': data['title'], 'state': data['state'], 'slots': data['slots']}
        if private:
            value.update(token=plan.token, expiresAt=data.get('expiresAt'))
        if data.get('bookingId'):
            booking = session.get(Booking, data['bookingId'])
            # Shared links continue to point to the current room after a repair.
            visited = set()
            while booking.status == 'cancelled' and booking.id not in visited:
                visited.add(booking.id)
                repair = session.scalar(select(Plan).where(Plan.kind == 'repair', Plan.token == 'repair-'+str(booking.id)))
                if not repair:
                    break
                booking = session.get(Booking, repair.data['bookingId'])
            value['booking'] = booking_json(session, booking) if private else {'confirmed': True, 'date': booking.date.isoformat(), 'startTime': booking.start_time, 'endTime': booking.end_time, 'status': booking.status, 'room': room_json(session.get(Room, booking.room_id))}
        if plan.kind == 'meeting':
            votes = list(data.get('votes', {}).values())
            value['voters'] = len(votes)
            value['options'] = [{'index': i, **s, 'votes': sum(i in v['choices'] for v in votes), 'rooms': [room_json(r) for r in candidates(session, data, s)][:3]} for i, s in enumerate(data['slots'])]
        return value

    @app.post('/api/plans/{kind}', status_code=201, tags=['Planning'])
    def create(kind: str, data: PlanInput, user=Depends(student)):
        if kind not in ('queue', 'meeting'):
            fail(404, 'NOT_FOUND', 'Неизвестный тип плана.')
        if set(data.equipment) - EQUIPMENT.keys():
            fail(422, 'INVALID_EQUIPMENT', 'Неизвестное оборудование.')
        for slot in data.slots:
            validate_interval(slot.startTime, slot.endTime)
            if slot.date.isoformat()+'T'+slot.startTime <= campus_now().isoformat()[:16]:
                fail(422, 'PAST_BOOKING', 'Выберите будущие интервалы.')
        with sessions() as session:
            serialize_writes(session)
            if data.teamId:
                from .community import member
                member(session, data.teamId, user, fail, True)
            active = session.scalars(select(Plan).where(Plan.user_id == user.id, Plan.kind.in_(['queue', 'meeting']))).all()
            if sum(p.data['state'] in ('waiting', 'open', 'offered') for p in active) >= 10:
                fail(409, 'PLAN_LIMIT', 'Можно иметь не больше 10 открытых планов.')
            if kind == 'queue' and any(p.kind == kind and p.data['state'] in ('waiting', 'offered') and p.data['slots'] == data.model_dump(mode='json')['slots'] for p in active):
                fail(409, 'DUPLICATE_PLAN', 'Такая заявка уже есть.')
            plan = Plan(user_id=user.id, kind=kind, token=secrets.token_urlsafe(32), data={**data.model_dump(mode='json'), 'state': 'waiting' if kind == 'queue' else 'open', 'votes': {}})
            session.add(plan)
            session.flush()
            refresh_queue(session)
            audit(session, user, 'plan.create', plan.id)
            if data.teamId and kind == 'meeting':
                from .notifications import enqueue
                import os
                team = session.get(Plan, data.teamId)
                for uid in team.data['members']:
                    enqueue(session, int(uid), 'meeting', 'Выберите время: '+data.title, os.getenv('PUBLIC_URL', '')+'/#meeting='+plan.token, 'poll:'+str(plan.id)+':'+uid)
            session.commit()
            return result(session, plan)

    @app.get('/api/plans', tags=['Planning'])
    def mine(user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            refresh_queue(session)
            session.commit()
            return [result(session, p) for p in session.scalars(select(Plan).where(Plan.user_id == user.id, Plan.kind.in_(['queue', 'meeting'])).order_by(Plan.id.desc()))]

    @app.delete('/api/plans/{plan_id}', tags=['Planning'])
    def close(plan_id: int, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            plan = owned(session, plan_id, user)
            data = dict(plan.data)
            if data['state'] == 'offered':
                session.get(Booking, data['bookingId']).status = 'cancelled'
            data['state'] = 'closed'
            plan.data = data
            session.flush()
            refresh_queue(session)
            session.commit()
            return {'closed': True}

    @app.post('/api/plans/{plan_id}/confirm', tags=['Planning'])
    def confirm(plan_id: int, choice: Choice, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            refresh_queue(session)
            plan = owned(session, plan_id, user)
            data = dict(plan.data)
            if data['state'] == 'offered':
                booking = session.get(Booking, data['bookingId'])
            elif plan.kind == 'meeting' and data['state'] == 'open':
                if choice.slot >= len(data['slots']):
                    fail(422, 'INVALID_SLOT', 'Нет такого интервала.')
                slot = data['slots'][choice.slot]
                if slot['date']+'T'+slot['startTime'] <= campus_now().isoformat()[:16]:
                    fail(422, 'PAST_BOOKING', 'Время уже прошло.')
                if choice.roomId not in [r.id for r in candidates(session, data, slot)]:
                    fail(409, 'BOOKING_CONFLICT', 'Аудитория уже занята. Обновите варианты.')
                booking = Booking(room_id=choice.roomId, user_id=user.id, date=date.fromisoformat(slot['date']), start_time=slot['startTime'], end_time=slot['endTime'], comment=data['title'], requirements=data['equipment'], team_id=data.get('teamId'))
                session.add(booking)
                session.flush()
            else:
                fail(409, 'PLAN_CLOSED', 'Предложение истекло или план уже завершён.')
            check(session,booking)
            data.update(state='confirmed', bookingId=booking.id)
            plan.data = data
            audit(session, user, 'plan.confirm', plan.id)
            from .notifications import enqueue
            recipients = session.get(Plan, data['teamId']).data['members'] if data.get('teamId') else {str(user.id): 'owner'}
            for uid in recipients:
                enqueue(session, int(uid), 'meeting', 'Встреча подтверждена: '+data['title'], f'{booking.date} {booking.start_time}–{booking.end_time}. Откройте CampusFlow для подробностей.', 'confirm:'+str(plan.id)+':'+uid)
            session.commit()
            return booking_json(session, booking)

    @app.get('/api/meetings/{token}', tags=['Planning'])
    def shared(token: str):
        with sessions() as session:
            return result(session, public(session, token), False)

    @app.post('/api/meetings/{token}/votes', tags=['Planning'])
    def vote(token: str, data: Vote, request: Request):
        consume(sessions, secret, 'meeting-vote:'+token+':'+(request.client.host if request.client else 'unknown'), 30, seconds=60)
        with sessions() as session:
            serialize_writes(session)
            plan = public(session, token)
            value = dict(plan.data)
            if value['state'] != 'open':
                fail(409, 'PLAN_CLOSED', 'Голосование завершено.')
            if any(i < 0 or i >= len(value['slots']) for i in data.choices):
                fail(422, 'INVALID_SLOT', 'Нет такого интервала.')
            votes = dict(value.get('votes', {}))
            key = data.voterToken if data.voterToken in votes else secrets.token_urlsafe(32)
            if len(votes) >= 100 and key not in votes:
                fail(409, 'VOTE_LIMIT', 'Достигнут лимит участников.')
            votes[key] = {'name': data.name, 'choices': sorted(set(data.choices))}
            value['votes'] = votes
            plan.data = value
            session.commit()
            return {'voterToken': key}

    @app.get('/api/bookings/{booking_id}/alternatives', tags=['Planning'])
    def alternatives(booking_id: int, user=Depends(student)):
        with sessions() as session:
            booking = session.get(Booking, booking_id)
            if not booking or booking.user_id != user.id:
                fail(404, 'BOOKING_NOT_FOUND', 'Бронь не найдена.')
            if booking.status != 'cancelled':
                fail(409, 'BOOKING_ACTIVE', 'Замена доступна после отмены исходной брони.')
            room = session.get(Room, booking.room_id)
            slot = {'date': booking.date.isoformat(), 'startTime': booking.start_time, 'endTime': booking.end_time}
            data = {'capacity': room.capacity, 'equipment': room.equipment, 'building': ''}
            options = candidates(session, data, slot)
            options.sort(key=lambda r: (r.building != room.building, abs(r.floor-room.floor), r.capacity))
            return [room_json(r) for r in options if r.id != room.id][:3]

    @app.post('/api/bookings/{booking_id}/replace', status_code=201, tags=['Planning'])
    def replace_booking(booking_id: int, choice: Choice, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            refresh_queue(session)
            original = session.get(Booking, booking_id)
            if not original or original.user_id != user.id:
                fail(404, 'BOOKING_NOT_FOUND', 'Бронь не найдена.')
            if original.status != 'cancelled':
                fail(409, 'BOOKING_ACTIVE', 'Сначала отмените исходную бронь.')
            previous = session.scalar(select(Plan).where(Plan.kind == 'repair', Plan.token == 'repair-'+str(booking_id)))
            if previous:
                fail(409, 'ALREADY_REPLACED', 'Замена уже создана. Откройте мои бронирования.')
            slot = {'date': original.date.isoformat(), 'startTime': original.start_time, 'endTime': original.end_time}
            if slot['date']+'T'+slot['startTime'] <= campus_now().isoformat()[:16]:
                fail(422, 'PAST_BOOKING', 'Время уже прошло.')
            room = session.get(Room, original.room_id)
            available = candidates(session, {'capacity': room.capacity, 'equipment': room.equipment, 'building': ''}, slot)
            if choice.roomId == room.id or choice.roomId not in [r.id for r in available]:
                fail(409, 'BOOKING_CONFLICT', 'Подходящая аудитория уже недоступна.')
            booking = Booking(room_id=choice.roomId, user_id=user.id, date=original.date, start_time=original.start_time, end_time=original.end_time, comment=original.comment, requirements=original.requirements, team_id=original.team_id)
            session.add(booking)
            session.flush()
            session.add(Plan(user_id=user.id, kind='repair', token='repair-'+str(booking_id), data={'originalId': booking_id, 'bookingId': booking.id, 'state': 'confirmed'}))
            audit(session, user, 'booking.replace', booking.id)
            session.commit()
            return booking_json(session, booking)
