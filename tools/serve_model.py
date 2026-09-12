"""Launch only the bundled local inference engine, authenticated and loopback-bound."""
from pathlib import Path
import os
import secrets
import subprocess

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime'
key=RUNTIME/'model.key'
if not key.exists():
    key.write_text(secrets.token_urlsafe(32)+'\n')
    key.chmod(0o600)
binary=RUNTIME/'llama/llama-b10883/llama-server'
args=[str(binary),'-m',str(RUNTIME/'Qwen3-1.7B-Q8_0.gguf'),'--host','127.0.0.1','--port','18081','--jinja','--ctx-size','8192','--parallel','1','--threads','12','--threads-batch','12','--n-predict','1500','--reasoning','off','--alias','agentfuse-local','--api-key-file',str(key),'--no-webui','--cors-origins','http://127.0.0.1:8787']
os.execv(binary,args)
