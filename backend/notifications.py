"""Verified email preferences and a durable HTTPS mail outbox."""
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.request
from datetime import timedelta

from fastapi import Depends, Header, Query
from pydantic import Field
from sqlalchemy import select

from .models import Plan, Booking, Room
from .schemas import Input
from .mail_transport import configured, provider, send, DeliveryError


def profile(session, uid):
    return session.scalar(select(Plan).where(Plan.kind == 'email', Plan.user_id == uid))


def recipients(session, booking):
    ids = {booking.id}
    repairs = list(session.scalars(select(Plan).where(Plan.kind == 'repair')))
    for _ in range(len(repairs)):
        before = len(ids)
        ids.update(p.data['originalId'] for p in repairs if p.data['bookingId'] in ids)
        if len(ids) == before:
            break
    users = {booking.user_id}
    for plan in session.scalars(select(Plan).where(Plan.kind.in_(['series', 'meeting']))):
        related = set(plan.data.get('bookingIds', [plan.data.get('bookingId')]))
        if related & ids and plan.data.get('teamId'):
            users.update(map(int, session.get(Plan, plan.data['teamId']).data['members']))
    return users


def enqueue(session, uid, category, subject, body, key, address=None):
    from .seed import campus_now
    p = profile(session, uid)
    if not address and (not p or not p.data.get('verified') or not p.data.get('preferences', {}).get(category, True)):
        return
    token = hashlib.sha256(('mail:'+key).encode()).hexdigest()
    if session.scalar(select(Plan.id).where(Plan.token == token)):
        return
    session.add(Plan(user_id=uid, kind='outbox', token=token, data={'to': address or p.data['email'], 'subject': subject, 'body': body, 'state': 'pending', 'attempts': 0, 'category': category, 'key': key, 'createdAt': campus_now().isoformat()}))
    session.flush()


class Preferences(Input):
    email: str = Field(max_length=254)
    meeting: bool = True
    team: bool = True
    queue: bool = True
    reminder: bool = True


class Verification(Input):
    token: str = Field(min_length=20, max_length=100)


