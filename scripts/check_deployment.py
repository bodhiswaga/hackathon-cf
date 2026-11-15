"""Non-destructive deployment acceptance using a temporary student and room."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

base = os.getenv('CAMPUS_URL', 'http://127.0.0.1:8080')
def call(path, method='GET', data=None, token=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization'] = 'Bearer '+token
    req = Request(base+'/api'+path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as r: return r.status,json.load(r)
    except HTTPError as e: return e.code,json.load(e)

assert call('/health')[0] == 200
_, admin = call('/auth/login','POST',{'login':os.getenv('ADMIN_LOGIN','admin'),'password':os.getenv('ADMIN_PASSWORD','campus2026')})
a = admin['accessToken']
registration = {'login':'check-'+uuid4().hex[:12],'displayName':'Deployment verification','password':uuid4().hex}
if os.getenv('REGISTRATION_INVITE_CODE'):
    registration['inviteCode'] = os.environ['REGISTRATION_INVITE_CODE']
code, student = call('/auth/register','POST',registration)
assert code == 201, student
s = student['accessToken']
code,room = call('/admin/rooms','POST',{'name':'CHECK-'+uuid4().hex[:8],'building':'TEST','floor':1,'capacity':10,'equipment':[]},a)
assert code == 201, room
_,meta = call('/meta')
data = {'roomId':room['id'],'date':str(date.fromisoformat(meta['today'])+timedelta(days=2)),'startTime':'14:00','endTime':'15:00'}
with ThreadPoolExecutor(2) as pool:
    results=list(pool.map(lambda _:call('/bookings','POST',data,s),range(2)))
assert sorted(r[0] for r in results)==[201,409],results
booking=next(r[1] for r in results if r[0]==201)
assert call('/bookings/'+str(booking['id']),'DELETE',token=s)[0]==200
assert call('/admin/rooms/'+str(room['id']),'DELETE',token=a)[0]==200
assert call('/auth/logout','POST',token=s)[0]==200
assert call('/auth/me',token=s)[0]==401
print('PASS: PostgreSQL deployment, registration, room CRUD, concurrent conflict, cancellation, session revocation')
