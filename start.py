#!/usr/bin/env python3
"""Start/reuse the local model, mail entry point and Conversations. No downloads."""
from pathlib import Path
import json,os,signal,subprocess,sys,time,urllib.request
ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'.runtime'
PYTHON=ROOT/'.venv/bin/python'

def request(url,headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers or {}),timeout=2) as response:
            return response.status==200
    except Exception:return False

def launch(name,script):
    RUNTIME.mkdir(exist_ok=True)
    log=(RUNTIME/(name+'.log')).open('ab')
    process=subprocess.Popen([str(PYTHON),str(script)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (RUNTIME/(name+'.pid')).write_text(str(process.pid))
    return process

def main():
    if '--restart' in sys.argv:
        pidfile=RUNTIME/'app.pid'
        try:
            pid=int(pidfile.read_text())
            command=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
            if str(ROOT/'tools/serve.py').encode() not in command:
                print('Le processus enregistré ne correspond pas à ce répertoire. Arrêt refusé.');return 1
            os.kill(pid,signal.SIGTERM)
            for _ in range(30):
                try:os.kill(pid,0)
                except ProcessLookupError:break
                time.sleep(.2)
        except (FileNotFoundError,ProcessLookupError):pass
    if not PYTHON.exists() or not (RUNTIME/'Qwen3-1.7B-Q8_0.gguf').exists():
        print('Installez l’environnement local avec python3 tools/setup.py.');return 1
    model=lambda: request('http://127.0.0.1:18081/health',{'Authorization':'Bearer '+(RUNTIME/'model.key').read_text().strip()}) if (RUNTIME/'model.key').exists() else False
    if not model():
        process=launch('model',ROOT/'tools/serve_model.py')
        for _ in range(60):
            if model():break
            if process.poll() is not None:print('Échec du démarrage du modèle. Consultez .runtime/model.log.');return 1
            time.sleep(1)
        else:print('Chargement du modèle en cours. Relancez le script plus tard.');return 1
    if not request('http://127.0.0.1:8787/api/health'):
        process=launch('app',ROOT/'tools/serve.py')
        for _ in range(20):
            if request('http://127.0.0.1:8787/api/health'):break
            if process.poll() is not None:print('Échec du démarrage HTTP. Consultez .runtime/app.log.');return 1
            time.sleep(.5)
        else:print('Service HTTP indisponible. Consultez .runtime/app.log.');return 1
    if (RUNTIME/'conversations-venv/bin/python').exists():
        command=[sys.executable,str(ROOT/'tools/start_mail.py')]
        if '--restart' in sys.argv:command.append('--restart')
        if subprocess.run(command,cwd=ROOT).returncode:return 1
    print('AgentFuse disponible : http://127.0.0.1:8787')
    if (RUNTIME/'mail-services.json').exists():print('Messagerie locale et Conversations : http://127.0.0.1:8071/mail/')
    else:print('Messagerie non démarrée. Exécutez python3 tools/setup_mail.py puis relancez.')
    print('Comptes de démonstration : alice / admin ; mot de passe : agentfuse-demo')
    print('Modèle, données et journaux dans .runtime/ ; le démarrage peut être répété.')
    return 0
if __name__=='__main__':sys.exit(main())
