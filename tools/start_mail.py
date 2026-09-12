"""Start/restart only the localhost mail and real Conversations processes we own."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'.runtime'
PIDFILE=RUNTIME/'mail-services.json'


def main():
    records=json.loads(PIDFILE.read_text()) if PIDFILE.exists() else {}
    restart='--restart' in sys.argv
    subprocess.run([sys.executable,str(ROOT/'tools/postgres.py'),'start'],check=True)
    processes={
        'conversations': [str(RUNTIME/'conversations-venv/bin/python'),str(ROOT/'tools/conversations.py'),'serve'],
        'frontend': [sys.executable,str(ROOT/'tools/serve_conversations_frontend.py')],
    }
    for name,args in processes.items():
        old=records.get(name)
        alive=False
        if old:
            try:
                cmdline=Path('/proc',str(old),'cmdline').read_bytes().replace(b'\0',b' ').decode()
                alive=args[1] in cmdline
                if alive and restart:
                    os.kill(old,signal.SIGTERM)
                    for _ in range(30):
                        if not Path('/proc',str(old)).exists():break
                        time.sleep(.1)
                    alive=False
            except (FileNotFoundError,ProcessLookupError):pass
        if not alive:
            with (RUNTIME/(name+'.log')).open('ab') as log:
                p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=ROOT)
                records[name]=p.pid
    PIDFILE.write_text(json.dumps(records))
    for url in ['http://127.0.0.1:8071/local/session/','http://127.0.0.1:3000/']:
        deadline=time.monotonic()+30
        while True:
            try:
                with urllib.request.urlopen(url,timeout=2) as response:
                    if response.status==200:break
            except OSError:
                if time.monotonic()>=deadline:raise SystemExit('Service did not become ready: '+url)
                time.sleep(.3)
    print('Courrier: http://127.0.0.1:8071/mail/\nConversations: http://127.0.0.1:3000/')

if __name__=='__main__':main()
