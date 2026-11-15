"""HTTPS email transports. No mailbox password is stored by CampusFlow."""
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request


class DeliveryError(Exception):
    def __init__(self, code='PROVIDER_ERROR', retry_after=60, permanent=False):
        super().__init__(code)
        self.code, self.retry_after, self.permanent = code, retry_after, permanent


def provider():
    return os.getenv('MAIL_PROVIDER', 'resend')


def google_url_valid(url):
    return bool(re.fullmatch(r'https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec', url))


def configured():
    if not os.getenv('PUBLIC_URL'):
        return False
    if provider() == 'google-apps-script':
        return google_url_valid(os.getenv('GOOGLE_MAIL_URL', '')) and len(os.getenv('GOOGLE_MAIL_SECRET', '')) >= 32
    return provider() == 'resend' and bool(os.getenv('RESEND_API_KEY') and os.getenv('MAIL_FROM'))


class GoogleRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Apps Script ContentService returns results through a one-time GET URL.
        if not re.match(r'^https://script\.googleusercontent\.com/', newurl):
            raise DeliveryError('INVALID_GOOGLE_REDIRECT', permanent=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def google_envelope(message, key, timestamp=None):
    # Demo and production share one mailbox but must not share delivery identities.
    delivery_id = hashlib.sha256((os.environ['PUBLIC_URL'].rstrip('/')+'\n'+key).encode()).hexdigest()
    payload = json.dumps({'id': delivery_id, 'to': message['to'], 'subject': message['subject'], 'text': message['body']}, ensure_ascii=False, separators=(',', ':'))
    stamp = int(time.time()) if timestamp is None else timestamp
    signature = hmac.new(os.environ['GOOGLE_MAIL_SECRET'].encode(), (str(stamp)+'\n'+payload).encode(), hashlib.sha256).hexdigest()
    return {'timestamp': stamp, 'payload': payload, 'signature': signature}


def send(message, key):
    try:
        if provider() == 'google-apps-script':
            url = os.getenv('GOOGLE_MAIL_URL', '')
            if not google_url_valid(url):
                raise DeliveryError('INVALID_GOOGLE_URL', permanent=True)
            envelope = google_envelope(message, key)
            delivery_id = json.loads(envelope['payload'])['id']
            request = urllib.request.Request(url, data=json.dumps(envelope).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.build_opener(GoogleRedirects()).open(request, timeout=15) as response:
                result = json.load(response)
            if result.get('ok') and result.get('id') == delivery_id:
                return
            code = result.get('code', 'INVALID_GOOGLE_RESPONSE')
            raise DeliveryError(code, retry_after=3600 if code == 'QUOTA_EXCEEDED' else 60,
                                permanent=code in ('AUTH_FAILED', 'INVALID_MESSAGE', 'UNCONFIGURED', 'DELIVERY_UNCERTAIN', 'ID_CONFLICT'))
        request = urllib.request.Request('https://api.resend.com/emails', data=json.dumps({'from': os.environ['MAIL_FROM'], 'to': [message['to']], 'subject': message['subject'], 'text': message['body']}).encode(), headers={'Authorization': 'Bearer '+os.environ['RESEND_API_KEY'], 'Content-Type': 'application/json', 'Idempotency-Key': key}, method='POST')
        with urllib.request.urlopen(request, timeout=5) as response:
            if not json.load(response).get('id'):
                raise DeliveryError()
    except DeliveryError:
        raise
    except urllib.error.HTTPError as exc:
        raise DeliveryError('HTTP_'+str(exc.code), permanent=exc.code in (400, 401, 403, 404)) from None
    except Exception:
        # Never propagate provider bodies or signed payloads into application logs.
        raise DeliveryError('NETWORK_OR_RESPONSE_ERROR') from None
