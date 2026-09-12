"""Install the pinned native Conversations demo in this folder (Fedora 44 x86-64).

No global packages, Docker, system services, or modification of another checkout.
Existing databases and source files are preserved. --verify performs no downloads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime'
INTEGRATION=ROOT/'integrations/conversations'
NODE=RUNTIME/'node22/node-v22.23.2-linux-x64/bin/node'
PYTHON=RUNTIME/'conversations-venv/bin/python'


def run(args,**kwargs):
    subprocess.run([str(arg) for arg in args],check=True,**kwargs)


def download(name,entry,folder):
    target=folder/name
    if not target.exists():
        folder.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix(target.suffix+'.part')
        run(['curl','-L','--fail','--silent','--show-error',entry['url'],'-o',temporary])
        temporary.replace(target)
    with target.open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
    if actual!=entry['sha256']:raise SystemExit('Checksum mismatch: '+str(target))
    return target


def extract_rpm(path,destination):
    """Read the verified RPM's newc payload, including hardlinks, inside destination."""
    raw=subprocess.check_output(['rpm2cpio',str(path)])
    offset=0;hardlinks={}
    destination.mkdir(parents=True,exist_ok=True)
    while offset<len(raw):
        header=raw[offset:offset+110]
        if header[:6] not in (b'070701',b'070702'):raise ValueError('Unexpected RPM payload')
        fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
        inode,mode,_,_,links,_,size,major,minor,_,_,namesize,_=fields
        offset+=110;name=raw[offset:offset+namesize-1].decode();offset=(offset+namesize+3)&~3
        content=raw[offset:offset+size];offset=(offset+size+3)&~3
        if name=='TRAILER!!!':break
        relative=Path(name.removeprefix('./'))
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe RPM path')
        target=destination/relative
        if not target.resolve().is_relative_to(destination.resolve()):raise ValueError('Unsafe RPM link')
        if stat.S_ISDIR(mode):target.mkdir(parents=True,exist_ok=True)
        elif stat.S_ISREG(mode):
            target.parent.mkdir(parents=True,exist_ok=True)
            if links>1:
                group=hardlinks.setdefault((major,minor,inode),{'paths':[],'data':None,'mode':mode})
                group['paths'].append(target)
                if size:group['data']=content
            else:target.write_bytes(content);target.chmod(mode&0o777)
        elif stat.S_ISLNK(mode):
            link=content.decode();resolved=(target.parent/link).resolve()
            if not resolved.is_relative_to(destination.resolve()):raise ValueError('External RPM symlink')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.is_symlink():target.symlink_to(link)
    for group in hardlinks.values():
        for target in group['paths']:target.write_bytes(group['data'] or b'');target.chmod(group['mode']&0o777)


