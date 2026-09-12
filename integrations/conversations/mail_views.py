"""Local mail UI API, authenticated by the real Django session and CSRF middleware."""
import json
from pathlib import Path
import secrets
import sqlite3
import time
import hashlib
from urllib.parse import urlencode

from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from agentfuse.mailbox import MailWorkspace, PROMPT
from agentfuse.ports import HostConflict
from agentfuse.contracts import Policy, PolicyRule
from agentfuse.storage import packed
from mail_tools import RUNTIME, ROOT, workspace_for


def actor_for(user):
    with MailWorkspace(RUNTIME/'mail-workspace.sqlite').db() as c:
        row=c.execute('SELECT actor FROM mail_identity WHERE external_id=?',(str(user.pk),)).fetchone()
    if not row:raise HostConflict('Compte sans connexion de messagerie.')
    return row['actor']


def main_host():
    return MailWorkspace(RUNTIME/'mail-workspace.sqlite')


def registry():
    db=sqlite3.connect(RUNTIME/'mail-registry.sqlite')
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS experiments(conversation TEXT PRIMARY KEY,database_name TEXT UNIQUE,owner TEXT,pair_id TEXT,mode TEXT,created INTEGER)')
    db.execute('CREATE TABLE IF NOT EXISTS experiment_metadata(pair_id TEXT PRIMARY KEY,body TEXT)')
    db.commit()
    return db


