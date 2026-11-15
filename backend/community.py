"""Teams and recurring meetings stored as typed documents in the plans table."""
import secrets
from datetime import timedelta

from fastapi import Depends
from pydantic import Field
from sqlalchemy import select

from .models import Plan, Booking, User, Room
from .schemas import Input, BookingInput
from .planning import serialize_writes, refresh_queue
from .seed import campus_now
from .notifications import enqueue


class TeamInput(Input):
    name: str = Field(min_length=2, max_length=80)


class Join(Input):
    token: str = Field(min_length=20, max_length=64)


class MemberInput(Input):
    role: str = Field(pattern='^(organizer|member|remove)$')


class SeriesInput(BookingInput):
    weeks: int = Field(default=1, ge=1, le=12)
    teamId: int | None = Field(default=None, gt=0)
    skip: list[int] = Field(default_factory=list, max_length=12)
    overrides: dict[int, int] = Field(default_factory=dict)


class RSVP(Input):
    answer: str = Field(pattern='^(yes|no|maybe)$')


def member(session, team_id, user, fail, organize=False):
    team = session.get(Plan, team_id)
    role = team.data.get('members', {}).get(str(user.id)) if team and team.kind == 'team' else None
    if not role or team.data.get('closed'):
        fail(404, 'TEAM_NOT_FOUND', 'Команда не найдена.')
    if organize and role not in ('owner', 'organizer'):
        fail(403, 'FORBIDDEN', 'Назначать встречи может организатор команды.')
    return team


