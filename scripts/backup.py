"""Create a PostgreSQL custom-format backup without exposing credentials in arguments."""
import argparse
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit, unquote


def pg_env(url):
    parsed = urlsplit(url.replace('postgresql+psycopg://','postgresql://'))
    if parsed.scheme not in ('postgresql','postgres'):
        raise ValueError('PostgreSQL URL required')
    env = os.environ.copy()
    env.update(PGHOST=parsed.hostname or 'localhost', PGPORT=str(parsed.port or 5432), PGDATABASE=unquote(parsed.path.lstrip('/')), PGUSER=unquote(parsed.username or ''), PGPASSWORD=unquote(parsed.password or ''))
    from urllib.parse import parse_qs
    options = parse_qs(parsed.query)
    if 'sslmode' in options: env['PGSSLMODE'] = options['sslmode'][0]
    return env


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an existing backup')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    env=pg_env(os.environ['DATABASE_URL'])
    subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl','--file',str(args.output)],env=env,check=True)
    subprocess.run(['pg_restore','--list',str(args.output)],stdout=subprocess.DEVNULL,check=True)
    print('Backup created and archive verified:', args.output)


if __name__=='__main__': main()
