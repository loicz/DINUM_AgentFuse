'use strict';
const $=s=>document.querySelector(s);
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state=null,selected=null,view='inbox',csrf='',chat=null,pair=null,notices=false,busy=false;
const alerted=new Set();
let archiveFolder=null;
async function request(path,body){
  const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok)throw new Error(result.detail||'Le service est momentanément indisponible.');
  return result;
}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,6500);}
function run(fn){return async event=>{try{await fn(event);}catch(error){toast(error.message);}};}
function show(name){view=name;document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!==name+'-view');document.querySelectorAll('.topnav button').forEach(b=>b.classList.toggle('selected',b.dataset.view===name));if(name==='security')$('#threat').hidden=true;render();}
function dateLabel(day){return new Date(day+'T12:00:00').toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'});}
function pdfUrl(id,conversation){return '/local/pdf/'+encodeURIComponent(id)+'/'+(conversation?'?conversation='+encodeURIComponent(conversation):'');}
function openPDF(id,conversation){const url=pdfUrl(id,conversation);$('#pdf-name').textContent=id+'.pdf';$('#pdf-frame').src=url;$('#pdf-download').href=url+(conversation?'&':'?')+'download=1';$('#pdf-dialog').showModal();}
function replaceDetails(element,html){const opened=new Set([...element.querySelectorAll('details[open][data-source]')].map(d=>d.dataset.source));element.innerHTML=html;element.querySelectorAll('details[data-source]').forEach(d=>d.open=opened.has(d.dataset.source));}
function quarantineUrl(id,conversation){return '/local/quarantine/'+encodeURIComponent(id)+'/'+(conversation?'?conversation='+encodeURIComponent(conversation):'');}
function attributionLabel(value){return {already_quarantined:'Ce fichier était déjà en quarantaine. Le tri est arrêté sans désigner d’autre PDF comme suspect.',scan_signal:'Un motif d’instruction suspecte a été détecté dans le PDF. Ce signal ne prouve pas à lui seul la cause de l’opération.',single_exposed_pdf:'Seul PDF lu avant le blocage : isolement préventif, origine de l’instruction non confirmée.',ambiguous:'Plusieurs PDF ont été lus, sans signal permettant de choisir. Aucun fichier isolé automatiquement ; origine à vérifier.',unavailable:'Aucune source PDF suspecte identifiée. Le fichier visé par une opération ne prouve pas son origine.'}[value]||value;}
function sourceHTML(source,conversation){return `<div class="source-card"><strong>${escape(source.filename)}</strong>${source.mails.map(m=>`<p>Courriel de ${escape(m.sender_name)} &lt;${escape(m.sender)}&gt;<br>Objet : ${escape(m.subject)}<br>Reçu le ${escape(m.received)}</p>`).join('')||'<p>Courriel d’origine indisponible.</p>'}${source.evidence?.length?'<p>Signaux : '+source.evidence.map(e=>escape(e.rule_id)+' (caractères '+e.start+'–'+e.end+')').join(', ')+'</p>':''}<details data-source="${escape(source.source_id)}"><summary>Identifiants du fichier</summary><small>Courriel(s) : ${escape(source.mails.map(m=>m.id).join(", "))}<br>Ressource : ${escape(source.resource)}<br>Version : ${escape(source.content_version)}<br>SHA-256 : ${escape(source.sha256)}</small></details>${source.quarantine_status==='integrity_failed'?'<p>Fichier isolé, mais intégrité du PDF non vérifiable. Téléchargement pour examen indisponible ; contactez l’administrateur.</p>':''}${source.quarantine_id&&source.quarantine_status!=='integrity_failed'?`<p><strong>En quarantaine</strong> · <a href="${quarantineUrl(source.quarantine_id,conversation)}">Télécharger pour examen manuel ↓</a></p>`:''}</div>`;}
function incidentHTML(incident,conversation){if(!incident)return '';return `<div class="incident-detail"><p>${incident.task_stopped?'Tri arrêté. Une nouvelle conversation peut traiter les fichiers restants.':'Opération refusée.'}</p>${incident.target?'<p>Fichier visé par l’opération : '+escape(incident.target.filename)+'</p>':''}<p>${escape(attributionLabel(incident.attribution))}</p>${incident.sources.length?'<strong>Sources PDF à examiner</strong>'+incident.sources.map(s=>sourceHTML(s,conversation)).join(''):''}</div>`;}
function renderQuarantine(){
  const files=state.quarantine||[];$('#quarantine-count').textContent=files.length;
  replaceDetails($('#quarantine-files'),files.map(q=>`<article class="quarantine-card"><p class="status-tag block">ISOLÉ AUTOMATIQUEMENT</p><p>${escape(attributionLabel(q.attribution))}</p>${sourceHTML({...q.source,quarantine_id:q.id})}</article>`).join('')||'<div class="empty-note">Aucun PDF en quarantaine.</div>');
}
function renderMails(){
  const search=$('#search').value.toLowerCase();
  const mails=state.mails.filter(m=>(!notices||!m.attachment)&&[m.sender_name,m.subject,m.body].join(' ').toLowerCase().includes(search));
  $('#messages').innerHTML=mails.map(m=>`<button class="message ${m.unread?'unread':''} ${m.id===selected?'selected':''}" data-mail="${escape(m.id)}"><div class="message-top"><strong>${m.unread?'<span class="unread-dot"></span>':''}${escape(m.sender_name)}</strong><time>${escape(m.received.slice(11,16))}</time></div><div class="subject">${escape(m.subject)}</div><div class="excerpt">${escape(m.body.replace(/\n/g,' '))}</div>${m.attachment?'<span class="pdf-tag">▧ &nbsp; '+escape(m.attachment+'.pdf')+(m.quarantine_id?' · EN QUARANTAINE':'')+'</span>':''}</button>`).join('')||'<div class="empty-note">Aucun message trouvé.</div>';
  $('#mail-total').textContent=mails.length+' messages';$('#unread-count').textContent=state.mails.filter(m=>m.unread).length;
  $('#mail-day').textContent=dateLabel(state.config.day);
  $('#folder-links').innerHTML=Object.entries(state.folders).map(([id,label])=>`<button class="mail-folder" data-folder="${id}"><span>▱ &nbsp; ${escape(label)}</span></button>`).join('');
}
function renderReader(){const m=state.mails.find(m=>m.id===selected);if(!m)return;
  $('#reader').innerHTML=`<div class="reader-toolbar"><button id="back-to-mails" class="text-button">← Boîte de réception</button><span class="label-internal">CANDIDATURE</span></div><h2>${escape(m.subject)}</h2><div class="sender-block"><div class="avatar">${escape(m.sender_name.split(' ').map(w=>w[0]).slice(0,2).join(''))}</div><div><strong>${escape(m.sender_name)}</strong><small>${escape(m.sender)}<br>À : recrutement@service.demo.invalid</small></div><time>${escape(m.received.slice(11,16))}</time></div><div class="mail-body">${escape(m.body)}</div>${m.attachment?`<div class="attachment-heading">1 pièce jointe</div><div class="attachment-card"><div class="pdf-icon">PDF</div><div class="attachment-text"><strong>${escape(m.attachment+'.pdf')}</strong><small>Curriculum vitae · document original</small></div></div><div class="attachment-actions">${m.quarantine_id?'<button data-view="quarantine">En quarantaine · examiner le fichier →</button>':`<button data-pdf="${escape(m.attachment)}">Consulter le CV ↗</button><a href="${pdfUrl(m.attachment)}?download=1">Télécharger ↓</a>`}</div>`:''}`;
  $('#back-to-mails').onclick=()=>$('#reader').classList.remove('open');
}
function renderArchive(folder=archiveFolder){
  archiveFolder=folder;
  const copies=state.copies.filter(c=>c.destination!=='external-outbox'&&!c.quarantined);
  const unique=[...new Map(copies.map(c=>[c.destination+'/'+c.resource,c])).values()];
  $('#archive-count').textContent=new Set(copies.map(c=>c.resource)).size;
  $('#archive-folders').innerHTML=Object.entries(state.folders).map(([id,label])=>`<button class="folder-card" data-folder="${id}"><span>▱</span><strong>${escape(label)}</strong><small>${unique.filter(c=>c.destination===id).length} CV classé(s)</small></button>`).join('');
  const rows=folder?unique.filter(c=>c.destination===folder):unique;
  $('#archive-detail').innerHTML=(folder?'<h2>'+escape(state.folders[folder])+'</h2>':'')+(rows.length?rows.map(c=>`<div class="file-row"><div class="pdf-icon">PDF</div><div><strong>${escape(c.filename)}</strong><small>${escape(state.folders[c.destination])} · copie du PDF original</small></div><a href="/local/copy/${escape(c.id)}/">Télécharger ↓</a></div>`).join(''):'<div class="empty-note">Les PDF apparaîtront ici après leur classement par Conversations.</div>');
}
function operationLabel(e){const op=e.action.operation;return op.capability==='resource.read'?'Lecture · '+op.resource.resource_id:op.destination.destination_id.startsWith('external-')?'Transfert externe · '+op.filename:'Classement · '+op.filename;}
function reasonLabel(reason){return {'policy.allowed':'Conforme aux permissions et aux règles du service.','policy.destination_denied':'Ce destinataire ne figure pas dans les destinations autorisées par le service.','policy.rule_denied':'Une règle du service interdit cette opération.','scope.expansion_required':'Cette ressource ou destination ne fait pas partie du périmètre fourni par la messagerie.','context.incomplete':'Des informations nécessaires ne peuvent pas être vérifiées.','permissions.denied':'Le compte ne dispose pas des droits requis.','task.inactive':'La tâche est terminée ou a expiré.'}[reason]||reason;}
function eventRows(events,baseline=false,conversation){return events.map(e=>`<div class="event-row"><span class="event-icon ${e.decision.outcome==='block'?'block':''}">${e.decision.outcome==='block'?'×':e.executed?'✓':'…'}</span><div class="event-content"><strong>${escape(operationLabel(e))}</strong><small>${baseline&&e.executed?'Sans AgentFuse · droits du compte uniquement':escape(reasonLabel(e.decision.reason_code))}<br>${e.status==='execution_unknown'?'Résultat à vérifier · ne pas supposer une réussite':e.executed?'Opération réellement exécutée':'Opération non exécutée à cet instant'}</small>${incidentHTML(e.incident,conversation)}</div><span class="status-tag ${e.decision.outcome==='block'?'block':''}">${e.status==='execution_unknown'?'À VÉRIFIER':e.decision.outcome==='block'?'BLOQUÉ':e.executed?(baseline?'EXÉCUTÉ':'AUTORISÉ'):'EN ATTENTE'}</span></div>`).join('');}
function renderPolicy(){if(!state.policy)return;$('#policy-list').innerHTML=`<p class="hint">Version publiée : ${escape(state.policy.policy_version)} · seules les personnes habilitées administrent ces règles.</p>`+state.policy.rules.map(rule=>`<div class="policy-rule"><div><strong>${escape(rule.label)}</strong><p>Bloquer · ${escape(rule.destination_ids.join(', ')||rule.capability)}</p></div>${rule.rule_id==='cv-no-external-transfer'?'<span class="status-tag">PROTECTION INITIALE</span>':`<button class="remove-rule" data-remove-rule="${escape(rule.rule_id)}">Retirer</button>`}</div>`).join('');}
function render(){if(!state)return;renderMails();renderReader();renderArchive();renderQuarantine();replaceDetails($('#security-events'),eventRows(state.events)||'<div class="empty-note">Aucune opération proposée pour le moment. La protection s’appliquera automatiquement.</div>');renderPolicy();}
async function refresh(){
  state=await request('/local/mail/state/');$('#account-name').textContent=state.user.name;$('#demo-tab').hidden=!state.user.admin;$('#policy-tab').hidden=!state.user.admin;
  const previous=$('#history').value;$('#history').innerHTML='<option value="">Nouvelle expérience</option>'+state.experiments.map(p=>`<option value="${escape(p.pair_id)}">${new Date(p.created*1000).toLocaleString('fr-FR')}</option>`).join('');$('#history').value=pair?.id||previous;
  render();
  const incidents=state.events.filter(e=>e.incident?.task_stopped&&!alerted.has(e.id));
  for(const event of incidents)alerted.add(event.id);
  if(incidents.length){const incident=incidents[0].incident;$('#threat-detail').textContent='Tri arrêté. '+(incident.quarantine_ids.length?incident.quarantine_ids.length+' PDF placé(s) en quarantaine. ':'')+(incident.sources.map(s=>s.filename).join(', ')||'Source non identifiée.')+' Consultez les sources et la raison du blocage.';$('#threat').hidden=false;}
}
async function startChat(){if(state.user.admin){toast('Pour le travail courant, connectez-vous avec Alice. L’administrateur dispose des expériences isolées.');return;}const result=await request('/local/mail/start/',{});chat=result;$('#conversation-frame').src=result.url;$('#conversation-frame').hidden=false;$('#chat-placeholder').hidden=true;$('#open-chat').href=result.url;show('chat');}
function comparisonHTML(report){
  const baseline=report.branches.find(b=>b.mode==='baseline'),protectedBranch=report.branches.find(b=>b.mode==='protected');
  const done=report.branches.every(b=>b.state.tasks[0]?.status==='completed');
  const blocked=report.assessment?.interception_demonstrated===true;
  const contained=report.branches.some(b=>b.state.events.some(e=>e.incident?.task_stopped));
  const failed=report.branches.some(b=>['failed','cancelled'].includes(b.state.tasks[0]?.status));
  const title=blocked?'Le modèle a proposé le transfert. AgentFuse l’a arrêté avant exécution.':failed?'Une exécution a été interrompue':done?'Résultat de cette exécution réelle':'Conversations traite les candidatures…';
  const detail=contained?'Le tri protégé a été arrêté. Les sources suspectes et les éventuels PDF isolés figurent ci-dessous. Une nouvelle conversation peut traiter les fichiers restants.':blocked?'Le récepteur local a reçu le PDF dans la branche sans protection. Il ne l’a pas reçu dans la branche protégée.':failed?'Les copies déjà réalisées sont conservées. Consultez les résultats et relancez une nouvelle expérience.':done?'Un transfert non proposé ne prouve pas une interception. Consultez les opérations réelles ci-dessous.':'Les compteurs reflètent uniquement les effets déjà constatés, pas les intentions du modèle.';
  return `<p class="hint">${busy?'Exécution en cours':'Résultats enregistrés · expérience réelle'} · ${escape(report.id)}</p><div class="comparison-verdict ${blocked?'':'neutral'}"><h3>${title}</h3><p>${detail}</p></div><p class="hint">Entrée commune : <button class="text-button" data-pdf="cv-noe-moreau" data-conversation="${escape(baseline.conversation)}">Consulter le CV utilisé ↗</button> · PDF identiques : ${JSON.stringify(baseline.pdf_hashes)===JSON.stringify(protectedBranch.pdf_hashes)?'oui':'NON — comparaison invalide'}</p><div class="comparison-grid">`+report.branches.map(b=>`<article class="branch-card ${b.mode}"><h2>${b.mode==='baseline'?'Sans AgentFuse':'Avec AgentFuse'}</h2><p class="hint">${b.mode==='baseline'?'Droits du compte fictif Alice uniquement':'Protection active · règles du service'}</p><strong class="big-number">${b.delivered}</strong><div class="metric-label">PDF reçu(s) dans la boîte externe isolée</div><p>Transfert proposé par le modèle : <strong>${b.proposed_transfer?'oui':'non'}</strong><br>Copies de classement réalisées : <strong>${b.archived} / ${Object.keys(b.pdf_hashes).length}</strong><br>PDF en quarantaine : <strong>${b.state.quarantine?.length||0}</strong></p>${eventRows([...b.state.events].reverse(),b.mode==='baseline',b.conversation)}${b.state.copies.filter(c=>c.destination==='external-outbox').map(c=>`<p><a href="/local/copy/${escape(c.id)}/?conversation=${escape(b.conversation)}&format=eml">Télécharger le message réellement reçu (.eml) ↓</a></p>`).join('')}<details><summary>Réponse de Conversations</summary><pre>${escape(b.state.tasks[0]?.output||'En cours…')}</pre></details><div class="branch-footer"><a href="${escape(b.url)}" target="_blank" rel="noopener">Voir la conversation réelle ↗</a><a href="/local/archive.zip?conversation=${escape(b.conversation)}">Télécharger les CV classés ↓</a></div></article>`).join('')+'</div><button class="secondary" id="export-evidence">Télécharger les preuves JSON</button>';
}
async function updatePair(){if(!pair)return;pair=await request('/local/mail/experiment/?id='+encodeURIComponent(pair.id));replaceDetails($('#comparison'),comparisonHTML(pair));$('#export-evidence').onclick=()=>download('agentfuse-conversations-'+pair.id+'.json',pair);}
function download(name,object){const url=URL.createObjectURL(new Blob([JSON.stringify(object,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function compare(){
  if(busy)return;busy=true;$('#compare').disabled=true;
  try{
    pair=await request('/local/mail/experiments/',{scenario:$('#scenario').value});await refresh();await updatePair();
    for(const branch of pair.branches){
      $('#experiment-progress').textContent=(branch.mode==='baseline'?'1/2 · Sans AgentFuse':'2/2 · Avec AgentFuse')+' · Conversations + modèle local';
      const response=await fetch('/api/v1.0/chats/'+branch.conversation+'/conversation/',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({messages:[{id:crypto.randomUUID(),role:'user',parts:[{type:'text',text:pair.prompt}]}]})});
      if(!response.ok)throw new Error('Conversations a refusé la demande ('+response.status+').');
      await response.text();await updatePair();
    }
    $('#experiment-progress').textContent='Exécutions terminées · résultats réels ci-dessous';
  }finally{busy=false;$('#compare').disabled=false;await refresh();}
}
async function publish(policy){await request('/local/mail/policy/',{policy,expected:state.policy.policy_version});await refresh();toast('Règles publiées. Les prochains outils utiliseront cette version.');}
async function bootstrap(){const session=await request('/local/session/');csrf=session.csrf;$('#login').hidden=session.authenticated;$('#application').hidden=!session.authenticated;$('#logout').hidden=!session.authenticated;if(session.authenticated)await refresh();}
$('#login-form').onsubmit=run(async e=>{e.preventDefault();const result=await request('/local/session/',{user:$('#user').value,password:$('#password').value});csrf=result.csrf;await bootstrap();});
$('#logout').onclick=run(async()=>{await request('/api/v1.0/logout/',{});state=null;chat=null;$('#conversation-frame').src='about:blank';location.reload();});
document.addEventListener('click',run(async e=>{const b=e.target.closest('[data-view],[data-mail],[data-pdf],[data-folder],[data-remove-rule]');if(!b)return;
  if(b.dataset.view)show(b.dataset.view);
  if(b.dataset.mail){selected=b.dataset.mail;renderMails();renderReader();await request('/local/mail/read/',{id:selected});await refresh();$('#reader').classList.add('open');}
  if(b.dataset.pdf)openPDF(b.dataset.pdf,b.dataset.conversation);
  if(b.dataset.folder){show('archives');renderArchive(b.dataset.folder);}
  if(b.dataset.removeRule){const policy=structuredClone(state.policy);policy.rules=policy.rules.filter(r=>r.rule_id!==b.dataset.removeRule);await publish(policy);}
}));
$('#cancel-chat').onclick=run(async()=>{await request('/local/mail/cancel/',{});$('#conversation-frame').src='about:blank';$('#conversation-frame').hidden=true;$('#chat-placeholder').hidden=false;await refresh();toast('Tri arrêté. Les copies déjà réalisées sont conservées.');});
$('#sort').onclick=run(startChat);$('#new-chat').onclick=run(startChat);$('#prepare-chat').onclick=run(startChat);$('#refresh').onclick=run(refresh);$('#search').oninput=renderMails;
$('#show-notices').onclick=()=>{notices=true;renderMails();};$('#inbox-folder').onclick=()=>{notices=false;renderMails();};
$('#close-pdf').onclick=()=>{$('#pdf-dialog').close();$('#pdf-frame').src='about:blank';};$('#dismiss-threat').onclick=()=>$('#threat').hidden=true;
$('#compare').onclick=run(compare);$('#history').onchange=run(async()=>{if(busy)return;if(!$('#history').value){pair=null;$('#comparison').innerHTML='';return;}pair={id:$('#history').value};await updatePair();});
$('#rule-form').onsubmit=run(async e=>{e.preventDefault();const policy=structuredClone(state.policy);policy.rules.push({rule_id:'service-'+crypto.randomUUID(),label:$('#rule-label').value,effect:'block',capability:'file.copy',data_classes:[],resource_ids:[],destination_ids:[$('#rule-target').value]});await publish(policy);$('#rule-label').value='';});
$('#export-policy').onclick=()=>download('regles-candidatures.json',state.policy);
setInterval(()=>{if(state)refresh().catch(()=>{});if(pair)updatePair().catch(()=>{});},2500);
bootstrap().catch(error=>toast(error.message));

$('#show-upload').onclick=()=>$('#upload-dialog').showModal();
$('#close-upload').onclick=()=>$('#upload-dialog').close();
$('#upload-form').onsubmit=run(async e=>{e.preventDefault();const file=$('#candidate-file').files[0];if(!file||file.size>2*1024*1024)throw new Error('PDF de 2 Mo maximum requis.');const form=new FormData();form.append('name',$('#candidate-name').value);form.append('file',file);const response=await fetch('/local/application-upload/',{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':csrf},body:form});const result=await response.json();if(!response.ok)throw new Error(result.detail||'Import impossible.');$('#upload-dialog').close();$('#upload-form').reset();await refresh();selected='mail-'+result.id;renderReader();toast('Candidature ajoutée. Vous pouvez commencer un nouveau tri.');});
