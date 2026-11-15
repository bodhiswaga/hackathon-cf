"""Fixed-window throttling shared by every application worker via the database."""
import hashlib
import hmac
import time
from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .models import RateBucket


def consume(sessions, secret, key, limit, seconds=900):
    now = int(time.time())
    window = now // seconds * seconds
    digest = hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()
    with sessions() as session:
        insert = sqlite_insert if session.bind.dialect.name == 'sqlite' else pg_insert
        statement = insert(RateBucket).values(key=digest, window=window, count=1)
        statement = statement.on_conflict_do_update(index_elements=['key'], set_={'window': window, 'count': case((RateBucket.window == window, RateBucket.count + 1), else_=1)}).returning(RateBucket.count)
        count = session.scalar(statement)
        session.commit()
    if count > limit:
        raise HTTPException(429, detail={'code':'RATE_LIMITED','message':'Слишком много попыток. Попробуйте позже.'}, headers={'Retry-After':str(window+seconds-now)})
