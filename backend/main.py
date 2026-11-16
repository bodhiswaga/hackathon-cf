import asyncio
from contextlib import suppress
from .attendance import process as process_attendance, attendance_json
import csv
import io
import os
import re
import secrets
import hmac
import logging
import time
from contextlib import asynccontextmanager
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from .database import make_engine, session_factory
from .models import AuditEvent, AuthSession, Booking, Room, User, Plan
from .schemas import BookingInput, EQUIPMENT, Login, Register, RoomInput, ProfileInput, PasswordInput
from .security import hash_password, verify_password
from .seed import TIMEZONE, campus_now, seed
from .migrate import upgrade, verify
from .limiter import consume
from .http_limits import BodyLimitMiddleware
from .controls import install as install_controls, closure_slots, blocked, restrictions
from .community import install as install_community
from .notifications import install as install_notifications, enqueue, recipients
from .planning import install as install_planning, serialize_writes, refresh_queue
from starlette.middleware.trustedhost import TrustedHostMiddleware

OPEN, CLOSE = '08:00', '22:00'
logger = logging.getLogger('uvicorn.error')
DUMMY_HASH = hash_password('constant-time-invalid-account-password')


def fail(status, code, message):
    raise HTTPException(status, detail={'code': code, 'message': message})


def user_json(user):
    return {'id': user.id, 'login': user.login, 'role': user.role, 'displayName': user.display_name, 'firstName': user.first_name or user.display_name.partition(' ')[0], 'lastName': user.last_name or user.display_name.partition(' ')[2], 'avatar':user.avatar}


def room_json(room):
    return {'id': room.id, 'name': room.name, 'building': room.building, 'floor': room.floor, 'capacity': room.capacity, 'equipment': room.equipment, 'description': room.description, 'active': room.active}


def minutes(value):
    h, m = map(int, value.split(':'))
    return h * 60 + m


def free_intervals(bookings):
    cursor, result = OPEN, []
    for b in sorted(bookings, key=lambda b: b.start_time):
        if b.start_time > cursor:
            result.append({'startTime': cursor, 'endTime': b.start_time})
        cursor = max(cursor, b.end_time)
    if cursor < CLOSE:
        result.append({'startTime': cursor, 'endTime': CLOSE})
    return result