def verify():
    for path in [PYTHON,NODE,RUNTIME/'postgres/usr/bin/pg_ctl',RUNTIME/'conversations/src/frontend/apps/conversations/dist/index.html',RUNTIME/'pgdata/PG_VERSION']:
        if not path.exists():raise SystemExit('Missing runtime: '+str(path))
    run([PYTHON,'-c',"import django,pydantic_ai,psycopg; print('Django',django.get_version(),'PydanticAI',pydantic_ai.__version__,'PostgreSQL driver',psycopg.__version__)"])
    run([NODE,'--version'])
    run(['pdftotext','-v'])
    run([PYTHON,ROOT/'tools/conversations.py','check'])
    print('Mail runtime verified. Start with: python3 start.py')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if args.verify:return verify()
    release=platform.freedesktop_os_release() if platform.system()=='Linux' else {}
    if platform.machine()!='x86_64' or release.get('ID')!='fedora' or release.get('VERSION_ID')!='44':
        raise SystemExit('This native installer targets Fedora 44 x86-64. See integrations/conversations/README.md for platform boundaries.')
    for command in ['uv','curl','rpm2cpio','pdftotext','prlimit']:
        if not shutil.which(command):raise SystemExit('Required native prerequisite: '+command)
    if not (RUNTIME/'Qwen3-1.7B-Q8_0.gguf').exists():raise SystemExit('First run python3 tools/setup.py')
    manifest=json.loads((ROOT/'tools/mail-assets.json').read_text())
    archives={name:download(name,entry,RUNTIME) for name,entry in manifest['archives'].items()}
    token_cache=RUNTIME/'tiktoken-cache';token_cache.mkdir(exist_ok=True)
    token_url=manifest['archives']['cl100k_base.tiktoken']['url']
    shutil.copyfile(archives['cl100k_base.tiktoken'],token_cache/hashlib.sha1(token_url.encode()).hexdigest())
    upstream=RUNTIME/'conversations'
    if not upstream.exists():
        staging=RUNTIME/'conversations-source'
        with tarfile.open(archives['conversations-source.tar.gz']) as archive:archive.extractall(staging,filter='data')
        (staging/('conversations-'+manifest['upstream_commit'])).rename(upstream)
    if not NODE.exists():
        with tarfile.open(archives['node22.tar.xz']) as archive:archive.extractall(RUNTIME/'node22',filter='data')
    if not (RUNTIME/'postgres/usr/bin/pg_ctl').exists():
        rpms=json.loads((ROOT/'tools/mail-rpms.json').read_text())
        for name,entry in rpms.items():extract_rpm(download(name,entry,RUNTIME/'mail-rpms'),RUNTIME/'postgres')
    if not PYTHON.exists():run(['uv','venv','--python',sys.executable,PYTHON.parent.parent,'--cache-dir',RUNTIME/'setup-cache/uv'])
    run(['uv','pip','install','--python',PYTHON,'--cache-dir',RUNTIME/'setup-cache/uv','-r',INTEGRATION/'requirements.lock'])
    for name in ['postgres.key','conversations.key','model.key']:
        path=RUNTIME/name
        if not path.exists():path.write_text(secrets.token_urlsafe(32)+'\n');path.chmod(0o600)
    pg=RUNTIME/'postgres';pgdata=RUNTIME/'pgdata';env=dict(os.environ,LD_LIBRARY_PATH=str(pg/'usr/lib64'))
    if not (pgdata/'PG_VERSION').exists():
        run([pg/'usr/bin/initdb','-D',pgdata,'-L',pg/'usr/share/pgsql','-U','agentfuse','--pwfile',RUNTIME/'postgres.key','--auth','scram-sha-256','--encoding','UTF8','--locale','C.UTF-8'],env=env)
        with (pgdata/'postgresql.conf').open('a') as file:
            file.write("\nlisten_addresses='127.0.0.1'\nport=15439\n")
            file.write("unix_socket_directories='"+str(RUNTIME).replace("'","''")+"'\n")
            file.write("dynamic_library_path='"+str(pg/'usr/lib64/pgsql').replace("'","''")+"'\n")
    run([sys.executable,ROOT/'tools/patch_conversations.py'])
    yarn=RUNTIME/'node-tools/node_modules/yarn/bin/yarn.js'
    if not yarn.exists():
        run([NODE,NODE.parent.parent/'lib/node_modules/npm/bin/npm-cli.js','install','--prefix',RUNTIME/'node-tools','yarn@1.22.22','--cache',RUNTIME/'setup-cache/npm','--no-audit','--no-fund'])
    frontend=upstream/'src/frontend'
    node_env=dict(os.environ,PATH=str(NODE.parent)+':'+os.environ['PATH'])
    run([NODE,yarn,'install','--frozen-lockfile','--non-interactive','--cache-folder',RUNTIME/'setup-cache/yarn'],cwd=frontend,env=node_env)
    run([NODE,frontend/'node_modules/vite/bin/vite.js','build'],cwd=frontend/'apps/conversations',env=node_env)
    run([sys.executable,ROOT/'tools/postgres.py','start'])
    (RUNTIME/'conversations-static').mkdir(exist_ok=True)
    run([PYTHON,ROOT/'tools/conversations.py','init'])
    verify()


if __name__=='__main__':main()
