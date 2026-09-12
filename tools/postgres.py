"""Control only this prototype's isolated PostgreSQL cluster."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]/'.runtime'
env=dict(os.environ, LD_LIBRARY_PATH=str(ROOT/'postgres/usr/lib64'))
pg=ROOT/'postgres/usr/bin/pg_ctl'
command=sys.argv[1] if len(sys.argv)>1 else 'start'
if command not in ('start','status','stop'):raise SystemExit('start | status | stop')
if command=='start' and subprocess.run([str(pg),'-D',str(ROOT/'pgdata'),'status'],env=env,stdout=subprocess.DEVNULL).returncode==0:
    print('PostgreSQL is already running.');raise SystemExit(0)
args=[str(pg),'-D',str(ROOT/'pgdata'),'-l',str(ROOT/'postgres.log'),'-w',command]
if command=='stop':args.extend(['-m','fast'])
raise SystemExit(subprocess.run(args,env=env).returncode)
