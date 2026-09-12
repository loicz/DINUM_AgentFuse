"""Run with the separately installed wheel environment, never the source package."""
import asyncio,tempfile
from pathlib import Path
import httpx
import agentfuse
from agentfuse.app import create_app

async def main():
    assert 'site-packages' in str(agentfuse.__file__),agentfuse.__file__
    with tempfile.TemporaryDirectory(prefix='agentfuse-installed-') as folder:
        app=create_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',timeout=10) as client:
            response=await client.get('/')
            assert response.status_code==307 and response.headers['location']=='http://127.0.0.1:8071/mail/'
            for path in ('/api/health',):
                async with asyncio.timeout(10):response=await client.get(path)
                assert response.status_code==200,(path,response.status_code)
            for path in ('/legacy','/documents/old-document','/static/index.html','/static/app.js','/static/style.css','/static/mark.svg'):
                assert (await client.get(path)).status_code==404,path
            response=await client.post('/api/login',json={'user':'alice','password':'agentfuse-demo'})
            assert response.status_code==404
        print('Wheel installé : redirection, état du service et absence des anciennes API vérifiés.')
        from agentfuse.mailbox import MailWorkspace
        from importlib.resources import files
        assert (files('agentfuse')/'mail_web/index.html').is_file()
        assert {p.name for p in (files('agentfuse')/'assets').iterdir()}=={'NotoSansSC.ttf','OFL.txt'}
        assert all((files('agentfuse')/'mail_web'/name).is_file() for name in ('mail.js','mail.css'))
        mail=MailWorkspace(Path(folder)/'mail.sqlite');mail.initialize(scenario='clean');mail.bind_identity('installed-user','alice')
        task=mail.conversation_task('installed-user','installed-chat','Classer les candidatures.')
        copied=await mail.perform(task,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
        assert copied.execution.status=='succeeded'
        assert mail.copy_file('alice',copied.execution.result.copy_id)[0]==mail.pdf('alice','cv-noe-moreau')[0]
        print('Installed wheel: mail adapter, bundled PDF fixtures and exact PDF execution passed.')
if __name__=='__main__':asyncio.run(main())
