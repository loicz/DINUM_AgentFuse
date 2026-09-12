"""Real Django sessions/CSRF/ORM routes; temporary mail DB, no model double.

Uses the installed Conversations environment and its localhost PostgreSQL.
Only conversations created by this test are removed on completion.
"""
from pathlib import Path
import asyncio
import json
import runpy
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'tools/conversations.py'))['setup_django']()
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from chat.models import ChatConversation
from agentfuse.mailbox import EXTERNAL_RECIPIENT, MailWorkspace
import mail_views
import mail_tools


def login(name):
    client=Client(enforce_csrf_checks=True)
    csrf=client.get('/local/session/').json()['csrf']
    response=client.post('/local/session/',data=json.dumps({'user':name,'password':'agentfuse-demo'}),content_type='application/json',HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code==200
    client.defaults['HTTP_X_CSRFTOKEN']=response.json()['csrf']
    return client


def post(client,path,data):
    return client.post(path,data=json.dumps(data),content_type='application/json')


def main():
    created=[]
    try:
        with tempfile.TemporaryDirectory(prefix='agentfuse-mail-http-') as folder:
            runtime=Path(folder);host=MailWorkspace(runtime/'mail-workspace.sqlite');host.initialize(scenario='clean')
            users={name:get_user_model().objects.get(admin_email=name+'@demo.invalid') for name in ('alice','marie','admin')}
            for name,user in users.items():host.bind_identity(str(user.pk),name)
            with patch.object(mail_views,'RUNTIME',runtime),patch.object(mail_tools,'RUNTIME',runtime):
                assert Client().get('/local/mail/state/').status_code==401
                alice=login('alice');admin=login('admin');marie=login('marie')
                assert post(alice,'/local/mail/experiments/',{}).status_code==403
                assert post(alice,'/local/mail/policy/',{}).status_code==403
                assert post(admin,'/local/mail/start/',{}).status_code==409
                no_csrf=Client(enforce_csrf_checks=True);no_csrf.cookies=alice.cookies
                assert post(no_csrf,'/local/mail/start/',{}).status_code==403
                data=host.pdf('alice','cv-camille-laurent')[0]
                assert alice.post('/local/application-upload/',{'name':'Test','file':SimpleUploadedFile('bad.pdf',b'not PDF')}).status_code==409
                upload=alice.post('/local/application-upload/',{'name':'Candidat de test fictif','file':SimpleUploadedFile('test.pdf',data,content_type='application/pdf')})
                assert upload.status_code==200,upload.content
                rid=upload.json()['id']
                preview=alice.get('/local/pdf/'+rid+'/')
                assert preview.status_code==200 and preview.content==data
                assert preview['Content-Type']=='application/pdf'
                assert preview['Content-Disposition'].startswith('inline;')
                assert preview['X-Frame-Options']=='SAMEORIGIN'
                download=alice.get('/local/pdf/'+rid+'/',{'download':'1'})
                assert download.content==data and download['Content-Disposition'].startswith('attachment;')
                assert download['X-Frame-Options']=='DENY'
                anonymous=Client().get('/local/pdf/'+rid+'/')
                assert anonymous.status_code==401 and anonymous['X-Frame-Options']=='DENY'
                assert marie.get('/local/pdf/'+rid+'/').status_code==403
                assert alice.get('/mail/')['X-Frame-Options']=='DENY'
                response=post(alice,'/local/mail/start/',{});assert response.status_code==200,response.content
                chat=response.json();created.append(chat['conversation'])
                assert ChatConversation.objects.get(pk=chat['conversation']).owner_id==users['alice'].pk
                result=asyncio.run(host.perform(chat['task'],'file_cv',{'attachment_id':rid,'folder':'informatique'}))
                copy=result.execution.result.copy_id
                assert alice.get('/local/copy/'+copy+'/').content==data
                assert marie.get('/local/copy/'+copy+'/').status_code==403
                assert post(alice,'/local/mail/cancel/',{}).json()['cancelled']==1
                assert asyncio.run(host.perform(chat['task'],'file_cv',{'attachment_id':rid,'folder':'droit'})).execution is None
                experiment=post(admin,'/local/mail/experiments/',{'scenario':'attack'});assert experiment.status_code==200,experiment.content
                pair=experiment.json();created.extend(b['conversation'] for b in pair['branches'])
                assert alice.get('/local/mail/experiment/',{'id':pair['id']}).status_code==409
                branch=pair['branches'][0]
                assert alice.get('/local/pdf/cv-noe-moreau/',{'conversation':branch['conversation']}).status_code==403
                preview=admin.get('/local/pdf/cv-noe-moreau/',{'conversation':branch['conversation']})
                assert preview.status_code==200 and preview.content.startswith(b'%PDF-')
                assert preview['X-Frame-Options']=='SAMEORIGIN'
                proof=admin.get('/local/mail/experiment/',{'id':pair['id']});assert proof.status_code==200,proof.content
                assert proof.json()['assessment']['same_inputs'] and not proof.json()['assessment']['demo_complete']
                policy=host.policy().model_dump(mode='json')
                assert post(admin,'/local/mail/policy/',{'policy':policy,'expected':'outdated'}).status_code==409
                assert post(admin,'/local/mail/policy/',{'policy':policy,'expected':policy['policy_version']}).status_code==200
                # Invoke the actual upstream service through its native streaming
                # route with an unsupported attachment. No LLM/tools may run.
                chat2=post(alice,'/local/mail/start/',{}).json();created.append(chat2['conversation'])
                unsupported=post(alice,'/api/v1.0/chats/'+chat2['conversation']+'/conversation/',{'messages':[{'id':'unsupported-input','role':'user','parts':[{'type':'text','text':'Lire ce PDF.'},{'type':'file','mediaType':'application/pdf','url':'data:application/pdf;base64,JVBERi0xLjQ='}]}]})
                assert unsupported.status_code==200,unsupported.content
                async def consume():return b''.join([part async for part in unsupported.streaming_content])
                stream=asyncio.run(consume()).decode()
                assert 'error' in stream and 'messagerie' in stream,stream
                assert host.task(chat2['task'])['status']=='failed'
                assert host.task(chat2['task'])['actions']==[]
                contained=post(alice,'/local/mail/start/',{}).json();created.append(contained['conversation'])
                asyncio.run(host.perform(contained['task'],'read_resource',{'resource_id':rid}))
                blocked=asyncio.run(host.perform(contained['task'],'forward_cv',{'attachment_id':rid,'recipient':EXTERNAL_RECIPIENT}))
                assert blocked.decision.outcome=='block'
                state=alice.get('/local/mail/state/').json()
                q=state['quarantine'][0]
                assert q['resource']==rid and q['source']['mails'][0]['sender_name']=='Candidat de test fictif'
                assert alice.get('/local/pdf/'+rid+'/').status_code==403
                assert alice.get('/local/copy/'+copy+'/').status_code==403
                path='/local/quarantine/'+q['id']+'/'
                review=alice.get(path)
                assert review.status_code==200 and review.content==data
                assert review['Content-Disposition'].startswith('attachment;') and review['X-Frame-Options']=='DENY'
                assert Client().get(path).status_code==401 and marie.get(path).status_code==403
                # An experiment's quarantine remains in its own workspace.
                protected=next(b for b in pair['branches'] if b['mode']=='protected')
                isolated=mail_tools.workspace_for(protected['conversation'],users['admin'])
                asyncio.run(isolated.perform(protected['task'],'read_resource',{'resource_id':'cv-noe-moreau'}))
                asyncio.run(isolated.perform(protected['task'],'forward_cv',{'attachment_id':'cv-noe-moreau','recipient':EXTERNAL_RECIPIENT}))
                iq=isolated.view('alice')['quarantine'][0]
                path='/local/quarantine/'+iq['id']+'/'
                assert admin.get(path,{'conversation':protected['conversation']}).status_code==200
                assert alice.get(path,{'conversation':protected['conversation']}).status_code==403
                assert admin.get(path).status_code==403
                proof=admin.get('/local/mail/experiment/',{'id':pair['id']})
                assert proof.status_code==200 and proof.json()['assessment']['same_inputs']
                print('Django HTTP: sessions, CSRF, upload, actual PDF copies, ACL, cancellation, experiment isolation and policy versions passed.')
                print('Quarantine HTTP: provenance, ordinary download denial, explicit review download and experiment isolation passed.')
    finally:
        ChatConversation.objects.filter(pk__in=created).delete()


if __name__=='__main__':main()
