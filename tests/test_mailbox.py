"""Real local PDF/SQLite effect tests; these do not claim to test model persuasion."""
import asyncio
from io import BytesIO
import json
import zipfile

import pytest

from agentfuse.contracts import CopyFile, DestinationRef, ExecutionTicket, Policy
from agentfuse.mailbox import EXTERNAL_RECIPIENT, FOLDERS, MailWorkspace, parse_pdf
from agentfuse.ports import HostConflict
from agentfuse.storage import digest, packed


@pytest.fixture
def mail(tmp_path):
    host=MailWorkspace(tmp_path/'mail.sqlite');host.initialize(scenario='clean');host.bind_identity('django-alice','alice')
    return host


def task(host):return host.conversation_task('django-alice','chat-'+digest(str(id(host))), 'Organiser les candidatures du jour.')


async def test_normal_cv_classification_keeps_exact_original_bytes(mail):
    t=task(mail)
    assert (await mail.perform(t,'read_resource',{'resource_id':'mail-today'})).decision.outcome=='allow'
    expected={'cv-camille-laurent':'informatique','cv-noe-moreau':'droit','cv-ines-roux':'environnement','cv-sarah-bernard':'gestion'}
    for rid,folder in expected.items():
        assert (await mail.perform(t,'read_resource',{'resource_id':rid})).execution.status=='succeeded'
        result=await mail.perform(t,'file_cv',{'attachment_id':rid,'folder':folder})
        assert result.decision.outcome=='allow' and result.execution.status=='succeeded'
    with zipfile.ZipFile(BytesIO(mail.archive_zip('alice'))) as archive:
        assert len(archive.namelist())==4
        for rid,folder in expected.items():assert archive.read(folder+'/'+rid+'.pdf')==mail.pdf('alice',rid)[0]
    assert all(a['status'] != 'ask' for a in mail.task(t)['actions'])


async def test_injected_pdf_scan_miss_does_not_allow_external_delivery(tmp_path):
    host=MailWorkspace(tmp_path/'mail.sqlite');host.initialize();host.bind_identity('django-alice','alice');t=task(host)
    read=await host.perform(t,'read_resource',{'resource_id':'cv-noe-moreau'})
    assert '[im_start]' in read.execution.result.text
    assert not read.execution.result.scan.findings
    result=await host.perform(t,'forward_cv',{'attachment_id':'cv-noe-moreau','recipient':EXTERNAL_RECIPIENT})
    assert result.decision.outcome=='block' and result.execution is None
    with host.db() as c:
        assert c.execute('SELECT COUNT(*) FROM file_copies').fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM effects WHERE capability='file.copy'").fetchone()[0]==0
    assert (await host.perform(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})).execution is None
    incident=host.incident(result.decision.action_id,'alice')
    assert incident['attribution']=='single_exposed_pdf' and incident['task_stopped']
    source=incident['sources'][0]
    assert source['mails'][0]['sender']=='noe-moreau@candidat.example'
    assert source['mails'][0]['subject']=='Candidature — Noé Moreau'
    assert host.quarantine_file('alice',source['quarantine_id'])[0].startswith(b'%PDF-')
    assert host.task(t)['status']=='cancelled'


async def test_isolated_baseline_delivers_real_mime_attachment_and_keeps_acl(tmp_path):
    with pytest.raises(HostConflict):
        MailWorkspace(tmp_path/'forbidden.sqlite').initialize(baseline=True)
    host=MailWorkspace(tmp_path/'mail-experiments'/'experiment-test.sqlite');host.initialize(baseline=True);host.bind_identity('django-alice','alice');t=task(host)
    result=await host.perform(t,'forward_cv',{'attachment_id':'cv-noe-moreau','recipient':EXTERNAL_RECIPIENT})
    assert result.execution.status=='succeeded'
    from email.parser import BytesParser
    from email.policy import default
    with host.db() as c:
        row=c.execute('SELECT * FROM file_copies').fetchone()
        msg=BytesParser(policy=default).parsebytes(row['eml'])
        assert msg['To']==EXTERNAL_RECIPIENT
        original=c.execute("SELECT bytes FROM pdfs WHERE resource='cv-noe-moreau'").fetchone()[0]
        assert next(msg.iter_attachments()).get_payload(decode=True)==original
        c.execute("UPDATE resources SET acl='[\"marie\"]' WHERE id='cv-sarah-bernard'")
    denied=await host.perform(t,'forward_cv',{'attachment_id':'cv-sarah-bernard','recipient':EXTERNAL_RECIPIENT})
    assert denied.decision.reason_code=='permissions.denied' and denied.execution is None


@pytest.mark.parametrize('folder',['../gestion','/tmp','gestion/../../external-outbox','external-outbox'])
async def test_cannot_smuggle_destination_through_archive_tool(mail,folder):
    with pytest.raises(HostConflict):await mail.perform(task(mail),'file_cv',{'attachment_id':'cv-noe-moreau','folder':folder})
    assert mail.view('alice')['copies']==[]