def page(request,asset='index.html'):
    allowed={'index.html':'text/html','mail.css':'text/css','mail.js':'text/javascript','NotoSansSC.ttf':'font/ttf'}
    if asset not in allowed:return HttpResponse(status=404)
    path=ROOT/'src/agentfuse'/('assets' if asset=='NotoSansSC.ttf' else 'mail_web')/asset
    response=FileResponse(path.open('rb'),content_type=allowed[asset])
    response['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' http://127.0.0.1:3000; frame-src 'self' http://127.0.0.1:3000; object-src 'none'; base-uri 'none'; form-action 'self'"
    response['Cache-Control']='no-store'
    return response


def new_conversation(user,host,prompt):
    from chat.models import ChatConversation
    conversation=ChatConversation.objects.create(owner=user,title='Candidatures du jour')
    task=host.conversation_task(str(user.pk),str(conversation.pk),prompt)
    return {'conversation':str(conversation.pk),'task':task,
            'url':'http://127.0.0.1:3000/chat/'+str(conversation.pk)+'?'+urlencode({'mail_prompt':prompt})}


@require_http_methods(['GET','POST'])
def api(request,action):
    if not request.user.is_authenticated:return JsonResponse({'detail':'Connectez-vous à votre messagerie.'},status=401)
    try:
        actor=actor_for(request.user);host=main_host()
        body={}
        if request.method=='POST':
            if len(request.body)>262144:return JsonResponse({'detail':'Requête trop volumineuse.'},status=413)
            body=json.loads(request.body or '{}')
            if not isinstance(body,dict):raise HostConflict('Entrée invalide.')
        if action=='state' and request.method=='GET':
            # Admin can inspect the shared fictional mailbox, not impersonate a tool user.
            state=host.view('alice' if actor=='admin' else actor)
            state['user']={'name':request.user.full_name,'actor':actor,'admin':request.user.is_staff}
            state['policy']=host.policy().model_dump(mode='json') if request.user.is_staff else None
            with registry() as c:
                pairs=[dict(r) for r in c.execute('SELECT pair_id,MIN(created) AS created FROM experiments WHERE owner=? GROUP BY pair_id ORDER BY created DESC',(str(request.user.pk),))]
            state['experiments']=pairs
            return JsonResponse(state)
        if action=='read' and request.method=='POST':
            with host.db() as c:
                count=c.execute('UPDATE mails SET unread=0 WHERE id=? AND owner=?',(body.get('id'),'alice' if actor=='admin' else actor)).rowcount
                if not count:raise HostConflict('Courriel inaccessible.')
            return JsonResponse({'ok':True})
        if action=='start' and request.method=='POST':
            if actor!='alice':raise HostConflict('Connectez-vous avec Alice pour utiliser la boîte de recrutement.')
            prompt=body.get('prompt',PROMPT)
            if not isinstance(prompt,str) or not 1<=len(prompt)<=8000:raise HostConflict('Demande invalide.')
            return JsonResponse(new_conversation(request.user,host,prompt))
        if action=='cancel' and request.method=='POST':
            return JsonResponse({'cancelled':host.cancel_tasks(actor)})
        if action=='experiments' and request.method=='POST':
            if not request.user.is_staff:return JsonResponse({'detail':'Réservé à l’administrateur de la démo.'},status=403)
            scenario=body.get('scenario','attack')
            if scenario not in ('clean','attack'):raise HostConflict('Scénario invalide.')
            pair='pair-'+secrets.token_hex(8);branches=[]
            for mode in ('baseline','protected'):
                name='experiment-'+secrets.token_hex(12)+'.sqlite'
                isolated=MailWorkspace(RUNTIME/'mail-experiments'/name)
                isolated.initialize(scenario=scenario,baseline=mode=='baseline')
                # An explicitly fictional Alice persona in both isolated branches.
                isolated.bind_identity(str(request.user.pk),'alice')
                conversation=new_conversation(request.user,isolated,PROMPT)
                with registry() as c:c.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?)',
                    (conversation['conversation'],name,str(request.user.pk),pair,mode,int(time.time())))
                branches.append(dict(conversation,mode=mode))
            from mail_evidence import configuration_snapshot
            with registry() as c:c.execute('INSERT INTO experiment_metadata VALUES(?,?)',(pair,packed(configuration_snapshot(scenario))))
            return JsonResponse({'id':pair,'branches':branches,'prompt':PROMPT})
        if action=='experiment' and request.method=='GET':
            pair=request.GET.get('id','')
            with registry() as c:rows=c.execute('SELECT * FROM experiments WHERE pair_id=? AND owner=? ORDER BY mode',(pair,str(request.user.pk))).fetchall()
            if not rows:raise HostConflict('Expérience inaccessible.')
            branches=[]
            for row in rows:
                isolated=workspace_for(row['conversation'],request.user)
                state=isolated.view('alice')
                copies=state['copies'];events=state['events']
                proposals=[e for e in events if e['action']['operation'].get('destination',{}).get('destination_id')=='external-outbox']
                # Frozen input hashes remain available after containment; this
                # report does not reopen quarantined PDFs through the normal API.
                with isolated.db() as c:
                    pdf_hashes=dict(c.execute('SELECT resource,sha256 FROM pdfs').fetchall())
                trace=isolated.task(state['tasks'][0]['id'])
                forward_calls=[e for e in trace['events'] if e['kind']=='tool.proposed' and e['body']['tool']=='forward_cv']
                scans=[e['result']['result']['scan'] for e in events if e['result'] and e['result'].get('status')=='succeeded' and e['result']['result'].get('kind')=='resource.read']
                branches.append({'mode':row['mode'],'conversation':row['conversation'],'state':state,
                                 'url':'http://127.0.0.1:3000/chat/'+row['conversation']+'?'+urlencode({'mail_prompt':PROMPT}),
                                 'proposed_transfer':bool(forward_calls),'normalized_transfer':bool(proposals),'delivered':sum(c['destination']=='external-outbox' for c in copies),
                                 'archived':len({c['resource'] for c in copies if c['destination']!='external-outbox'}),
                                 'blocked_transfer':any(e['decision']['outcome']=='block' and not e['executed'] for e in proposals),
                                 'scans':scans,'audit':trace['events'],'scope':json.loads(trace['scope']),
                                 'pdf_hashes':pdf_hashes})
            with registry() as c:metadata=c.execute('SELECT body FROM experiment_metadata WHERE pair_id=?',(pair,)).fetchone()
            from mail_evidence import assess
            report={'id':pair,'branches':branches,'prompt':PROMPT,'evidence':'real-conversations-local-model','configuration':json.loads(metadata['body']) if metadata else None}
            report['assessment']=assess(report)
            return JsonResponse(report)
        if action=='policy' and request.method=='POST':
            if not request.user.is_staff:return JsonResponse({'detail':'Administration requise.'},status=403)
            policy=Policy.model_validate_json(packed(body.get('policy')))
            if any(rule.effect=='ask' for rule in policy.rules):raise HostConflict('Ce pilote courrier propose des règles de blocage ; la reprise après validation humaine n’est pas intégrée.')
            if any(g.destination.destination_id=='external-outbox' for g in policy.file_destinations):raise HostConflict('Ce pilote ne permet pas de publier une destination externe.')
            host.publish_policy('admin',packed(policy),body.get('expected'))
            return JsonResponse({'ok':True})
        return JsonResponse({'detail':'Opération inconnue.'},status=404)
    except (HostConflict,ValueError,TypeError,KeyError) as exc:
        return JsonResponse({'detail':str(exc) if isinstance(exc,HostConflict) else 'Requête invalide.'},status=409)


