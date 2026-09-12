"""Run the pinned real Conversations backend with its explicit local profile."""
from pathlib import Path
import os
import sys
import hashlib

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
sys.path[:0] = [str(ROOT/'integrations/conversations'), str(RUNTIME/'conversations/src/backend'), str(ROOT/'src')]
os.environ.update(DJANGO_SETTINGS_MODULE='local_settings', DJANGO_CONFIGURATION='LocalMail',
                  PYTHON_SERVER_MODE='async', OPENAI_AGENTS_DISABLE_TRACING='true',
                  HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
os.environ['TIKTOKEN_CACHE_DIR']=str(RUNTIME/'tiktoken-cache')
token_table=RUNTIME/'tiktoken-cache/9b5ad71b2ce5302211f9c61530b329a4922fc6a4'
if not token_table.exists() or hashlib.sha256(token_table.read_bytes()).hexdigest()!='223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7':
    raise SystemExit('Table de tokens absente ou invalide. Exécutez python3 tools/setup_mail.py avant de démarrer.')


def setup_django():
    import configurations
    configurations.setup()


def main():
    command = sys.argv[1] if len(sys.argv)>1 else 'serve'
    if command == 'serve':
        from agentfuse.mailbox import MailWorkspace
        # This launcher owns the single local backend; a restart cannot resume a
        # previous model stream. Preserve effect receipts and close stale tasks.
        for path in [RUNTIME/'mail-workspace.sqlite',*(RUNTIME/'mail-experiments').glob('*.sqlite')]:
            if path.exists():MailWorkspace(path).recover()
        import uvicorn
        uvicorn.run('conversations.asgi:application', host='127.0.0.1', port=8071, access_log=False)
    else:
        setup_django()
        from django.core.management import call_command
        if command == 'init':
            import psycopg
            key=(RUNTIME/'postgres.key').read_text().strip()
            with psycopg.connect(host='127.0.0.1',port=15439,user='agentfuse',password=key,dbname='postgres',autocommit=True) as connection:
                if not connection.execute("SELECT 1 FROM pg_database WHERE datname='agentfuse_conversations'").fetchone():
                    connection.execute('CREATE DATABASE agentfuse_conversations')
            call_command('migrate', interactive=False, verbosity=1)
            from django.contrib.auth import get_user_model
            from django.contrib.auth.hashers import make_password
            User=get_user_model()
            from agentfuse.mailbox import MailWorkspace
            mailbox=MailWorkspace(RUNTIME/'mail-workspace.sqlite')
            mailbox.initialize()
            for name, full in [('alice','Alice Martin'),('marie','Marie Bernard'),('admin','Administration locale')]:
                user,created=User.objects.get_or_create(admin_email=name+'@demo.invalid', defaults={
                    'email':name+'@demo.invalid','full_name':full,'short_name':full.split()[0],
                    'language':'fr-fr','is_staff':name=='admin','is_superuser':name=='admin',
                    'password':make_password('agentfuse-demo'),
                })
                if created:user.set_password('agentfuse-demo');user.save()
                mailbox.bind_identity(str(user.pk),name)
            call_command('check')
        else:
            call_command(command, *sys.argv[2:])


if __name__ == '__main__':main()
