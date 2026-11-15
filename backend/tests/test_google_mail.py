import hashlib
import hmac
import json
import subprocess
import shutil
from pathlib import Path

import pytest

from backend import mail_transport
from backend.models import Plan
from backend.tests.test_acceptance import client, auth


@pytest.fixture
def google(monkeypatch):
    for key, value in {'MAIL_PROVIDER':'google-apps-script', 'PUBLIC_URL':'https://campus.example', 'GOOGLE_MAIL_URL':'https://script.google.com/macros/s/example-deployment/exec', 'GOOGLE_MAIL_SECRET':'s'*40, 'NOTIFICATIONS_JOB_SECRET':'j'*40}.items():
        monkeypatch.setenv(key, value)


def test_signed_envelope_and_configuration(google, monkeypatch):
    assert mail_transport.configured()
    message = {'to':'test@example.com','subject':'Встреча','body':'Екатеринбург'}
    e = mail_transport.google_envelope(message, 'a'*64, timestamp=12345)
    assert e['signature'] == hmac.new(('s'*40).encode(), ('12345\n'+e['payload']).encode(), hashlib.sha256).hexdigest()
    assert json.loads(e['payload'])['text'] == 'Екатеринбург'
    for url in ['http://script.google.com/macros/s/abc/exec','https://evil.example/exec','https://script.google.com.evil.example/macros/s/abc/exec','https://script.google.com/macros/s/abc/dev']:
        monkeypatch.setenv('GOOGLE_MAIL_URL',url)
        assert not mail_transport.configured()


def test_relay_errors_and_receipts(google, monkeypatch):
    class Response:
        result = {'ok':True,'id':json.loads(mail_transport.google_envelope({'to':'test@example.com','subject':'Тест','body':'Текст'}, 'a'*64)['payload'])['id']}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps(self.result).encode()
    class Opener:
        def open(self, request, timeout):
            assert json.loads(request.data)['signature']
            return Response()
    monkeypatch.setattr(mail_transport.urllib.request,'build_opener',lambda *args:Opener())
    message = {'to':'test@example.com','subject':'Тест','body':'Текст'}
    mail_transport.send(message,'a'*64)
    Response.result = {'ok':False,'code':'QUOTA_EXCEEDED'}
    with pytest.raises(mail_transport.DeliveryError) as exc:
        mail_transport.send(message,'a'*64)
    assert not exc.value.permanent and exc.value.retry_after == 3600
    Response.result = {'ok':False,'code':'DELIVERY_UNCERTAIN'}
    with pytest.raises(mail_transport.DeliveryError) as exc:
        mail_transport.send(message,'a'*64)
    assert exc.value.permanent


def test_quota_keeps_message_without_exhausting_retries(client, google, monkeypatch):
    from backend.notifications import DeliveryError
    h = auth(client)
    assert client.put('/api/email',headers=h,json={'email':'test@example.com'}).status_code == 200
    def quota(*args):raise DeliveryError('QUOTA_EXCEEDED',retry_after=3600)
    monkeypatch.setattr('backend.notifications.send',quota)
    headers={'Authorization':'Bearer '+'j'*40}
    assert client.post('/api/jobs/notifications',headers=headers).json()['sent'] == 0
    status=client.get('/api/email',headers=h).json()['deliveries'][0]
    assert status['state']=='pending' and status['error']=='QUOTA_EXCEEDED'
    with client.app.state.sessions() as s:
        d=s.query(Plan).filter_by(kind='outbox').one().data
        assert d['attempts']==0 and d['nextAttempt']
    # The next immediate cron tick must not retry early.
    assert client.post('/api/jobs/notifications',headers=headers).json()['processed']==0


def test_google_redirects_do_not_leak_payload():
    handler=mail_transport.GoogleRedirects()
    request=mail_transport.urllib.request.Request('https://script.google.com/macros/s/abc/exec',data=b'signed-private-body')
    with pytest.raises(mail_transport.DeliveryError):
        handler.redirect_request(request,None,302,'',{},'https://evil.example/')
    redirected=handler.redirect_request(request,None,302,'',{},'https://script.googleusercontent.com/macros/echo?test=1')
    assert redirected.get_method()=='GET' and redirected.data is None


def test_actual_apps_script_protocol():
    if not shutil.which('node'):
        pytest.skip('Apps Script protocol test requires Node; run on the host or in frontend CI')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node',str(root/'scripts/google-mail/test-relay.cjs')],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
