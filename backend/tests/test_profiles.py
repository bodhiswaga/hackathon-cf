import base64
import io
from PIL import Image
from sqlalchemy import select
from backend.models import Plan, User
from backend.tests.test_acceptance import client,auth


def test_names_registration_profile_and_backward_compatibility(client):
    body={'login':'split.names','firstName':'Иван','lastName':'Петров','password':'a-secure-password'}
    r=client.post('/api/auth/register',json=body)
    assert r.status_code==201,r.text
    assert r.json()['user']['displayName']=='Иван Петров'
    h={'Authorization':'Bearer '+r.json()['accessToken']}
    updated=client.patch('/api/auth/profile',headers=h,json={'firstName':'Пётр','lastName':'Иванов'})
    assert updated.json()['displayName']=='Пётр Иванов'
    assert client.patch('/api/auth/profile',headers=h,json={'firstName':'Пётр'}).status_code==422
    assert client.patch('/api/auth/profile',headers=h,json={'firstName':' ','lastName':'Иванов'}).status_code==422
    assert client.patch('/api/auth/profile',headers=h,json={'displayName':'Legacy Name'}).json()['firstName']=='Legacy'
    assert client.get('/api/auth/me',headers=h).json()['lastName']=='Name'


def test_avatar_normalized_persisted_and_owned(client):
    first,second=auth(client),auth(client,'student2')
    output=io.BytesIO();Image.new('RGB',(192,128),'#244c43').save(output,format='PNG')
    image='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
    r=client.put('/api/auth/avatar',headers=first,json={'image':image})
    assert r.status_code==200,r.text
    assert r.json()['avatar'].startswith('data:image/jpeg;base64,')
    thumbnail=Image.open(io.BytesIO(base64.b64decode(r.json()['avatar'].split(',')[1])))
    assert thumbnail.size==(96,96)
    assert client.get('/api/auth/me',headers=second).json()['avatar']==''
    assert client.get('/api/auth/me',headers=first).json()['avatar']==r.json()['avatar']
    for invalid in ['data:image/svg+xml;base64,PHN2Zz4=','data:image/png;base64,anVuaw==']:
        assert client.put('/api/auth/avatar',headers=first,json={'image':invalid}).status_code==422
    assert client.put('/api/auth/avatar',json={'image':image}).status_code==401
    assert client.put('/api/auth/avatar',headers=first,json={'image':''}).json()['avatar']==''


def test_mail_history_dates_pagination_and_privacy(client):
    first,second=auth(client),auth(client,'student2')
    with client.app.state.sessions() as session:
        uid=session.scalar(select(User.id).where(User.login=='student1'))
        for i in range(55):
            session.add(Plan(user_id=uid,kind='outbox',token='history-'+str(i),data={'subject':'Письмо '+str(i),'state':'sent','createdAt':'2026-11-16T10:00:00+05:00','sentAt':'2026-11-16T10:01:00+05:00'}))
        session.commit()
    summary=client.get('/api/email',headers=first).json()
    assert summary['deliveries'][0]['sentAt']=='2026-11-16T10:01:00+05:00'
    page=client.get('/api/email/history',headers=first).json()
    assert len(page['items'])==50 and page['hasMore']
    rest=client.get('/api/email/history?before='+str(page['items'][-1]['id']),headers=first).json()
    assert len(rest['items'])==5 and not rest['hasMore']
    assert client.get('/api/email/history',headers=second).json()['items']==[]
    assert client.get('/api/email/history').status_code==401