def install(app, sessions, current_user, fail, validate_interval, booking_json, audit):
    def student(user=Depends(current_user)):
        if user.role != 'student':
            fail(403, 'FORBIDDEN', 'Раздел доступен студентам.')
        return user

    def team_json(session, team, user):
        return {'id': team.id, 'name': team.data['name'], 'inviteToken': team.token if team.data['members'].get(str(user.id)) in ('owner', 'organizer') else '',
                'meetings': [{'title': p.data['title'], 'token': p.token} for p in session.scalars(select(Plan).where(Plan.kind == 'meeting')) if p.data.get('teamId') == team.id and p.data.get('state') != 'closed'],
                'members': [{'id': int(uid), 'name': session.get(User, int(uid)).display_name, 'role': role} for uid, role in team.data['members'].items()]}

    @app.get('/api/teams', tags=['Teams'])
    def teams(user=Depends(student)):
        with sessions() as session:
            return [team_json(session, t, user) for t in session.scalars(select(Plan).where(Plan.kind == 'team')) if str(user.id) in t.data['members'] and not t.data.get('closed')]

    @app.post('/api/teams', status_code=201, tags=['Teams'])
    def create_team(data: TeamInput, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            if len([t for t in session.scalars(select(Plan).where(Plan.kind == 'team', Plan.user_id == user.id)) if not t.data.get('closed')]) >= 10:
                fail(409, 'TEAM_LIMIT', 'Лимит: 10 команд на владельца.')
            team = Plan(user_id=user.id, kind='team', token=secrets.token_urlsafe(32), data={'name': data.name, 'members': {str(user.id): 'owner'}})
            session.add(team)
            session.flush()
            audit(session, user, 'team.create', team.id)
            session.commit()
            return team_json(session, team, user)

    @app.post('/api/teams/join', tags=['Teams'])
    def join(data: Join, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            team = session.scalar(select(Plan).where(Plan.kind == 'team', Plan.token == data.token))
            if not team or team.data.get('closed'):
                fail(404, 'INVITE_INVALID', 'Приглашение недействительно.')
            members = dict(team.data['members'])
            if len(members) >= 100 and str(user.id) not in members:
                fail(409, 'TEAM_FULL', 'В команде уже 100 участников.')
            members.setdefault(str(user.id), 'member')
            team.data = {**team.data, 'members': members}
            enqueue(session, user.id, 'team', 'Вы вступили в команду '+team.data['name'], 'Командные встречи доступны в разделе «Команды».', 'join:'+str(team.id)+':'+str(user.id))
            session.commit()
            return team_json(session, team, user)

    @app.post('/api/teams/{team_id}/invite', tags=['Teams'])
    def rotate(team_id: int, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            team = member(session, team_id, user, fail, True)
            team.token = secrets.token_urlsafe(32)
            session.commit()
            return team_json(session, team, user)

    @app.patch('/api/teams/{team_id}/members/{uid}', tags=['Teams'])
    def change_member(team_id: int, uid: int, data: MemberInput, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            team = member(session, team_id, user, fail)
            members = dict(team.data['members'])
            if members[str(user.id)] != 'owner' and not (uid == user.id and data.role == 'remove'):
                fail(403, 'FORBIDDEN', 'Управление ролями доступно владельцу.')
            if members.get(str(uid)) == 'owner':
                fail(409, 'OWNER_REQUIRED', 'Владелец не может покинуть команду.')
            if str(uid) not in members:
                fail(404, 'MEMBER_NOT_FOUND', 'Участник не найден.')
            if data.role == 'remove':
                members.pop(str(uid))
            else:
                members[str(uid)] = data.role
            team.data = {**team.data, 'members': members}
            session.commit()
            return {'updated': True}

    def preview(session, data, user, exclude=()):
        validate_interval(data.startTime, data.endTime)
        if data.teamId:
            member(session, data.teamId, user, fail, True)
        if any(i < 0 or i >= data.weeks for i in [*data.skip, *data.overrides]):
            fail(422, 'INVALID_OCCURRENCE', 'Неизвестная дата серии.')
        rows = []
        for i in range(data.weeks):
            day = data.date+timedelta(weeks=i)
            if day.isoformat()+'T'+data.startTime <= campus_now().isoformat()[:16]:
                fail(422, 'PAST_BOOKING', 'Начало серии должно быть в будущем.')
            room_id = data.overrides.get(i, data.roomId)
            room = session.get(Room, room_id)
            if not room or not room.active:
                fail(404, 'ROOM_NOT_FOUND', 'Аудитория недоступна.')
            busy = session.scalar(select(Booking.id).where(Booking.room_id == room_id, Booking.date == day, Booking.status == 'active', Booking.start_time < data.endTime, Booking.end_time > data.startTime, Booking.id.not_in(exclude)).limit(1))
            rows.append({'index': i, 'date': day.isoformat(), 'roomId': room_id, 'roomName': room.building+'-'+room.name, 'conflict': bool(busy), 'skipped': i in data.skip})
        return rows

    @app.post('/api/series/preview', tags=['Series'])
    def preview_series(data: SeriesInput, seriesId: int | None = None, user=Depends(student)):
        with sessions() as session:
            old = session.get(Plan, seriesId) if seriesId else None
            if seriesId and (not old or old.kind != 'series' or old.user_id != user.id):
                fail(404, 'SERIES_NOT_FOUND', 'Серия не найдена.')
            return preview(session, data, user, old.data['bookingIds'] if old else ())

    @app.post('/api/series', status_code=201, tags=['Series'])
    @app.put('/api/series/{series_id}', tags=['Series'])
    def create_series(data: SeriesInput, series_id: int | None = None, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            refresh_queue(session)
            old = session.get(Plan, series_id) if series_id else None
            if series_id and (not old or old.kind != 'series' or old.user_id != user.id):
                fail(404, 'SERIES_NOT_FOUND', 'Серия не найдена.')
            rows = preview(session, data, user, old.data['bookingIds'] if old else ())
            selected = [r for r in rows if not r['skipped']]
            if not selected:
                fail(422, 'EMPTY_SERIES', 'Выберите хотя бы одну встречу.')
            if any(r['conflict'] for r in selected):
                fail(409, 'BOOKING_CONFLICT', 'Есть занятые даты. Выберите замену или пропустите их.')
            ids = []
            if old:
                for bid in old.data['bookingIds']:
                    previous = session.get(Booking, bid)
                    if previous.date.isoformat()+'T'+previous.start_time > campus_now().isoformat()[:16]:
                        previous.status = 'cancelled'
                        audit(session, user, 'booking.cancel', previous.id)
                    else:
                        ids.append(bid)
            for row in selected:
                b = Booking(room_id=row['roomId'], user_id=user.id, date=data.date+timedelta(weeks=row['index']), start_time=data.startTime, end_time=data.endTime, comment=data.comment)
                session.add(b)
                session.flush()
                ids.append(b.id)
            series = old or Plan(user_id=user.id, kind='series', token=secrets.token_urlsafe(32), data={})
            series.data = {'teamId': data.teamId, 'bookingIds': ids, 'rsvp': {}, 'input': data.model_dump(mode='json')}
            session.add(series)
            session.flush()
            recipients = member(session, data.teamId, user, fail).data['members'] if data.teamId else {str(user.id): 'owner'}
            for uid in recipients:
                enqueue(session, int(uid), 'meeting', 'Новые встречи: '+(data.comment or 'CampusFlow'), f'{len(ids)} встреч, начало {data.date} в {data.startTime}. Подробности — в CampusFlow.', 'series:'+str(series.id)+':'+str(ids[-1])+':'+uid)
            audit(session, user, 'series.create', series.id)
            session.commit()
            return {'id': series.id, 'bookingIds': ids}

    @app.get('/api/series', tags=['Series'])
    def list_series(user=Depends(student)):
        with sessions() as session:
            result = []
            for s in session.scalars(select(Plan).where(Plan.kind == 'series').order_by(Plan.id.desc())):
                team = session.get(Plan, s.data['teamId']) if s.data.get('teamId') else None
                if s.user_id != user.id and not (team and str(user.id) in team.data['members']):
                    continue
                result.append({'id': s.id, 'ownerId': s.user_id, 'teamId': s.data.get('teamId'), 'bookings': [booking_json(session, session.get(Booking, bid)) for bid in s.data['bookingIds']], 'rsvp': s.data['rsvp']})
            return result

    @app.post('/api/series/{series_id}/rsvp', tags=['Series'])
    def respond(series_id: int, data: RSVP, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            s = session.get(Plan, series_id)
            if not s or s.kind != 'series':
                fail(404, 'SERIES_NOT_FOUND', 'Серия не найдена.')
            if s.data.get('teamId'):
                member(session, s.data['teamId'], user, fail)
            elif s.user_id != user.id:
                fail(403, 'FORBIDDEN', 'Это чужая встреча.')
            s.data = {**s.data, 'rsvp': {**s.data['rsvp'], str(user.id): data.answer}}
            session.commit()
            return {'saved': True}

    @app.delete('/api/series/{series_id}', tags=['Series'])
    def cancel_series(series_id: int, user=Depends(student)):
        with sessions() as session:
            serialize_writes(session)
            s = session.get(Plan, series_id)
            if not s or s.kind != 'series' or s.user_id != user.id:
                fail(404, 'SERIES_NOT_FOUND', 'Серия не найдена.')
            for bid in s.data['bookingIds']:
                b = session.get(Booking, bid)
                if b.date.isoformat()+'T'+b.start_time > campus_now().isoformat()[:16]:
                    b.status = 'cancelled'
                    audit(session, user, 'booking.cancel', b.id)
            session.flush()
            refresh_queue(session)
            session.commit()
            return {'cancelled': True}