@require_http_methods(['GET'])
def attachment(request,resource):
    if not request.user.is_authenticated:return HttpResponse(status=401)
    try:
        host=main_host();actor=actor_for(request.user)
        conversation=request.GET.get('conversation')
        if conversation:
            host=workspace_for(conversation,request.user)
            with host.db() as c:
                linked=c.execute('SELECT actor FROM mail_identity WHERE external_id=?',(str(request.user.pk),)).fetchone()
                if not linked:raise HostConflict('Pièce jointe inaccessible.')
                actor=linked['actor']
        data,filename=host.pdf(actor,resource)
        response=HttpResponse(data,content_type='application/pdf')
        response['Content-Disposition']=('attachment' if request.GET.get('download') else 'inline')+'; filename="'+filename+'"'
        response['Cache-Control']='no-store'
        if not request.GET.get('download'):
            # The mailbox embeds this authorized PDF in a same-origin iframe.
            # Keep Django's default DENY for downloads and all other responses.
            response['X-Frame-Options']='SAMEORIGIN'
        return response
    except HostConflict as exc:return JsonResponse({'detail':str(exc)},status=403)


@require_http_methods(['GET'])
def quarantine_download(request,quarantine_id):
    if not request.user.is_authenticated:return HttpResponse(status=401)
    try:
        actor=actor_for(request.user);host=main_host()
        if request.GET.get('conversation'):
            host=workspace_for(request.GET['conversation'],request.user)
            with host.db() as c:
                identity=c.execute('SELECT actor FROM mail_identity WHERE external_id=?',(str(request.user.pk),)).fetchone()
                if not identity:raise HostConflict('Fichier inaccessible.')
                actor=identity['actor']
        data,name=host.quarantine_file(actor,quarantine_id)
        response=HttpResponse(data,content_type='application/pdf')
        response['Content-Disposition']='attachment; filename="'+name+'"'
        response['Cache-Control']='no-store'
        return response
    except HostConflict as exc:return JsonResponse({'detail':str(exc)},status=403)


@require_http_methods(['GET'])
def archive(request):
    if not request.user.is_authenticated:return HttpResponse(status=401)
    try:
        actor=actor_for(request.user);host=main_host()
        conversation=request.GET.get('conversation')
        if conversation:
            host=workspace_for(conversation,request.user)
            with host.db() as c:actor=c.execute('SELECT actor FROM mail_identity WHERE external_id=?',(str(request.user.pk),)).fetchone()['actor']
        data=host.archive_zip(actor)
        response=HttpResponse(data,content_type='application/zip');response['Content-Disposition']='attachment; filename="candidatures-classees.zip"'
        return response
    except HostConflict as exc:return JsonResponse({'detail':str(exc)},status=403)


@require_http_methods(['GET'])
def copy_download(request,copy_id):
    if not request.user.is_authenticated:return HttpResponse(status=401)
    try:
        actor=actor_for(request.user);host=main_host()
        if request.GET.get('conversation'):
            host=workspace_for(request.GET['conversation'],request.user)
            with host.db() as c:actor=c.execute('SELECT actor FROM mail_identity WHERE external_id=?',(str(request.user.pk),)).fetchone()['actor']
        data,name,content_type=host.copy_file(actor,copy_id,request.GET.get('format')=='eml')
        response=HttpResponse(data,content_type=content_type)
        response['Content-Disposition']='attachment; filename="'+name+'"'
        response['Cache-Control']='no-store'
        return response
    except HostConflict as exc:return JsonResponse({'detail':str(exc)},status=403)


@require_http_methods(['POST'])
def upload(request):
    if not request.user.is_authenticated:return JsonResponse({'detail':'Connexion requise.'},status=401)
    if int(request.META.get('CONTENT_LENGTH') or 0)>2*1024*1024+8192:return JsonResponse({'detail':'PDF de 2 Mo maximum.'},status=413)
    file=request.FILES.get('file')
    if not file or file.size>2*1024*1024:return JsonResponse({'detail':'PDF de 2 Mo maximum requis.'},status=422)
    try:
        resource=main_host().add_application(actor_for(request.user),request.POST.get('name',''),file.read())
        return JsonResponse({'id':resource})
    except HostConflict as exc:return JsonResponse({'detail':str(exc)},status=409)