def install(app, sessions, current_user, fail, secret):
    from .planning import serialize_writes, refresh_queue
    from .seed import campus_now
    from .limiter import consume

    @app.get('/api/email', tags=['Email'])
    def settings(user=Depends(current_user)):
        with sessions() as session:
            p = profile(session, user.id)
            deliveries = [{'id': m.id, 'subject': m.data['subject'], 'state': m.data['state'], 'error': m.data.get('error', ''), 'nextAttempt': m.data.get('nextAttempt'), 'createdAt':m.data.get('createdAt'), 'sentAt':m.data.get('sentAt')} for m in session.scalars(select(Plan).where(Plan.kind == 'outbox', Plan.user_id == user.id).order_by(Plan.id.desc()).limit(20))]
            return {'provider': provider(), 'deliveries': deliveries, 'configured': configured(), 'email': p.data.get('email', '') if p else '', 'verified': bool(p and p.data.get('verified')), 'preferences': p.data.get('preferences', {}) if p else {}}

    @app.get('/api/email/history', tags=['Email'])
    def history(before: int | None = Query(default=None,gt=0), user=Depends(current_user)):
        with sessions() as session:
            query=select(Plan).where(Plan.kind=='outbox',Plan.user_id==user.id)
            if before:
                query=query.where(Plan.id<before)
            rows=list(session.scalars(query.order_by(Plan.id.desc()).limit(51)))
            return {'items':[{'id':m.id,'subject':m.data['subject'],'state':m.data['state'],'error':m.data.get('error',''),'createdAt':m.data.get('createdAt'),'sentAt':m.data.get('sentAt')} for m in rows[:50]],'hasMore':len(rows)>50}

    @app.put('/api/email', tags=['Email'])
    def save(data: Preferences, user=Depends(current_user)):
        if not re.fullmatch(r'[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+', data.email):
            fail(422, 'INVALID_EMAIL', 'Проверьте email.')
        if not configured():
            fail(503, 'EMAIL_NOT_CONFIGURED', 'Отправка писем ещё не настроена оператором.')
        consume(sessions, secret, 'email:'+str(user.id), 5, 3600)
        with sessions() as session:
            serialize_writes(session)
            p = profile(session, user.id)
            if not p:
                p = Plan(user_id=user.id, kind='email', token=secrets.token_urlsafe(32), data={})
                session.add(p)
            verified = p.data.get('verified', False) and p.data.get('email') == data.email
            token = secrets.token_urlsafe(32)
            p.data = {'email': data.email, 'verified': verified, 'preferences': data.model_dump(exclude={'email'}), 'verificationHash': hashlib.sha256(token.encode()).hexdigest(), 'expires': (campus_now()+timedelta(hours=1)).isoformat()}
            session.flush()
            if not verified:
                enqueue(session, user.id, 'verification', 'Подтвердите email CampusFlow', os.environ['PUBLIC_URL'].rstrip('/')+'/#verify-email='+token, 'verify:'+token, data.email)
            session.commit()
            return {'saved': True, 'verificationRequired': not verified}

    @app.post('/api/email/verify', tags=['Email'])
    def verify(data: Verification):
        with sessions() as session:
            serialize_writes(session)
            digest = hashlib.sha256(data.token.encode()).hexdigest()
            p = next((p for p in session.scalars(select(Plan).where(Plan.kind == 'email')) if p.data.get('verificationHash') == digest), None)
            if not p or p.data['expires'] <= campus_now().isoformat():
                fail(400, 'INVALID_VERIFICATION', 'Ссылка истекла или уже использована.')
            p.data = {**p.data, 'verified': True, 'verificationHash': ''}
            session.commit()
            return {'verified': True}

    @app.post('/api/jobs/notifications', tags=['Operations'])
    def run(authorization: str = Header(default='')):
        expected = os.getenv('NOTIFICATIONS_JOB_SECRET', '')
        if len(expected) < 32 or not hmac.compare_digest(authorization, 'Bearer '+expected):
            fail(401, 'UNAUTHORIZED', 'Недействительный ключ задания.')
        if not configured():
            fail(503, 'EMAIL_NOT_CONFIGURED', 'Почтовый сервис не настроен.')
        with sessions() as session:
            serialize_writes(session)
            refresh_queue(session)
            now = campus_now()
            for p in session.scalars(select(Plan).where(Plan.kind == 'queue')):
                if p.data.get('state') == 'offered':
                    enqueue(session, p.user_id, 'queue', 'Доступна аудитория: подтвердите бронь', 'Предложение действительно до '+p.data['expiresAt']+'. '+os.environ['PUBLIC_URL']+' — раздел «Встречи и очередь».', 'queue:'+str(p.id))
            for b in session.scalars(select(Booking).where(Booking.status == 'active', Booking.date >= now.date(), Booking.date <= (now+timedelta(hours=1)).date())):
                if any(p.data.get('state') == 'offered' and p.data.get('bookingId') == b.id for p in session.scalars(select(Plan).where(Plan.kind == 'queue'))):
                    continue
                start = now.replace(year=b.date.year, month=b.date.month, day=b.date.day, hour=int(b.start_time[:2]), minute=int(b.start_time[3:]), second=0, microsecond=0)
                if now < start <= now+timedelta(hours=1):
                    room = session.get(Room, b.room_id)
                    for uid in recipients(session, b):
                        enqueue(session, uid, 'reminder', 'Встреча начнётся в течение часа', f'{b.date}, {b.start_time}, {room.building}-{room.name}. '+os.environ['PUBLIC_URL'], 'reminder:'+str(b.id)+':'+str(uid))
            pending = [p.id for p in session.scalars(select(Plan).where(Plan.kind == 'outbox').order_by(Plan.id)) if (p.data['state'] == 'pending' and p.data.get('nextAttempt', '') <= now.isoformat()) or (p.data['state'] == 'processing' and p.data.get('lease', '') < now.isoformat())][:10]
            session.commit()
        sent = 0
        for item_id in pending:
            with sessions() as session:
                serialize_writes(session)
                item = session.get(Plan, item_id)
                if item.data['state'] not in ('pending', 'processing') or (item.data['state'] == 'processing' and item.data.get('lease', '') >= campus_now().isoformat()):
                    continue
                d = dict(item.data)
                p = profile(session, item.user_id)
                stale = d.get('createdAt', campus_now().isoformat()) < (campus_now()-timedelta(hours=46 if provider() == 'google-apps-script' else 23)).isoformat()
                if d['category'] == 'verification':
                    verification_hash = hashlib.sha256(d['body'].split('=')[-1].encode()).hexdigest()
                    stale = stale or not p or p.data.get('verificationHash') != verification_hash or p.data.get('expires', '') <= campus_now().isoformat()
                if d['category'] == 'queue':
                    plan = session.get(Plan, int(d['key'].split(':')[1]))
                    stale = stale or not plan or plan.data.get('state') != 'offered' or plan.data['expiresAt'] <= campus_now().isoformat()
                if d['category'] == 'reminder':
                    booking = session.get(Booking, int(d['key'].split(':')[1]))
                    stale = stale or not booking or booking.status != 'active' or booking.date.isoformat()+'T'+booking.start_time <= campus_now().isoformat()[:16]
                if stale:
                    item.data = {**d, 'state': 'skipped'}
                    session.commit()
                    continue
                if d['category'] != 'verification' and (not p or not p.data.get('verified') or p.data['email'] != d['to'] or not p.data['preferences'].get(d['category'], True)):
                    item.data = {**d, 'state': 'skipped'}
                    session.commit()
                    continue
                item.data = {**d, 'state': 'processing', 'lease': (campus_now()+timedelta(minutes=5)).isoformat()}
                token = item.token
                session.commit()
            try:
                send(d, token)
                d['state'] = 'sent'
                d['sentAt'] = campus_now().isoformat()
                d.pop('error', None)
                d.pop('nextAttempt', None)
                sent += 1
            except DeliveryError as exc:
                d['error'] = exc.code
                if exc.code != 'QUOTA_EXCEEDED':
                    d['attempts'] += 1
                d['state'] = 'failed' if exc.permanent or d['attempts'] >= 5 else 'pending'
                delay = max(exc.retry_after, min(3600, 60 * 2**min(d['attempts'], 6)))
                d['nextAttempt'] = (campus_now()+timedelta(seconds=delay)).isoformat()
            with sessions() as session:
                item = session.get(Plan, item_id)
                item.data = d
                session.commit()
        return {'sent': sent, 'processed': len(pending)}