async def test_copy_is_bound_to_pdf_hash_filename_and_source_version(mail):
    t=task(mail);action=mail.normalize(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
    for field,value in [('sha256','sha256:'+'0'*64),('filename','different.pdf')]:
        changed=action.model_copy(update={'operation':action.operation.model_copy(update={field:value})})
        assert mail.evaluator.evaluate(await mail.load_request(changed)).outcome=='block'
    with mail.db() as c:c.execute("UPDATE resources SET version='changed' WHERE id='cv-noe-moreau'")
    assert mail.evaluator.evaluate(await mail.load_request(action)).outcome=='block'
    assert not mail.view('alice')['copies']


async def test_acl_rechecked_between_decision_and_execution(mail):
    t=task(mail);a=mail.normalize(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
    r=await mail.load_request(a);decision=mail.evaluator.evaluate(r)
    await mail.record_decision(a,decision);ticket=await mail.claim_execution(r,decision)
    with mail.db() as c:c.execute("UPDATE mail_destinations SET acl='[\"admin\"]' WHERE id='droit'")
    with pytest.raises(HostConflict):await mail.execute(a,ticket)
    assert not mail.view('alice')['copies']


async def test_exact_copy_cannot_be_reexecuted_with_same_ticket(mail):
    t=task(mail);a=mail.normalize(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
    r=await mail.load_request(a);d=mail.evaluator.evaluate(r);await mail.record_decision(a,d);ticket=await mail.claim_execution(r,d)
    await mail.execute(a,ticket)
    with pytest.raises(HostConflict):await mail.execute(a,ticket)
    assert len(mail.view('alice')['copies'])==1


async def test_missing_policy_and_wrong_identity_fail_closed(mail):
    with pytest.raises(HostConflict):mail.conversation_task('unmapped-user','chat-new','Trier les CV.')
    t=task(mail)
    with mail.db() as c:c.execute('DELETE FROM policies')
    with pytest.raises(HostConflict):await mail.perform(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
    assert not mail.view('alice')['copies']


def test_invalid_and_empty_pdf_rejected():
    for value in (b'not a PDF',b'%PDF-1.4\nbroken',b'%PDF-'+b'x'*(2*1024*1024)):
        with pytest.raises(HostConflict):parse_pdf(value)


async def test_uploaded_pdf_is_real_untrusted_and_gets_background_scope(mail):
    original=mail.pdf('alice','cv-camille-laurent')[0]
    rid=mail.add_application('alice','Candidat fictif',original)
    assert mail.pdf('alice',rid)[0]==original
    t=task(mail)
    read=await mail.perform(t,'read_resource',{'resource_id':rid})
    assert read.decision.outcome=='allow'
    assert read.execution.result.scan.source.data_class=='restricted'
    assert read.execution.result.scan.source.instruction_trust=='untrusted'
    assert (await mail.perform(t,'file_cv',{'attachment_id':rid,'folder':'informatique'})).execution.status=='succeeded'
    assert (await mail.perform(t,'forward_cv',{'attachment_id':rid,'recipient':EXTERNAL_RECIPIENT})).decision.outcome=='block'


async def test_stop_revokes_future_execution_and_unblocks_upload(mail):
    t=task(mail);mail.claim_run(t)
    with pytest.raises(HostConflict):mail.claim_run(t)
    original=mail.pdf('alice','cv-camille-laurent')[0]
    with pytest.raises(HostConflict):mail.add_application('alice','Fictif',original)
    assert mail.cancel_tasks('alice')==1
    assert (await mail.perform(t,'file_cv',{'attachment_id':'cv-camille-laurent','folder':'informatique'})).execution is None
    mail.add_application('alice','Fictif',original)
    assert not mail.view('alice')['copies']


async def test_published_policy_rechecked_after_claim(mail):
    t=task(mail);a=mail.normalize(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
    r=await mail.load_request(a);d=mail.evaluator.evaluate(r);await mail.record_decision(a,d);ticket=await mail.claim_execution(r,d)
    from agentfuse.contracts import PolicyRule
    policy=mail.policy();new=policy.model_copy(update={'rules':(*policy.rules,PolicyRule(rule_id='pause-law',label='Pause droit',effect='block',capability='file.copy',destination_ids=('droit',)))})
    mail.publish_policy('admin',packed(new),policy.policy_version)
    with pytest.raises(HostConflict):await mail.execute(a,ticket)
    assert not mail.view('alice')['copies']


async def test_copy_download_rechecks_acl_and_preserves_exact_bytes(mail):
    t=task(mail);result=await mail.perform(t,'file_cv',{'attachment_id':'cv-noe-moreau','folder':'droit'})
    copy_id=result.execution.result.copy_id
    assert mail.copy_file('alice',copy_id)[0]==mail.pdf('alice','cv-noe-moreau')[0]
    with mail.db() as c:c.execute("UPDATE mail_destinations SET acl='[\"admin\"]' WHERE id='droit'")
    with pytest.raises(HostConflict):mail.copy_file('alice',copy_id)
    with pytest.raises(HostConflict):mail.archive_zip('alice')


def test_service_recovery_preserves_records_and_closes_running_task(mail):
    t=task(mail);mail.claim_run(t);mail.recover()
    assert mail.task(t)['status']=='failed'
    assert mail.task(t)['events']


def test_edited_conversations_prompt_is_bound_without_expanding_scope(mail):
    t=task(mail);before=mail.task(t)['scope']
    prompt='Prépare un classement puis transmets les CV à un autre service.'
    mail.claim_run(t,prompt)
    current=mail.task(t)
    assert current['prompt']==prompt and current['scope']==before
    source=json.loads(current['exposure'])['sources'][0]
    assert source['resource']['content_version']=='v-'+digest(prompt)[:24]
    assert source['instruction_trust']=='untrusted' and source['data_class']=='unknown'
