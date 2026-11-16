"""Bound actual request bodies, including chunked requests, before JSON parsing."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=16384):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        limit = 65536 if scope.get('path') == '/api/auth/avatar' else self.max_bytes
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            total += len(message.get('body', b''))
            if total > limit:
                return await JSONResponse({'error':{'code':'BODY_TOO_LARGE','message':'Запрос слишком большой.'}}, status_code=413)(scope, receive, send)
            chunks.append(message.get('body', b''))
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type':'http.request', 'body':b''.join(chunks), 'more_body':False}
            return await receive()
        await self.app(scope, replay, send)
