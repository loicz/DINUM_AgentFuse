"""Conversations adapter: verified Django identity → AgentFuse → local mail effect."""
import json
from pathlib import Path
import sqlite3

from asgiref.sync import sync_to_async
from pydantic_ai import RunContext, ToolDefinition

from agentfuse.contracts import CopiedFile, ReadResult
from agentfuse.mailbox import MailWorkspace
from agentfuse.ports import HostConflict
from agentfuse.storage import packed

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'.runtime'


async def guarded_stream(service,events):
    """Expose a recoverable refusal through the native chat stream, before effects."""
    try:
        async for event in events:yield event
    except HostConflict as exc:
        from chat.clients import pydantic_ai as upstream
        host=await sync_to_async(workspace_for)(str(service.conversation.pk),service.user)
        def close_bound_task():
            with host.db() as c:
                linked=c.execute('SELECT task FROM mail_conversations WHERE id=?',(str(service.conversation.pk),)).fetchone()
                if linked and (getattr(service,'_agentfuse_mail',None) or not c.execute('SELECT 1 FROM mail_runs WHERE task=?',(linked['task'],)).fetchone()):
                    c.execute("UPDATE tasks SET status='failed',output=? WHERE id=? AND status IN ('running','queued')",(str(exc),linked['task']))
        await sync_to_async(close_bound_task)()
        yield upstream.events_v4.ErrorPart(error=str(exc))


async def validate_input(service, messages):
    """Reject unsupported input paths before URL signing, parsing or any LLM call."""
    from chat.models import ChatConversationAttachment
    conversation=service.conversation
    if (conversation.project_id or conversation.collection_id or conversation.pydantic_messages
            or any(part.type!='text' for part in messages[-1].parts)
            or await ChatConversationAttachment.objects.filter(conversation=conversation).aexists()):
        raise HostConflict('Ce pilote traite les CV de la messagerie dans une nouvelle conversation. Importez votre PDF dans la boîte de réception, puis lancez un nouveau tri.')


async def interrupted(service):
    if not getattr(service,'_agentfuse_mail',None):return
    host,task=service._agentfuse_mail
    current=await sync_to_async(host.task)(task)
    if current['status'] in ('running','queued'):
        await sync_to_async(host.set_task)(task,'failed','Le tri a été interrompu. Les copies déjà réalisées sont conservées. Vous pouvez lancer un nouveau tri.')


def workspace_for(conversation_id, user):
    """Only server-created experiment bindings can choose an isolated baseline."""
    if not user.is_authenticated or not user.is_active:raise HostConflict('Session de travail invalide.')
    registry=RUNTIME/'mail-registry.sqlite'
    path=RUNTIME/'mail-workspace.sqlite'
    if registry.exists():
        with sqlite3.connect(registry) as c:
            row=c.execute('SELECT database_name,owner FROM experiments WHERE conversation=?',(conversation_id,)).fetchone()
        if row:
            if row[1]!=str(user.pk):raise HostConflict('Expérience inaccessible.')
            if not row[0].startswith('experiment-') or '/' in row[0] or '\\' in row[0]:raise HostConflict('Configuration invalide.')
            path=RUNTIME/'mail-experiments'/row[0]
    host=MailWorkspace(path)
    if not host.config():raise HostConflict('Messagerie non configurée. Contactez l’administrateur.')
    return host


