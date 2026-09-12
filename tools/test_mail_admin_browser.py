"""Actual browser administration and recorded real Conversations evidence."""
import asyncio
from email.parser import BytesParser
from email.policy import default
import hashlib
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ['LD_LIBRARY_PATH']=str(ROOT/'.runtime/browser-libs/usr/lib64')
from playwright.async_api import async_playwright,expect


async def main():
    shots=ROOT/'docs/screenshots/mail'
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=str(ROOT/'.runtime/chromium/chrome-linux64/chrome'),headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1500,'height':1000});errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto('http://127.0.0.1:8071/mail/')
        await page.locator('#user').select_option('admin');await page.locator('#login-form button[type=submit]').click()
        await page.locator('#demo-tab').wait_for()
        await page.locator('#demo-tab').click()
        state=(await page.request.get('http://127.0.0.1:8071/local/mail/state/')).json()
        state=await state
        report=None
        for record in state['experiments']:
            response=await page.request.get('http://127.0.0.1:8071/local/mail/experiment/?id='+record['pair_id'])
            candidate=await response.json()
            if candidate['assessment']['demo_complete']:
                report=candidate;break
        assert report,'No completed genuine attack comparison is available.'
        await page.locator('#history').select_option(report['id'])
        await expect(page.locator('.comparison-verdict')).to_contain_text('avant exécution')
        await page.screenshot(path=str(shots/'08-real-comparison.png'),full_page=True)
        async with page.expect_download() as evidence:
            await page.locator('#export-evidence').click()
        assert (await evidence.value).suggested_filename.endswith('.json')
        baseline=next(b for b in report['branches'] if b['mode']=='baseline')
        copy=next(c for c in baseline['state']['copies'] if c['destination']=='external-outbox')
        received=await page.request.get('http://127.0.0.1:8071/local/copy/'+copy['id']+'/?conversation='+baseline['conversation']+'&format=eml')
        assert received.status==200
        message=BytesParser(policy=default).parsebytes(await received.body())
        attachment=next(message.iter_attachments()).get_payload(decode=True)
        assert attachment.startswith(b'%PDF-') and hashlib.sha256(attachment).hexdigest()==copy['sha256']
        await page.locator('#policy-tab').click()
        await page.locator('#rule-label').fill('Vérification navigateur · pause Gestion')
        await page.locator('#rule-target').select_option('gestion')
        await page.locator('#rule-form button.primary').click()
        rule=page.locator('.policy-rule').filter(has_text='Vérification navigateur · pause Gestion')
        try:
            await expect(rule).to_be_visible()
            await page.screenshot(path=str(shots/'09-policy.png'),full_page=True)
        finally:
            # Remove only the rule created by this test; original policies remain.
            if await rule.count():await rule.locator('.remove-rule').click()
        await expect(rule).to_have_count(0)
        assert not errors,errors
        print('Admin browser: saved real comparison, JSON export, actual MIME/PDF delivery and policy publish/remove passed.')
        await browser.close()


if __name__=='__main__':asyncio.run(main())
