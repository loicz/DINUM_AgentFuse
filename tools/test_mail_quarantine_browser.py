"""Real Django + browser on a temporary mailbox; scripted tool calls, no LLM.

Run with the Conversations Python environment. Only the browser subprocess uses
the existing prototype test environment. No running product data is changed.
"""
import argparse
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


async def browser_check(base,output):
    os.environ['LD_LIBRARY_PATH']=str(ROOT/'.runtime/browser-libs/usr/lib64')
    from playwright.async_api import async_playwright,expect
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=str(ROOT/'.runtime/chromium/chrome-linux64/chrome'),headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];external=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith('http') and not r.url.startswith(base+'/') else None)
        await page.goto(base+'/mail/')
        await page.locator('#login-form button').click()
        await expect(page.locator('#threat')).to_be_visible()
        await expect(page.locator('#quarantine-count')).to_have_text('1')
        await page.locator('.topnav [data-view="security"]').click()
        await expect(page.locator('#security-events')).to_contain_text('Plusieurs PDF ont été lus')
        await expect(page.locator('#security-events')).to_contain_text('Seul PDF lu')
        await expect(page.locator('#security-events')).to_contain_text('noe-moreau@candidat.example')
        await expect(page.locator('#security-events')).to_contain_text('Candidature — Noé Moreau')
        await expect(page.locator('#security-events')).to_contain_text('<img src=x onerror=alert(1)>')
        assert await page.locator('img[src="x"]').count()==0
        await page.screenshot(path=str(output/'security.png'),full_page=True)
        await page.locator('.topnav [data-view="quarantine"]').click()
        await expect(page.locator('#quarantine-files')).to_contain_text('cv-noe-moreau.pdf')
        await page.locator('#quarantine-files summary').click()
        async with page.expect_response(lambda r:r.url==base+'/local/mail/state/'):
            pass
        await expect(page.locator('#quarantine-files details')).to_have_attribute('open','')
        state=await (await page.request.get(base+'/local/mail/state/')).json()
        q=state['quarantine'][0]
        async with page.expect_download() as pending:
            await page.locator('#quarantine-files a').click()
        download=await pending.value
        import hashlib
        assert hashlib.sha256(Path(await download.path()).read_bytes()).hexdigest()==q['sha256']
        assert (await page.request.get(base+'/local/pdf/cv-noe-moreau/')).status==403
        copy=next(c for c in state['copies'] if c['resource']=='cv-noe-moreau')
        assert (await page.request.get(base+'/local/copy/'+copy['id']+'/')).status==403
        await page.screenshot(path=str(output/'quarantine.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(output/'quarantine-mobile.png'),full_page=True)
        await page.reload()
        await expect(page.locator('#quarantine-count')).to_have_text('1')
        await page.locator('[data-mail="mail-cv-noe-moreau"]').click()
        await expect(page.locator('#reader')).to_contain_text('En quarantaine')
        assert await page.locator('#reader [data-pdf]').count()==0
        await page.locator('#logout').click()
        assert not errors and not external,(errors,external)
        await browser.close()
    print('Browser: provenance, ambiguity, quarantine, PDF download, reload, escaping and mobile layout passed.',flush=True)


def main(output):
    import runpy
    import threading
    from unittest.mock import patch
    from wsgiref.simple_server import make_server,WSGIRequestHandler
    runpy.run_path(str(ROOT/'tools/conversations.py'))['setup_django']()
    from django.contrib.auth import get_user_model
    from django.core.wsgi import get_wsgi_application
    from agentfuse.mailbox import EXTERNAL_RECIPIENT,MailWorkspace
    import mail_tools
    import mail_views

    class QuietHandler(WSGIRequestHandler):
        def log_message(self,*args):pass

    with tempfile.TemporaryDirectory(prefix='agentfuse-quarantine-ui-') as folder:
        runtime=Path(folder);host=MailWorkspace(runtime/'mail-workspace.sqlite');host.initialize(scenario='clean')
        alice=get_user_model().objects.get(admin_email='alice@demo.invalid')
        host.bind_identity(str(alice.pk),'alice')
        with host.db() as c:c.execute("UPDATE mails SET sender_name=? WHERE attachment='cv-noe-moreau'",('<img src=x onerror=alert(1)>',))
        async def prepare():
            t=host.conversation_task(str(alice.pk),'browser-unique','Classer les CV.')
            await host.perform(t,'read_resource',{'resource_id':'cv-noe-moreau'})
            await host.perform(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
            await host.perform(t,'forward_cv',{'attachment_id':'cv-noe-moreau','recipient':EXTERNAL_RECIPIENT})
            t=host.conversation_task(str(alice.pk),'browser-ambiguous','Classer les CV restants.')
            for rid in ('cv-camille-laurent','cv-ines-roux'):await host.perform(t,'read_resource',{'resource_id':rid})
            await host.perform(t,'forward_cv',{'attachment_id':'cv-ines-roux','recipient':EXTERNAL_RECIPIENT})
        asyncio.run(prepare())
        with patch.object(mail_views,'RUNTIME',runtime),patch.object(mail_tools,'RUNTIME',runtime):
            with make_server('127.0.0.1',0,get_wsgi_application(),handler_class=QuietHandler) as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    subprocess.run([str(ROOT/'.venv/bin/python'),__file__,'--browser',f'http://127.0.0.1:{server.server_port}','--output',str(output)],check=True)
                finally:server.shutdown();thread.join()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.browser:asyncio.run(browser_check(args.browser,args.output))
    else:main(args.output)
