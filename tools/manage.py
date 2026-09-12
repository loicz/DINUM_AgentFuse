"""Manage only Python/llama processes whose command points to this trial directory."""
from pathlib import Path
import argparse,os,signal
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('action',choices=['status','stop-app']);args=p.parse_args()
for entry in Path('/proc').iterdir():
 if not entry.name.isdigit():continue
 try:
  raw=(entry/'cmdline').read_bytes();parts=raw.split(b'\0');pid=int(entry.name)
  if pid==os.getpid() or entry.stat().st_uid!=os.getuid():continue
  relevant=str(ROOT/'tools/serve.py').encode() in parts
  if relevant:
   print('AgentFuse app process',pid)
   if args.action=='stop-app':os.kill(pid,signal.SIGTERM)
 except (OSError,ValueError):continue
