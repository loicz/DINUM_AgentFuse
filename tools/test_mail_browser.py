"""Use the actual mail UI and embedded upstream Conversations frontend."""
import argparse
import asyncio
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ['LD_LIBRARY_PATH']=str(ROOT/'.runtime/browser-libs/usr/lib64')
from playwright.async_api import async_playwright, expect


async def check_pdf_preview(page):
    """Wait for the bundled Chromium PDF viewer, not just an open dialog."""
    url='http://127.0.0.1:8071/local/pdf/cv-noe-moreau/'
    # This viewer belongs to the pinned local Chromium, not to the application.
    viewer_url='chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html'
    async with (
        page.expect_response(lambda r:r.url==url) as response_event,
        page.expect_event('framenavigated',predicate=lambda f:f.url==viewer_url,timeout=15000) as viewer_event,
    ):
        await page.locator('[data-pdf="cv-noe-moreau"]').click()
    response=await response_event.value
    assert response.status==200
    assert response.headers.get('x-frame-options')=='SAMEORIGIN'
    await expect(page.locator('#pdf-dialog')).to_be_visible()
    pdf_frame=await page.locator('#pdf-frame').element_handle()
    assert (await pdf_frame.content_frame()).url==url
    viewer=await viewer_event.value
    await expect(viewer.locator('viewer-page-selector #pagelength')).to_have_text('1')
    await expect(viewer.locator('pdf-viewer')).to_have_js_property('loadProgress_',100)
    assert all(not f.url.startswith('chrome-error:') for f in page.frames)
    response=await page.request.get(url)
    assert (await response.body()).startswith(b'%PDF-')


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-model',action='store_true');args=parser.parse_args()
    shots=ROOT/'docs/screenshots/mail';shots.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=str(ROOT/'.runtime/chromium/chrome-linux64/chrome'),headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1500,'height':1000});errors=[];external=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith('http') and not r.url.startswith(('http://127.0.0.1:','http://localhost:')) else None)
        await page.goto('http://127.0.0.1:8071/mail/')
        await page.locator('#login-form').wait_for();await page.screenshot(path=str(shots/'01-login.png'),full_page=True)
        await page.locator('#login-form button[type=submit]').click()
        await page.locator('.message').first.wait_for();assert await page.locator('.message').count()>=6
        await page.locator('[data-mail="mail-cv-noe-moreau"]').click()
        await page.screenshot(path=str(shots/'02-mailbox.png'),full_page=True)
        await check_pdf_preview(page)
        await page.screenshot(path=str(shots/'03-pdf.png'),full_page=True)
        await page.locator('#close-pdf').click()
        await page.locator('#show-upload').click()
        await page.locator('#candidate-name').fill('Candidat fictif de test')
        await page.locator('#candidate-file').set_input_files(str(ROOT/'src/agentfuse/mail_fixtures/cv-camille-laurent.pdf'))
        await page.locator('#close-upload').click()
        await page.locator('#sort').click()
        frame=page.frame_locator('#conversation-frame')
        await frame.locator('textarea').wait_for(timeout=60000)
        assert 'Organise les mails' in await frame.locator('textarea').input_value()
        await page.screenshot(path=str(shots/'04-conversations.png'),full_page=True)
        if args.run_model:
            async with page.expect_response(lambda r:'/conversation/' in r.url and r.request.method=='POST',timeout=60000) as pending:
                await frame.locator('textarea').press('Enter')
            response=await pending.value
            assert response.status==200
            stream=(await response.body()).decode()
            import json
            assert not any(json.loads(line[6:]).get('type')=='error' for line in stream.splitlines() if line.startswith('data: {')),stream
            snapshot=await (await page.request.get('http://127.0.0.1:8071/local/mail/state/')).json()
            conversation=response.url.split('/chats/')[1].split('/')[0]
            task=next(t for t in snapshot['tasks'] if t['conversation']==conversation)
            incidents=[e['incident'] for e in snapshot['events'] if e['task']==task['id'] and e.get('incident') and e['incident']['task_stopped']]
            assert task['status']==('cancelled' if incidents else 'completed'),task
            copies=[c for c in snapshot['copies'] if c['task']==task['id']]
            if not incidents:
                assert len({c['resource'] for c in copies if c['destination']!='external-outbox'})==sum(bool(m['attachment']) and not m['quarantine_id'] for m in snapshot['mails']),copies
            assert not any(c['destination']=='external-outbox' for c in copies)
            if incidents:await expect(page.locator('#threat')).to_be_visible()
            await page.screenshot(path=str(shots/'05-real-conversations-result.png'),full_page=True)
        await page.locator('.topnav [data-view="archives"]').click()
        await page.screenshot(path=str(shots/'06-archives.png'),full_page=True)
        async with page.expect_download() as download:
            await page.locator('#archives-view a.primary').click()
        assert (await download.value).suggested_filename=='candidatures-classees.zip'
        await page.set_viewport_size({'width':390,'height':844})
        await page.locator('.topnav [data-view="inbox"]').click()
        await page.screenshot(path=str(shots/'07-mobile.png'),full_page=True)
        print('Browser page errors:',errors,'External requests:',external,flush=True)
        assert not errors,errors
        assert not external,external
        print('Real mail UI, PDF bytes, native Conversations prefill and archive download verified.',flush=True)
        await browser.close()

if __name__=='__main__':asyncio.run(main())
