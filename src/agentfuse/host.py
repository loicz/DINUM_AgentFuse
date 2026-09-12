"""Hôte local : faits fiables, contrôle avant effet et audit transactionnel.

Les comptes, ressources et destinations sont fournis par l’adaptateur métier.
Le cœur de politique reste indépendant de cette implémentation SQLite.
"""
import json
import time

from .contracts import (
    Action, AuthorizationSnapshot, Evidence, EvaluationRequest, ExecutionFailure,
    ExecutionSuccess, ExecutionTicket, ExposureState, Policy, ReadResource,
    ReadResult, ResourceRef, SecuritySnapshot, Source, TaskScope,
)
from .detection import SourceTracker, TextScanner
from .gate import dispatch
from .policy import PolicyEvaluator
from .ports import HostConflict
from .storage import Database, digest, packed, uid
from .wire import parse_json


class SQLiteHost(Database):
    def __init__(self, path):
        super().__init__(path)
        self.evaluator = PolicyEvaluator()
        self.scanner = TextScanner()
        self.tracker = SourceTracker()

    async def defer(self, action, decision):
        raise HostConflict('La validation humaine n’est pas intégrée à cet hôte ; opération suspendue.')

    async def resolve_approval(self, resolution, *, actor_id):
        raise HostConflict('La reprise après validation humaine n’est pas intégrée à cet hôte.')

    def user(self,user_id,c=None):
        if c is None:
            with self.db() as conn: return self.user(user_id,conn)
        row=c.execute('SELECT id,name,role,active FROM users WHERE id=?',(user_id,)).fetchone()
        if row is None or not row['active']: raise HostConflict('Compte indisponible. Contactez l’administrateur de l’application.')
        return dict(row)


    def policy(self,c=None):
        if c is None:
            with self.db() as conn: return self.policy(conn)
        row=c.execute('SELECT body FROM policies ORDER BY version DESC LIMIT 1').fetchone()
        if row is None: raise HostConflict('Politique d’organisation manquante. Contactez l’administrateur.')
        return parse_json(Policy,row['body'])


    def publish_policy(self,actor,raw,expected):
        proposed=parse_json(Policy,raw)
        with self.db() as c:
            if self.user(actor,c)['role']!='admin': raise HostConflict('Seul un administrateur peut publier la politique.')
            current=self.policy(c)
            if current.policy_version!=expected: raise HostConflict('La politique a changé. Actualisez avant de publier.')
            ids=[r.rule_id for r in proposed.rules]
            if len(set(ids))!=len(ids): raise HostConflict('Les identifiants de règles doivent être uniques.')
            self._validate_policy(c, proposed)
            n=c.execute('SELECT MAX(version) FROM policies').fetchone()[0]+1
            proposed=proposed.model_copy(update={'policy_version':f'policy-{n}'})
            c.execute('INSERT INTO policies VALUES(?,?,?,?)',(n,packed(proposed),actor,int(time.time())))
            self.event(c,None,None,'policy.published',{'version':proposed.policy_version,'author':actor})
            return proposed


    def _validate_policy(self, c, policy):
        if (policy.docs_destinations or policy.file_destinations
                or any(rule.effect == 'ask' for rule in policy.rules)):
            raise HostConflict('Cette politique requiert un adaptateur métier compatible.')

    @staticmethod
    def source(row):
        return Source(source_id=f"{row['id']}:{row['classification_version']}:{row['version']}",
            resource=ResourceRef(resource_id=row['id'],content_version=row['version']), label=row['label'],
            instruction_trust='untrusted',data_class=row['class'],classification_origin='conservative_default' if row['class']=='unknown' else 'policy')


    def start_task(self,actor,prompt,resource_ids,engine='local-model'):
        if not prompt.strip() or len(prompt)>8000: raise HostConflict('Saisissez une demande de 8 000 caractères maximum.')
        if len(resource_ids)>16: raise HostConflict('Une tâche accepte au maximum 16 ressources.')
        with self.db() as c:
            self.user(actor,c)
            self.policy(c) # Missing/invalid policy stops before model invocation.
            refs=[]
            for rid in dict.fromkeys(resource_ids):
                row=c.execute('SELECT id,version,acl FROM resources WHERE id=?',(rid,)).fetchone()
                if not row or actor not in json.loads(row['acl']): raise HostConflict('Ressource sélectionnée indisponible. Actualisez la liste.')
                refs.append(ResourceRef(resource_id=row['id'],content_version=row['version']))
            task=uid('task'); now=int(time.time())
            scope=TaskScope(task_id=task,actor_id=actor,conversation_id=task,scope_version=1,status='active',readable_resources=tuple(refs),
                docs_grants=(),created_at=now,expires_at=now+3600)
            src=Source(source_id=task+'-prompt',resource=ResourceRef(resource_id=task+'-prompt',content_version='v-'+digest(prompt)[:24]),
                label='Demande de l’utilisateur',instruction_trust='untrusted',data_class='unknown',classification_origin='conservative_default')
            scan=self.scanner.scan_text(prompt,src)
            exposure=self.tracker.observe(ExposureState(task_id=task,revision=1,sources=(),complete=True,scans_complete=True),scan)
            c.execute('INSERT INTO tasks(id,actor,prompt,scope,exposure,evidence,status,created,engine) VALUES(?,?,?,?,?,?,?,?,?)',
                (task,actor,prompt,packed(scope),packed(exposure),packed([e.model_dump(mode='json') for e in scan.findings]),'queued',now,engine))
            self.event(c,task,None,'task.started',{'selected_resources':len(refs),'engine':engine})
            return task


    @staticmethod
    def event(c,task,action,kind,body):
        c.execute('INSERT INTO events(task,action,kind,body,created) VALUES(?,?,?,?,?)',(task,action,kind,packed(body),int(time.time())))


    def normalize(self,task,tool,args,action_id=None):
        with self.db() as c:
            t=c.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
            if not t: raise HostConflict('Tâche introuvable.')
            if tool=='read_resource' and set(args)=={'resource_id'} and isinstance(args['resource_id'],str):
                row=c.execute('SELECT id,version FROM resources WHERE id=?',(args['resource_id'],)).fetchone()
                op=ReadResource(capability='resource.read',resource=ResourceRef(resource_id=args['resource_id'],content_version=row['version'] if row else 'missing'))
            else: raise HostConflict('Outil ou paramètres invérifiables. Aucune opération exécutée.')
            return Action(action_id=action_id or uid('action'),actor_id=t['actor'],task_id=task,conversation_id=task,mapping_version='pilot-v1',operation=op)


    def _request(self,c,action):
        now=int(time.time()); user=self.user(action.actor_id,c)
        t=c.execute('SELECT * FROM tasks WHERE id=?',(action.task_id,)).fetchone()
        if not t: raise HostConflict('Tâche introuvable.')
        scope=parse_json(TaskScope,t['scope']); exposure=parse_json(ExposureState,t['exposure'])
        # Metadata/versions of every exposed stored resource must remain verifiable.
        for source in exposure.sources:
            if source.source_id==action.task_id+'-prompt': continue
            row=c.execute('SELECT id,label,version,class,classification_version,acl FROM resources WHERE id=?',(source.resource.resource_id,)).fetchone()
            if row is None or self.source(row)!=source or action.actor_id not in json.loads(row['acl']):
                raise HostConflict('La version, la classification ou les droits d’une source ont changé. Relancez la tâche.')
        source,operation_acl,verdict=self._operation_facts(c,action)
        acl_basis={'user':user,'operation':operation_acl}
        if t['status'] not in ('queued','running','waiting'):
            scope=scope.model_copy(update={'status':'cancelled'})
        auth=AuthorizationSnapshot(action_id=action.action_id,actor_id=action.actor_id,task_id=action.task_id,
            permissions_version='acl-'+digest(packed(acl_basis)),verdict=verdict,checked_at=now,valid_until=now+30)
        return EvaluationRequest(schema_version='pilot-v1',action=action,resource_source=source,policy=self.policy(c),snapshot=SecuritySnapshot(scope=scope,authorization=auth,exposure=exposure,
            evidence=tuple(Evidence.model_validate_json(packed(e)) for e in json.loads(t['evidence'])),grant=None,now=now))


    def _operation_facts(self,c,action):
        """Trusted adapter metadata hook; no content access or effect here."""
        source=None; acl_basis={}; verdict='permitted'
        if isinstance(action.operation,ReadResource):
            row=c.execute('SELECT id,label,version,class,classification_version,acl FROM resources WHERE id=?',(action.operation.resource.resource_id,)).fetchone()
            if row is None: verdict='unknown'
            else:
                source=self.source(row); acl_basis['resource']=dict(row)
                if row['version']!=action.operation.resource.content_version: verdict='unknown'
                elif action.actor_id not in json.loads(row['acl']): verdict='denied'
        else: verdict='denied'
        return source,acl_basis,verdict


    async def load_request(self,action):
        with self.db() as c: return self._request(c,action)


    async def record_decision(self,action,decision):
        with self.db() as c:
            self._record_decision(c,action,decision)


    def _record_decision(self,c,action,decision):
        """Adapter hook: persist the decision and containment in one transaction."""
        old=c.execute('SELECT * FROM actions WHERE id=?',(action.action_id,)).fetchone()
        if old and (old['body']!=packed(action) or old['status'] not in ('ask',)):
            raise HostConflict('Cette opération a déjà été traitée et ne peut pas être rejouée.')
        c.execute('INSERT INTO actions(id,task,body,decision,status,binding) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET decision=excluded.decision,status=excluded.status,binding=excluded.binding',
            (action.action_id,action.task_id,packed(action),packed(decision),decision.outcome,decision.binding))
        self.event(c,action.task_id,action.action_id,'decision',decision)


    async def claim_execution(self,request,decision):
        with self.db() as c:
            current=self._request(c,request.action); checked=self.evaluator.evaluate(current)
            if checked.outcome!='allow' or checked.binding!=decision.binding: raise HostConflict('Les conditions de sécurité ont changé. Opération suspendue.')
            row=c.execute('SELECT * FROM actions WHERE id=?',(request.action.action_id,)).fetchone()
            if not row or row['status']!='allow' or row['body']!=packed(request.action): raise HostConflict('Réservation d’exécution incohérente.')
            if c.execute("SELECT 1 FROM actions WHERE task=? AND status IN ('executing','execution_unknown')",(request.action.task_id,)).fetchone(): raise HostConflict('Cette tâche comporte une exécution non résolue. Vérification nécessaire.')
            ticket=ExecutionTicket(ticket_id=uid('ticket'),action_id=request.action.action_id,binding=decision.binding)
            c.execute("UPDATE actions SET status='executing',ticket=? WHERE id=?",(ticket.ticket_id,ticket.action_id))
            self.event(c,request.action.task_id,ticket.action_id,'execution.claimed',{'binding':ticket.binding})
            return ticket


    async def execute(self,action,ticket):
        with self.db() as c:
            row=c.execute('SELECT * FROM actions WHERE id=?',(action.action_id,)).fetchone()
            if not row or row['ticket']!=ticket.ticket_id or row['binding']!=ticket.binding or row['body']!=packed(action) or row['status']!='executing' or row['result']:
                raise HostConflict('Ticket d’exécution invalide.')
            r=self._request(c,action); checked=self.evaluator.evaluate(r)
            if checked.outcome!='allow' or checked.binding!=ticket.binding: raise HostConflict('Les conditions ont changé avant l’effet.')
            result,target=self._execute_operation(c,action,r)
            c.execute('INSERT INTO effects(task,action,capability,target,created) VALUES(?,?,?,?,?)',(action.task_id,action.action_id,action.operation.capability,target,int(time.time())))
            # Effect, durable receipt, exposure and evidence commit together for this local adapter.
            self._save_result(c,row,result)
            return result


    def _execute_operation(self,c,action,request):
        """Runs only inside the transaction after ticket and current policy checks."""
        op=action.operation
        if isinstance(op,ReadResource):
            resource=c.execute('SELECT * FROM resources WHERE id=?',(op.resource.resource_id,)).fetchone()
            report=self.scanner.scan_text(resource['content'],self.source(resource))
            if report.status!='complete':
                result=ExecutionFailure(status='failed',error_code='scan.incomplete')
            else:
                result=ExecutionSuccess(status='succeeded',result=ReadResult(kind='resource.read',text=resource['content'],scan=report))
            return result,resource['id']
        raise HostConflict('Opération non prise en charge par cet hôte.')

    def _save_result(self,c,row,result):
        c.execute('UPDATE actions SET result=? WHERE id=?',(packed(result),row['id']))
        if isinstance(result,ExecutionSuccess) and isinstance(result.result,ReadResult):
            t=c.execute('SELECT * FROM tasks WHERE id=?',(row['task'],)).fetchone()
            report=result.result.scan
            state=self.tracker.observe(parse_json(ExposureState,t['exposure']),report)
            evidence={e['evidence_id']:e for e in json.loads(t['evidence'])}
            evidence.update({e.evidence_id:e.model_dump(mode='json') for e in report.findings})
            if len(evidence)>256: raise HostConflict('Capacité des preuves atteinte. Scindez la tâche.')
            c.execute('UPDATE tasks SET exposure=?,evidence=? WHERE id=?',(packed(state),packed(list(evidence.values())),row['task']))
            if report.findings: self.event(c,row['task'],row['id'],'scan.signal',{'count':len(report.findings),'source':report.source.label})


    async def record_result(self,ticket,result):
        with self.db() as c:
            row=c.execute('SELECT * FROM actions WHERE id=? AND ticket=?',(ticket.action_id,ticket.ticket_id)).fetchone()
            if not row or row['status']!='executing': raise HostConflict('Enregistrement d’exécution incohérent.')
            if row['result'] and row['result']!=packed(result): raise HostConflict('Résultat d’exécution incohérent. Vérification nécessaire.')
            if not row['result']: self._save_result(c,row,result)
            c.execute('UPDATE actions SET status=? WHERE id=?',(result.status,row['id']))
            self.event(c,row['task'],row['id'],'execution.finished',{'status':result.status})
            if result.status!='succeeded': c.execute("UPDATE tasks SET status='failed',output=? WHERE id=?",('Exécution inachevée. Consultez le journal des opérations.',row['task']))


    async def perform(self,task,tool,arguments,action_id=None):
        action=self.normalize(task,tool,arguments,action_id)
        return await dispatch(action,host=self,evaluator=self.evaluator,executor=self)


    def task(self,task,actor=None):
        with self.db() as c:
            row=c.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
            if not row or (actor is not None and row['actor']!=actor): raise HostConflict('Tâche inaccessible.')
            data=dict(row)
            data['events']=[{**dict(e),'body':json.loads(e['body'])} for e in c.execute('SELECT * FROM events WHERE task=? ORDER BY sequence',(task,))]
            data['actions']=[{**dict(a),'body':json.loads(a['body']),'decision':json.loads(a['decision'])} for a in c.execute('SELECT * FROM actions WHERE task=? ORDER BY rowid',(task,))]
            return data


    def set_task(self,task,status,output=None):
        with self.db() as c:
            c.execute('UPDATE tasks SET status=?,output=COALESCE(?,output) WHERE id=?',(status,output,task))


    def recover(self):
        with self.db() as c:
            rows=c.execute("SELECT * FROM actions WHERE status='executing'").fetchall()
            for row in rows:
                status=json.loads(row['result'])['status'] if row['result'] else 'execution_unknown'
                c.execute('UPDATE actions SET status=? WHERE id=?',(status,row['id']))
                self.event(c,row['task'],row['id'],'execution.reconciled',{'status':status})
            c.execute("UPDATE tasks SET status='failed',output='Le service a redémarré. Les effets et le journal sont conservés. Vérifiez-les avant de relancer la tâche.' WHERE status IN ('queued','running')")
