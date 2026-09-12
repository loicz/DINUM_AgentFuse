"""Reproducible Linux x86-64 trial setup, contained entirely in this folder."""
from pathlib import Path
import hashlib,json,os,platform,subprocess,sys,tarfile,urllib.request,venv
ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'.runtime';RUNTIME.mkdir(exist_ok=True)
MODEL_URL='https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/90862c4b9d2787eaed51d12237eafdfe7c5f6077/Qwen3-1.7B-Q8_0.gguf'
LLAMA_URL='https://github.com/ggml-org/llama.cpp/releases/download/b10883/llama-b10883-bin-ubuntu-x64.tar.gz'

def download(url,path):
    if path.exists():return
    temporary=path.with_suffix(path.suffix+'.part')
    print('Téléchargement : '+path.name,flush=True)
    with urllib.request.urlopen(url,timeout=60) as response,temporary.open('wb') as target:
        while block:=response.read(1024*1024):target.write(block)
    temporary.replace(path)

def main():
    if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
        raise SystemExit('L’installateur du modèle cible Linux x86-64. Le cœur Python est indépendant de ce lanceur.')
    python=ROOT/'.venv/bin/python'
    if not python.exists():venv.create(ROOT/'.venv',with_pip=True)
    if subprocess.run([str(python),'-m','pip','--version'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        subprocess.run([str(python),'-m','ensurepip','--upgrade'],check=True)
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.lock')],check=True)
    subprocess.run([str(python),'-m','pip','install','--no-deps','-e',str(ROOT)],check=True)
    download(MODEL_URL,RUNTIME/'Qwen3-1.7B-Q8_0.gguf')
    download(LLAMA_URL,RUNTIME/'llama.tar.gz')
    manifest=json.loads((ROOT/'tools/assets.json').read_text())
    for name,expected in manifest.items():
        actual=hashlib.file_digest((RUNTIME/name).open('rb'),'sha256').hexdigest()
        if actual!=expected:raise SystemExit('Échec de vérification du téléchargement : '+name)
    if not (RUNTIME/'llama/llama-b10883/llama-server').exists():
        with tarfile.open(RUNTIME/'llama.tar.gz') as archive:archive.extractall(RUNTIME/'llama',filter='data')
    print('Installation terminée. Exécutez python3 start.py')
if __name__=='__main__':main()
