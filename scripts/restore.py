"""Restore only into an empty, separately provisioned database."""
import argparse
import os
from pathlib import Path
import subprocess
from backup import pg_env

parser=argparse.ArgumentParser()
parser.add_argument('backup',type=Path)
args=parser.parse_args()
env=pg_env(os.environ['RESTORE_DATABASE_URL'])
if os.environ.get('DATABASE_URL')==os.environ['RESTORE_DATABASE_URL']:
    raise SystemExit('Restore target must be separate from source DATABASE_URL')
count=subprocess.check_output(['psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-c',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],env=env,text=True).strip()
if count!='0': raise SystemExit('Restore target must have an empty public schema')
subprocess.run(['pg_restore','--exit-on-error','--single-transaction','--no-owner','--no-acl','--dbname',env['PGDATABASE'],str(args.backup)],env=env,check=True)
print('Restore completed into empty target:',env['PGDATABASE'])