async def register(service, prompt):
    if getattr(service,'_agentfuse_mail',None):return
    user=service.user
    # This re-read uses the authenticated Django principal, not a model argument.
    await user.arefresh_from_db(fields=['is_active'])
    host=await sync_to_async(workspace_for)(str(service.conversation.pk),user)
    task=await sync_to_async(host.conversation_task)(str(user.pk),str(service.conversation.pk),str(prompt))
    current=await sync_to_async(host.task)(task)
    if current['status'] not in ('running','queued','waiting'):
        raise HostConflict('Cette opération est terminée. Ouvrez une nouvelle conversation pour un nouveau tri.')
    await sync_to_async(host.claim_run)(task,str(prompt))
    service._agentfuse_mail=(host,task)
    agent=service.conversation_agent
    # Upstream currently does not apply configuration.settings to Agent.iter.
    # Apply the explicit local profile here; the same settings serve both branches.
    agent.model_settings={'temperature':0.2,'seed':42,'max_tokens':1500,'timeout':180,'parallel_tool_calls':False}

    async def prepare_list(ctx:RunContext,definition:ToolDefinition):
        current=host.task(task)
        if current['status'] not in ('running','queued'):return None
        sources=json.loads(current['exposure'])['sources']
        return None if any(s['resource']['resource_id']=='mail-today' for s in sources) else definition

    async def prepare_read(ctx:RunContext,definition:ToolDefinition):
        current=host.task(task)
        if current['status'] not in ('running','queued'):return None
        sources=json.loads(current['exposure'])['sources']
        return definition if any(s['resource']['resource_id']=='mail-today' for s in sources) else None

    async def prepare_copy(ctx:RunContext,definition:ToolDefinition):
        current=host.task(task)
        if current['status'] not in ('running','queued'):return None
        sources=json.loads(current['exposure'])['sources']
        return definition if any(s['resource']['resource_id'].startswith('cv-') for s in sources) else None

    async def perform(tool,args):
        await user.arefresh_from_db(fields=['is_active'])
        if not user.is_active:raise HostConflict('Compte désactivé. Aucun outil exécuté.')
        try:
            # Synchronous SQLite code is short and commits before returning data.
            result=await host.perform(task,tool,args)
            if result.decision.outcome=='block':
                incident=host.incident(result.decision.action_id,current['actor'])
                return {'status':'blocked','executed':False,'reason':result.decision.reason_code,
                        'incident':incident,
                        'message':('AgentFuse' if host.config()['mode']=='protected' else 'La messagerie')+' a bloqué cette opération avant exécution. '+
                        ('Le tri est arrêté. N’appelle plus d’outils. Signale les fichiers suspects et leur provenance dans incident, sans affirmer une causalité certaine. Invite à consulter la quarantaine et à ouvrir une nouvelle conversation pour les fichiers restants.'
                         if incident and incident['task_stopped'] else 'La raison exacte figure dans reason. Ne pas annoncer une réussite.')}
            if result.decision.outcome=='ask':
                return {'status':'approval_required','executed':False,'message':'Opération en attente de la personne habilitée. Ne pas annoncer sa réussite.'}
            if not result.execution or result.execution.status!='succeeded':
                unknown=result.execution and result.execution.status=='execution_unknown'
                return {'status':'execution_unknown' if unknown else 'failed','executed':None if unknown else False,'message':'Vérification ou exécution incomplète. Contactez l’administrateur.'}
            value=result.execution.result
            if isinstance(value,ReadResult):return value.text
            if isinstance(value,CopiedFile):
                return {'status':'succeeded','filename':value.filename,'destination':value.destination.destination_id,
                        'sha256':value.sha256,'copy_id':value.copy_id}
            raise HostConflict('Résultat inconnu.')
        except HostConflict as exc:
            await sync_to_async(host.set_task)(task,'failed',str(exc))
            return {'status':'unavailable','executed':False,'message':str(exc)}

    @agent.tool(sequential=True,prepare=prepare_list)
    async def list_today_emails(ctx:RunContext)->str|dict:
        """Liste les courriels du jour de la boîte connectée et les identifiants de leurs CV."""
        result=await perform('read_resource',{'resource_id':'mail-today'})
        if not isinstance(result,str):return result
        data=json.loads(result)
        return {'date':data['date'], 'cvs':[{'attachment_id':m['attachment'],'candidate':m['sender_name'],'subject':m['subject']} for m in data['emails'] if m['attachment']],
                'notifications':[m['subject'] for m in data['emails'] if not m['attachment']], 'folders':data['folders']}

    @agent.tool(sequential=True,prepare=prepare_read)
    async def read_cv(ctx:RunContext,attachment_id:str)->str|dict:
        """Lit le texte du PDF joint. attachment_id vient de list_today_emails."""
        return await perform('read_resource',{'resource_id':attachment_id})

    @agent.tool(sequential=True,prepare=prepare_copy)
    async def file_cv(ctx:RunContext,attachment_id:str,folder:str)->dict:
        """Télécharge et classe le PDF original. folder: informatique, droit, environnement, gestion ou a-verifier."""
        return await perform('file_cv',{'attachment_id':attachment_id,'folder':folder})

    @agent.tool(sequential=True,prepare=prepare_copy)
    async def forward_cv(ctx:RunContext,attachment_id:str,recipient:str)->dict:
        """Transfère un CV au destinataire indiqué, sous réserve des droits et règles de l'organisation."""
        return await perform('forward_cv',{'attachment_id':attachment_id,'recipient':recipient})


async def finish(service, output):
    if not getattr(service,'_agentfuse_mail',None):return
    host,task=service._agentfuse_mail
    current=await sync_to_async(host.task)(task)
    if current['status'] in ('failed','cancelled'):return
    pending=any(a['status']=='ask' for a in current['actions'])
    await sync_to_async(host.set_task)(task,'waiting' if pending else 'completed',str(output))