def create_app(database_url=None, secret=None):
    engine = make_engine(database_url or os.getenv('DATABASE_URL', 'sqlite:///./campusflow.db'))
    sessions = session_factory(engine)
    jwt_secret = secret or os.getenv('JWT_SECRET')
    production = os.getenv('APP_ENV') == 'production'
    demo = os.getenv('SEED_DATA', 'false' if production else 'true').lower() == 'true'
    registration = os.getenv('REGISTRATION_MODE', 'invite' if production else 'open')
    invite_code = os.getenv('REGISTRATION_INVITE_CODE', '')
    if registration not in ('open', 'invite', 'closed'):
        raise RuntimeError('REGISTRATION_MODE must be open, invite or closed')
    if registration == 'invite' and len(invite_code) < 16:
        raise RuntimeError('Invite registration requires REGISTRATION_INVITE_CODE of at least 16 characters')
    if production and demo:
        raise RuntimeError('Demo seed is prohibited in production')
    if production and (not jwt_secret or len(jwt_secret) < 32 or jwt_secret.startswith(('replace-', 'local-'))):
        raise RuntimeError('Production requires a random JWT_SECRET of at least 32 characters')
    if production and engine.dialect.name != 'postgresql':
        raise RuntimeError('Production requires PostgreSQL')
    if not jwt_secret:
        if os.getenv('RENDER'):
            raise RuntimeError('JWT_SECRET must be configured on Render')
        jwt_secret = secrets.token_hex(32)

    @asynccontextmanager
    async def lifespan(app):
        if production:
            verify(engine)
        else:
            upgrade(engine)
        if demo:
            with sessions() as session:
                seed(session)
        async def attendance_loop():
            first=True
            while True:
                try:
                    def tick():
                        with sessions() as session:
                            serialize_writes(session)
                            seen=getattr(app.state,'attendance_reachable',None)
                            reachable=bool(seen and 0<=(campus_now()-seen).total_seconds()<=90)
                            process_attendance(session,failure=getattr(app.state,'attendance_failure',None),startup=first,reachable=reachable)
                            session.commit()
                    await asyncio.to_thread(tick)
                    first=False
                except Exception:
                    app.state.attendance_failure=campus_now()
                    logger.error('attendance_job_failed; automatic cancellation protected')
                await asyncio.sleep(30)
        task=asyncio.create_task(attendance_loop())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            engine.dispose()

    app = FastAPI(title='CampusFlow API', version='1.1.0', description='Бронирование аудиторий. Время кампуса: Asia/Yekaterinburg. Вход: /api/auth/login; вставьте accessToken в Authorize.', lifespan=lifespan, docs_url=None if production else '/docs', redoc_url=None if production else '/redoc', openapi_url=None if production else '/openapi.json')
    app.state.engine = engine
    app.state.sessions = sessions
    app.add_middleware(BodyLimitMiddleware)
    if production:
        hosts = [v.strip() for v in os.getenv('ALLOWED_HOSTS', '').split(',') if v.strip()]
        if not hosts or '*' in hosts:
            raise RuntimeError('Production requires explicit ALLOWED_HOSTS')
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.exception_handler(HTTPException)
    async def http_error(_, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {'code': 'HTTP_ERROR', 'message': str(exc.detail)}
        return JSONResponse({'error': detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return JSONResponse({'error': {'code': 'VALIDATION_ERROR', 'message': 'Проверьте заполнение полей.', 'fields': [{'field': '.'.join(map(str, e['loc'][1:])), 'message': e['msg']} for e in exc.errors()]}}, status_code=422)

    @app.middleware('http')
    async def response_headers(request: Request, call_next):
        request_id = secrets.token_hex(8)
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Never log request bodies, credentials or SQL parameters.
            logger.error('request_failed id=%s method=%s path=%s', request_id, request.method, request.url.path)
            response = JSONResponse({'error': {'code':'INTERNAL_ERROR','message':'Ошибка сервера. Повторите попытку позже.', 'requestId':request_id}}, status_code=500)
        if request.url.path.startswith('/api/') and response.status_code<400:
            app.state.attendance_reachable=campus_now()
        if response.status_code>=500 or (response.status_code>=400 and request.url.path.startswith('/assets/')):
            app.state.attendance_failure=campus_now()
        response.headers['X-Request-ID'] = request_id
        logger.info('request id=%s method=%s path=%s status=%s duration_ms=%s', request_id, request.method, request.url.path, response.status_code, round((time.monotonic()-started)*1000))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def db():
        with sessions() as session:
            yield session

    bearer = HTTPBearer(auto_error=False)

    def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), session=Depends(db)):
        if not credentials:
            fail(401, 'UNAUTHORIZED', 'Войдите в аккаунт, чтобы продолжить.')
        try:
            payload = jwt.decode(credentials.credentials, jwt_secret, algorithms=['HS256'], options={'require': ['exp', 'sub', 'sid']})
            user_id = int(payload['sub'])
        except (jwt.InvalidTokenError, ValueError, KeyError):
            fail(401, 'SESSION_EXPIRED', 'Сессия истекла. Войдите снова.')
        user = session.get(User, user_id)
        auth_session = session.get(AuthSession, payload.get('sid', ''))
        if not user or not auth_session or auth_session.revoked or auth_session.user_id != user_id or not auth_session.expires_at or auth_session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            fail(401, 'UNAUTHORIZED', 'Аккаунт не найден.')
        return user

    def admin(user=Depends(current_user)):
        if user.role != 'admin':
            fail(403, 'FORBIDDEN', 'Этот раздел доступен только администратору.')
        return user

    def token_response(user):
        sid = secrets.token_hex(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=8)
        with sessions() as session:
            # Serialize session issuance with password changes.
            locked_user = session.scalar(select(User).where(User.id == user.id).with_for_update())
            if locked_user.password_hash != user.password_hash:
                fail(401, 'CREDENTIALS_CHANGED', 'Пароль изменён. Войдите снова.')
            session.add(AuthSession(id=sid, user_id=user.id, created_at=now, expires_at=expires))
            session.commit()
        token = jwt.encode({'sub': str(user.id), 'sid': sid, 'iat': now, 'exp': expires}, jwt_secret, algorithm='HS256')
        return {'accessToken': token, 'tokenType': 'bearer', 'expiresIn': 28800, 'user': user_json(user)}

    @app.post('/api/auth/logout', tags=['Auth'])
    def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), user=Depends(current_user), session=Depends(db)):
        payload = jwt.decode(credentials.credentials, jwt_secret, algorithms=['HS256'])
        auth_session = session.get(AuthSession, payload['sid'])
        auth_session.revoked = True
        session.commit()
        return {'loggedOut': True}

    def audit(session, user, action, entity_id=None):
        session.add(AuditEvent(actor_id=user.id, action=action, entity_id=entity_id))
        if action in ('booking.create', 'booking.cancel', 'booking.replace'):
            booking = session.get(Booking, entity_id)
            for uid in recipients(session, booking):
                enqueue(session, uid, 'meeting', 'Изменение брони CampusFlow', f'{booking.date} {booking.start_time}–{booking.end_time}, статус: {booking.status}. Подробности в приложении.', action+':'+str(entity_id)+':'+str(uid))

    @app.post('/api/auth/logout-all', tags=['Auth'])
    def logout_all(user=Depends(current_user)):
        with sessions() as session:
            session.scalar(select(User).where(User.id == user.id).with_for_update())
            session.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
            audit(session, user, 'sessions.revoke_all')
            session.commit()
        return {'loggedOut': True}

    @app.patch('/api/auth/profile', tags=['Auth'])
    def profile(data: ProfileInput, user=Depends(current_user), session=Depends(db)):
        user.display_name = data.displayName
        user.first_name, user.last_name = data.firstName, data.lastName
        audit(session, user, 'profile.update')
        session.commit()
        return user_json(user)

    @app.post('/api/auth/password', tags=['Auth'])
    def password(data: PasswordInput, user=Depends(current_user)):
        consume(sessions, jwt_secret, f'password:{user.id}', 10)
        with sessions() as session:
            if engine.dialect.name == 'sqlite':
                session.execute(text('BEGIN IMMEDIATE'))
            locked = session.scalar(select(User).where(User.id == user.id).with_for_update())
            if not verify_password(data.currentPassword, locked.password_hash):
                fail(400, 'INVALID_PASSWORD', 'Текущий пароль указан неверно.')
            if data.currentPassword == data.newPassword:
                fail(422, 'SAME_PASSWORD', 'Новый пароль должен отличаться от текущего.')
            locked.password_hash = hash_password(data.newPassword)
            session.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
            audit(session, user, 'password.change')
            session.commit()
        return {'passwordChanged': True}

    @app.get('/api/live', tags=['System'])
    def live():
        return {'status': 'alive'}

    @app.get('/api/health', tags=['System'])
    def health(session=Depends(db)):
        session.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.get('/api/meta', tags=['System'])
    def meta(session=Depends(db)):
        buildings = session.scalars(select(Room.building).where(Room.active.is_(True)).distinct().order_by(Room.building)).all()
        return {'timezone': TIMEZONE, 'today': campus_now().date().isoformat(), 'now': campus_now().strftime('%H:%M'), 'opensAt': OPEN, 'closesAt': CLOSE, 'buildings': buildings, 'equipment': EQUIPMENT, 'demo': demo, 'registrationMode': registration}

    @app.post('/api/auth/login', tags=['Auth'])
    def login(data: Login, request: Request, session=Depends(db)):
        consume(sessions, jwt_secret, 'login-ip:'+request.client.host, 60)
        consume(sessions, jwt_secret, 'login-account:'+data.login.strip().lower(), 20)
        user = session.scalar(select(User).where(User.login == data.login.strip().lower()))
        valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
        if not user or not valid:
            fail(401, 'INVALID_CREDENTIALS', 'Неверный логин или пароль.')
        if not user.password_hash.startswith('pbkdf2_sha256$'):
            user.password_hash = hash_password(data.password)
            session.commit()
        return token_response(user)

    @app.post('/api/auth/register', status_code=201, tags=['Auth'])
    def register(data: Register, request: Request, session=Depends(db)):
        consume(sessions, jwt_secret, 'register:'+request.client.host, 10, 3600)
        if registration == 'closed':
            fail(403, 'REGISTRATION_CLOSED', 'Регистрация закрыта. Обратитесь к администратору кампуса.')
        if registration == 'invite' and not hmac.compare_digest(data.inviteCode, invite_code):
            fail(403, 'INVALID_INVITE', 'Неверный код приглашения.')
        if production and len(data.password) < 12:
            fail(422, 'WEAK_PASSWORD', 'Пароль должен содержать не менее 12 символов.')
        if not data.displayName.strip():
            fail(422, 'INVALID_NAME', 'Укажите имя.')
        user = User(login=data.login.lower(), display_name=data.displayName, first_name=data.firstName, last_name=data.lastName, password_hash=hash_password(data.password), role='student')
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            fail(409, 'LOGIN_TAKEN', 'Этот логин уже занят. Выберите другой.')
        return token_response(user)

    @app.get('/api/auth/me', tags=['Auth'])
    def me(user=Depends(current_user)):
        return user_json(user)

    def get_room(session, room_id, active=True):
        room = session.get(Room, room_id)
        if not room or (active and not room.active):
            fail(404, 'ROOM_NOT_FOUND', 'Аудитория не найдена или больше недоступна.')
        return room

    def day_bookings(session, date, room_id=None):
        query = select(Booking).where(Booking.date == date, Booking.status == 'active')
        if room_id is not None:
            query = query.where(Booking.room_id == room_id)
        return session.scalars(query.order_by(Booking.start_time)).all()

    def refresh_plans():
        with sessions() as write_session:
            serialize_writes(write_session)
            refresh_queue(write_session)
            write_session.commit()

    def validate_interval(start, end):
        pattern = r'^([01]\d|2[0-3]):[0-5]\d$'
        if not re.fullmatch(pattern, start) or not re.fullmatch(pattern, end) or not OPEN <= start < end <= CLOSE:
            fail(422, 'INVALID_INTERVAL', 'Укажите начало раньше окончания, в пределах 08:00–22:00.')

    @app.get('/api/rooms', tags=['Rooms'])
    def rooms(building: str | None = None, minCapacity: int = Query(0, ge=0, le=1000), equipment: str = '', date: Date | None = None, startTime: str | None = None, endTime: str | None = None, session=Depends(db), user=Depends(current_user)):
        refresh_plans()
        required = {v for v in equipment.split(',') if v}
        if required - EQUIPMENT.keys():
            fail(422, 'INVALID_EQUIPMENT', 'Неизвестное оборудование.')
        if startTime or endTime:
            if not (date and startTime and endTime):
                fail(422, 'INCOMPLETE_INTERVAL', 'Для поиска по времени нужны дата, начало и окончание.')
            validate_interval(startTime, endTime)
        query = select(Room).where(Room.active.is_(True), Room.capacity >= minCapacity).order_by(Room.building, Room.name)
        if building:
            query = query.where(Room.building == building)
        busy = day_bookings(session, date) if date else []
        result = []
        for room in session.scalars(query).all():
            if not required.issubset(room.equipment):
                continue
            occupied = [b for b in busy if b.room_id == room.id] + (closure_slots(session,room.id,date) if date else [])
            if date and required:
                from types import SimpleNamespace
                occupied += [SimpleNamespace(start_time=p.data['startTime'],end_time=p.data['endTime']) for p in restrictions(session,room.id,date) if set(p.data['equipment']) & required]
            if startTime and blocked(session,room.id,date,startTime,endTime,required):
                continue
            available = not any(b.start_time < endTime and b.end_time > startTime for b in occupied) if startTime else True
            if startTime and not available:
                continue
            result.append({**room_json(room), 'busySlots': [{'startTime': b.start_time, 'endTime': b.end_time} for b in occupied], 'freeSlots': free_intervals(occupied) if date else []})
        return result

    @app.get('/api/rooms/{room_id}', tags=['Rooms'])
    def room_detail(room_id: int, session=Depends(db), user=Depends(current_user)):
        return room_json(get_room(session, room_id))

    @app.get('/api/rooms/{room_id}/free-slots', tags=['Rooms'])
    def slots(room_id: int, date: Date, session=Depends(db), user=Depends(current_user)):
        refresh_plans()
        get_room(session, room_id)
        busy = day_bookings(session, date, room_id) + closure_slots(session,room_id,date)
        return {'date': date.isoformat(), 'roomId': room_id, 'freeSlots': free_intervals(busy), 'busySlots': [{'startTime': b.start_time, 'endTime': b.end_time} for b in busy]}

    def booking_json(session, booking):
        held = any(p.data.get('state') == 'offered' and p.data.get('bookingId') == booking.id for p in session.scalars(select(Plan).where(Plan.user_id == booking.user_id, Plan.kind == 'queue')))
        return {'id': booking.id, 'warnings':[p.data['reason'] for p in restrictions(session,booking.room_id,booking.date) if p.data['startTime']<booking.end_time and p.data['endTime']>booking.start_time and (not p.data['equipment'] or set(p.data['equipment']) & set(booking.requirements))], 'attendance': attendance_json(session,booking), 'checkedIn': booking.checked_in, 'requirements': booking.requirements, 'held': held, 'roomId': booking.room_id, 'userId': booking.user_id, 'date': booking.date.isoformat(), 'startTime': booking.start_time, 'endTime': booking.end_time, 'status': booking.status, 'comment': booking.comment, 'room': room_json(session.get(Room, booking.room_id)), 'user': user_json(session.get(User, booking.user_id))}

    def lock_room(session, room_id):
        # A separate write session starts before any reads, including authentication.
        serialize_writes(session)
        room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if not room or not room.active:
            fail(404, 'ROOM_NOT_FOUND', 'Аудитория больше недоступна.')
        return room

    @app.post('/api/bookings', status_code=201, tags=['Bookings'])
    def create_booking(data: BookingInput, user=Depends(current_user)):
        if user.role != 'student':
            fail(403, 'FORBIDDEN', 'Бронирование доступно только студентам.')
        validate_interval(data.startTime, data.endTime)
        now = campus_now()
        if data.date < now.date() or (data.date == now.date() and data.startTime <= now.strftime('%H:%M')):
            fail(422, 'PAST_BOOKING', 'Нельзя забронировать время в прошлом.')
        with sessions() as session:
            lock_room(session, data.roomId)
            refresh_queue(session)
            conflict = session.scalar(select(Booking.id).where(Booking.room_id == data.roomId, Booking.date == data.date, Booking.status == 'active', Booking.start_time < data.endTime, Booking.end_time > data.startTime).limit(1))
            if conflict:
                fail(409, 'BOOKING_CONFLICT', 'Этот интервал уже занят. Выберите другое время или аудиторию.')
            booking = Booking(room_id=data.roomId, user_id=user.id, date=data.date, start_time=data.startTime, end_time=data.endTime, comment=data.comment, requirements=data.requirements)
            session.add(booking)
            session.flush()
            audit(session, user, 'booking.create', booking.id)
            session.commit()
            return booking_json(session, booking)

    @app.get('/api/bookings/my', tags=['Bookings'])
    def my_bookings(session=Depends(db), user=Depends(current_user)):
        refresh_plans()
        return [booking_json(session, b) for b in session.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.date.desc(), Booking.start_time)).all()]

    def owned_booking(session, booking_id, user):
        booking = session.get(Booking, booking_id)
        if not booking:
            fail(404, 'BOOKING_NOT_FOUND', 'Бронь не найдена.')
        if booking.user_id != user.id and user.role != 'admin':
            fail(403, 'FORBIDDEN', 'Это бронирование принадлежит другому пользователю.')
        return booking

    @app.get('/api/bookings/{booking_id}', tags=['Bookings'])
    def booking_detail(booking_id: int, session=Depends(db), user=Depends(current_user)):
        return booking_json(session, owned_booking(session, booking_id, user))

    def cancel(booking_id, user):
        with sessions() as session:
            serialize_writes(session)
            booking = owned_booking(session, booking_id, user)
            booking.status = 'cancelled'
            audit(session, user, 'booking.cancel', booking.id)
            session.flush()
            refresh_queue(session)
            session.commit()
            return booking_json(session, booking)

    @app.delete('/api/bookings/{booking_id}', tags=['Bookings'])
    def cancel_own(booking_id: int, user=Depends(current_user)):
        return cancel(booking_id, user)

    @app.get('/api/admin/bookings', tags=['Admin'])
    def all_bookings(date: Date | None = None, building: str | None = None, session=Depends(db), user=Depends(admin)):
        query = select(Booking).join(Room).order_by(Booking.date.desc(), Booking.start_time)
        if date:
            query = query.where(Booking.date == date)
        if building:
            query = query.where(Room.building == building)
        return [booking_json(session, b) for b in session.scalars(query).all()]

    @app.delete('/api/admin/bookings/{booking_id}', tags=['Admin'])
    def cancel_any(booking_id: int, user=Depends(admin)):
        return cancel(booking_id, user)

    def save_room(session, room, user, action):
        session.add(room)
        try:
            session.flush()
            audit(session, user, action, room.id)
            session.commit()
        except IntegrityError:
            session.rollback()
            fail(409, 'ROOM_EXISTS', 'Аудитория с таким номером уже есть в этом корпусе, в том числе в архиве.')
        return room_json(room)

    @app.post('/api/admin/rooms', status_code=201, tags=['Admin'])
    def add_room(data: RoomInput, session=Depends(db), user=Depends(admin)):
        return save_room(session, Room(**data.model_dump()), user, 'room.create')

    @app.put('/api/admin/rooms/{room_id}', tags=['Admin'])
    def edit_room(room_id: int, data: RoomInput, user=Depends(admin)):
        with sessions() as session:
            room = lock_room(session, room_id)
            for key, value in data.model_dump().items():
                setattr(room, key, value)
            return save_room(session, room, user, 'room.update')

    @app.delete('/api/admin/rooms/{room_id}', tags=['Admin'])
    def delete_room(room_id: int, user=Depends(admin)):
        with sessions() as session:
            room = lock_room(session, room_id)
            now = campus_now()
            future = session.scalar(select(Booking.id).where(Booking.room_id == room_id, Booking.status == 'active', (Booking.date > now.date()) | ((Booking.date == now.date()) & (Booking.end_time > now.strftime('%H:%M')))).limit(1))
            if future:
                fail(409, 'ROOM_HAS_BOOKINGS', 'Сначала отмените будущие брони этой аудитории.')
            room.active = False
            audit(session, user, 'room.archive', room.id)
            session.commit()
            return {'id': room_id, 'deleted': True}

    @app.get('/api/admin/stats', tags=['Admin'])
    def stats(date: Date | None = None, session=Depends(db), user=Depends(admin)):
        first = date or campus_now().date()
        rooms = session.scalars(select(Room).where(Room.active.is_(True))).all()
        bookings = session.scalars(select(Booking).where(Booking.status == 'active', Booking.date >= first, Booking.date < first+timedelta(days=7))).all()
        held_ids = {p.data.get('bookingId') for p in session.scalars(select(Plan).where(Plan.kind == 'queue')) if p.data.get('state') == 'offered'}
        held_count = sum(b.id in held_ids for b in bookings)
        bookings = [b for b in bookings if b.id not in held_ids]
        rows = []
        hourly = []
        for offset in range(7):
            day = first+timedelta(days=offset)
            for building in sorted({r.building for r in rooms}):
                room_ids = {r.id for r in rooms if r.building == building}
                matches = [b for b in bookings if b.date == day and b.room_id in room_ids]
                for hour in range(8,22):
                    booked = sum(max(0,min(minutes(b.end_time),(hour+1)*60)-max(minutes(b.start_time),hour*60)) for b in matches)
                    hourly.append({'date':day.isoformat(),'building':building,'hour':f'{hour:02}:00','occupancy':round(booked/(len(room_ids)*60)*100,1) if room_ids else 0})
                occupied = sum(minutes(b.end_time)-minutes(b.start_time) for b in matches)
                total = len(room_ids)*(minutes(CLOSE)-minutes(OPEN))
                rows.append({'date': day.isoformat(), 'building': building, 'bookings': len(matches), 'occupiedMinutes': occupied, 'availableMinutes': total, 'occupancy': round(occupied/total*100, 1) if total else 0})
        room_rows = [{'id':r.id,'name':r.building+'-'+r.name,'hours':round(sum(minutes(b.end_time)-minutes(b.start_time) for b in bookings if b.room_id==r.id)/60,1)} for r in rooms]
        attendance = {'checkedIn':sum(b.checked_in for b in bookings), 'unconfirmedPast':sum(not b.checked_in and b.date.isoformat()+'T'+b.end_time < campus_now().isoformat()[:16] for b in bookings)}
        return {'rooms':room_rows,'attendance':attendance,'rows': rows, 'hourly':hourly, 'heldCount':held_count, 'roomCount': len(rooms), 'bookingCount': len(bookings), 'occupiedHours': round(sum(minutes(b.end_time)-minutes(b.start_time) for b in bookings)/60, 1)}

    @app.get('/api/admin/audit', tags=['Admin'])
    def audit_history(limit: int = Query(50, ge=1, le=200), before: int | None = None, session=Depends(db), user=Depends(admin)):
        query = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
        if before is not None:
            query = query.where(AuditEvent.id < before)
        return [{'id':e.id,'actorId':e.actor_id,'action':e.action,'entityId':e.entity_id,'createdAt':e.created_at.isoformat()} for e in session.scalars(query)]

    @app.get('/api/admin/bookings.csv', tags=['Admin'])
    def export_csv(session=Depends(db), user=Depends(admin)):
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['ID', 'Дата', 'Начало', 'Окончание', 'Корпус', 'Аудитория', 'Пользователь', 'Статус', 'Комментарий'])
        def safe(value):
            value = str(value)
            return "'"+value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value
        for b in session.scalars(select(Booking).order_by(Booking.date, Booking.start_time)):
            room, owner = session.get(Room, b.room_id), session.get(User, b.user_id)
            writer.writerow([safe(v) for v in [b.id, b.date, b.start_time, b.end_time, room.building, room.name, owner.display_name, b.status, b.comment]])
        return Response('\ufeff'+stream.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="campusflow-bookings.csv"'})

    from .avatars import install as install_avatars
    install_avatars(app,current_user,db,user_json,audit)
    install_controls(app,sessions,current_user,admin,fail,validate_interval,audit,booking_json,room_json,free_intervals)
    install_planning(app, sessions, current_user, fail, validate_interval, room_json, booking_json, audit, jwt_secret)

    install_community(app, sessions, current_user, fail, validate_interval, booking_json, audit)
    install_notifications(app, sessions, current_user, fail, jwt_secret)

    frontend = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
    if frontend.exists():
        app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')
        @app.get('/{path:path}', include_in_schema=False)
        def spa(path: str):
            if path == 'theme.js':
                return FileResponse(frontend / 'theme.js')
            if path == 'favicon.svg':
                return FileResponse(frontend / 'favicon.svg', media_type='image/svg+xml')
            if path.startswith(('api/', 'assets/')) or path in ('docs', 'redoc', 'openapi.json'):
                fail(404, 'NOT_FOUND', 'Страница не найдена.')
            return FileResponse(frontend / 'index.html')
    return app


app = create_app()
