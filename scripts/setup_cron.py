"""Create health check on cron-job.org. API key comes only from environment."""
import json
import os
from urllib.request import Request, urlopen

url = os.environ['CAMPUS_URL'].rstrip('/')
if not url.startswith('https://'):
    raise SystemExit('CAMPUS_URL must be HTTPS')
job = {'job': {'title': 'CampusFlow health', 'enabled': True, 'url': url+'/api/health', 'saveResponses': False, 'requestMethod': 0, 'schedule': {'timezone':'Asia/Yekaterinburg','expiresAt':0,'hours':[-1],'mdays':[-1],'minutes':[0,10,20,30,40,50],'months':[-1],'wdays':[-1]}}}
request = Request('https://api.cron-job.org/jobs', data=json.dumps(job).encode(), method='PUT', headers={'Authorization':'Bearer '+os.environ['CRONJOB_API_KEY'],'Content-Type':'application/json'})
with urlopen(request, timeout=30) as response:
    result = json.load(response)
    print('Created job:', result.get('jobId'))
