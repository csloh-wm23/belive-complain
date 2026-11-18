const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token=document.querySelector('meta[name="csrf-token"]').content;
const labels={ANSWERED:'Answer accepted',AI_PENDING:'AI assistance',AWAITING_CONTACT:'Awaiting private contact',HUMAN_REVIEW:'Needs staff',IN_PROGRESS:'Staff handling',FOLLOW_UP:'Follow-up',VERIFIED:'Verified',CLOSED:'Closed',SKIPPED:'Not a support request'};
let data={cases:[],tenants:[],condos:[],examples:[],outbox:[],sources:[],audit:[],reports:{},tasks:[]}, selected=null,busy=false,authState=null,linkedCaseHandled=false;
const setText=(id,text)=>{const element=$(id);if(element)element.textContent=text;};
function notice(text,error=false){$('notice').hidden=false;$('notice').textContent=text;$('notice').className=error?'error':'';}
const connectionLostMessage='Connection lost. Keep the BeLive launcher running.';
async function request(route,p){
    const hasBody=p!==undefined;
    const options={method:hasBody?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:hasBody?JSON.stringify(p):undefined};
    if(hasBody)options.headers['Idempotency-Key']=crypto.randomUUID();
    let response=await fetch('/api/'+route,options);
    let value=await response.json();
    if(response.status===403&&value.code==='STALE_CSRF'){
        const auth=await request('auth');
        if(auth.csrf_token){
            options.headers['X-CSRF-Token']=auth.csrf_token;
            response=await fetch('/api/'+route,options);
            value=await response.json();
        }
    }
    if(!response.ok)throw Error(value.error||'Request failed');
    if(route==='auth'&&value.csrf_token)token=value.csrf_token;
    return value;
}
async function run(route,p){if(busy)throw Error('Wait for the current operation.');busy=true;const locked=[...document.querySelectorAll('button,input,textarea,select')].filter(e=>!e.disabled);locked.forEach(e=>e.disabled=true);try{const value=await request(route,p);await refresh();notice('Saved.');return value;}finally{locked.forEach(e=>e.disabled=false);busy=false;}}
function navigate(view){if(!document.querySelector(`[data-page="${CSS.escape(view)}"]`))view='overview';if(location.hash!=='#'+view)history.pushState(null,'','#'+view);document.querySelectorAll('[data-page]').forEach(e=>e.hidden=e.dataset.page!==view);document.querySelectorAll('[data-view]').forEach(e=>{e.classList.toggle('active',e.dataset.view===view);e.setAttribute('aria-current',e.dataset.view===view?'page':'false');});const names={overview:'Command center',cases:'Complaints',notifications:'Messages',sources:'Public reviews',memory:'Self-learning',settings:'AI & knowledge',database:'Data & backups',activity:'Reports & activity'};const nav=document.querySelector(`[data-view="${view}"]`);if(nav?.closest('details'))nav.closest('details').open=true;$('pageTitle').textContent=names[view];$('crumb').textContent=names[view];window.scrollTo(0,0);}
const level=c=>c.complaint_level||({LOW:'SIMPLE',MEDIUM:'MODERATE',HIGH:'HIGH',CRITICAL:'HIGH'}[c.severity]||'CHECKING');
const side=c=>['GOOGLE','FACEBOOK','THREADS','MANUAL_PUBLIC'].includes(c.platform)?'Proactive discovery':'Reactive support';
const pill=value=>`<span class="pill ${String(value).toLowerCase()}">${esc(labels[value]||value)}</span>`;
function rows(cases){return cases.map(c=>`<tr><td><button class="case-link" data-case="${c.id}">${esc(c.title)}</button><small>${esc(side(c))} · ${esc(c.id)} · ${esc(c.tenant_id||'Unverified tenant')} · ${esc(c.category)}${c.entrypoint==='TENANT_WEBSITE'?' · BeLive website':''}</small></td><td>${pill(level(c))}</td><td>${pill(c.status)}${staffAlert(c)?`<small>${esc(alertReason(c))}</small>`:''}</td><td>${esc(c.owner||(c.automatic_answer&&!c.handoff?'AI routine support':'Unassigned'))}</td><td>${esc(c.next_action||labels[c.status])}<small class="${c.overdue?'error':''}">${c.due_at?esc(new Date(c.due_at).toLocaleString())+(c.overdue?' · OVERDUE':''):'No deadline recorded'}</small></td></tr>`).join('')||'<tr><td colspan="5" class="empty">No complaints yet. Add one manually, wait for a tenant request, or configure an authorised public source.</td></tr>';}
const complaintQueues={
    staff:c=>c.status==='HUMAN_REVIEW',
    working:c=>c.status==='IN_PROGRESS',
    followup:c=>['FOLLOW_UP','VERIFIED'].includes(c.status),
    closed:c=>['CLOSED','SKIPPED','ANSWERED'].includes(c.status),
    all:()=>true
};
let complaintQueue='all';
const assignedToMe = c => Boolean(c.owner) && (c.owner_id ? c.owner_id===data.operator.id : c.owner===data.operator.name);
const staffAlert = c => !complaintQueues.closed(c) && (c.overdue || ['HIGH','CRITICAL'].includes(c.severity) || (c.status==='HUMAN_REVIEW'&&!c.owner));
const alertReason = c => [c.severity==='CRITICAL'?'Immediate safety risk':c.severity==='HIGH'?'High urgency':'',c.overdue?'Overdue':'',!c.owner?'Unassigned':''].filter(Boolean).join(' · ');
$('staffAlerts').onclick=()=>{
    complaintQueue='all';
    $('search').value='';$('statusFilter').value='';$('queueFilter').value='ALERTS';$('queueFilter').closest('details').open=true;
    navigate('cases');renderCases();
};
function renderCases(){
    const query=$('search').value.trim().toLowerCase(),status=$('statusFilter').value,focus=$('queueFilter').value;
    const matches=data.cases.filter(c=>complaintQueues[complaintQueue](c)&&(!status||c.status===status)
        &&(!focus||(focus==='MINE'?assignedToMe(c):focus==='ALERTS'?staffAlert(c):focus==='OVERDUE'?c.overdue:focus==='UNASSIGNED'?!c.owner&&!complaintQueues.closed(c):['HIGH','CRITICAL'].includes(c.severity)))
        &&[c.title,c.description,c.tenant_id,c.id,c.reported_location?.property,c.reported_location?.unit,c.reported_location?.address].join(' ').toLowerCase().includes(query));
    const priority=c=>c.severity==='CRITICAL'?0:c.severity==='HIGH'?1:c.overdue?2:3;
    matches.sort((a,b)=>priority(a)-priority(b) || (data.operator.role==='SUPPORT' ? Number(assignedToMe(b))-Number(assignedToMe(a)) : 0));
    $('caseRows').innerHTML=matches.length?rows(matches):'<tr><td colspan="5" class="empty">No matching complaints. Choose All or clear your filters.</td></tr>';
    document.querySelectorAll('[data-complaint-queue]').forEach(button=>{
        const queue=button.dataset.complaintQueue;
        button.setAttribute('aria-pressed',String(queue===complaintQueue));
        button.querySelector('span').textContent=data.cases.filter(complaintQueues[queue]).length;
    });
}
function renderDiscoveries(){
    const platformNames={GOOGLE:'Google Reviews',FACEBOOK:'Facebook',THREADS:'Threads'};
    const matches=data.cases.filter(c=>Object.hasOwn(platformNames,c.platform)&&c.status!=='SKIPPED');
    const filter=$('discoveryPlatform');
    const showFilter=new Set(matches.map(c=>c.platform)).size>1;
    filter.closest('label').hidden=!showFilter;
    if(!showFilter)filter.value='';
    const selectedPlatform=filter.value;
    const signature=c=>c.description.trim().replace(/\s+/g,' ').toLowerCase();
    const platformsByText=new Map();
    for(const c of matches){
        const key=signature(c);
        if(!platformsByText.has(key))platformsByText.set(key,new Set());
        platformsByText.get(key).add(c.platform);
    }
    $('discoveryFindings').innerHTML=matches.filter(c=>!selectedPlatform||c.platform===selectedPlatform).map(c=>{
        const duplicates=platformsByText.get(signature(c));
        return `<article class="record-card"><div class="card-heading"><strong>${esc(platformNames[c.platform])}</strong>${pill(c.status)}</div>
            <button class="case-link" data-case="${esc(c.id)}">${esc(c.title)} · ${esc(c.id)}</button>
            <p>${esc(c.description)}</p><small>Source: ${esc(c.source_id)} · Found ${esc(new Date(c.created_at).toLocaleString())}</small>
            ${c.public_url?`<p><a href="${esc(c.public_url)}" target="_blank" rel="noopener noreferrer">Open original source ↗</a></p>`:''}
            ${duplicates.size>1?'<p>Possible cross-platform duplicate: identical text was found on another platform.</p>':''}</article>`;
    }).join('')||'<p>No matching discoveries yet.</p>';
    const sources=data.sources.filter(s=>s.enabled);
    const tasks=new Set(data.tasks||[]);
    const running=sources.some(source=>tasks.has('source-'+source.id));
    $('scanAllSources').disabled=running||!sources.length;
    $('scanAllSources').textContent=running?'Collecting…':'Collect reviews now';
    $('scanSummary').textContent=sources.length
        ? `${sources.length} enabled source(s). Scheduled checks every ${data.source_interval_minutes} min while BeLive is running.`
        : 'An administrator needs to connect an authorised Google Reviews, Facebook or Threads source first.';
    const scanErrors={CONNECTOR_NOT_CONFIGURED:'API token missing',FACEBOOK_VERSION_REQUIRED:'Facebook API version missing',
        CONNECTOR_READ_FAILED:'Platform read failed. Check API access, token and source ID.'};
    $('scanResults').hidden=!sources.length;
    $('scanResults').innerHTML=sources.map(source=>{
        const result=tasks.has('source-'+source.id)?'Reading recent items…'
            :source.error?scanErrors[source.error]||'Platform read failed'
            :source.last_scan?`${source.last_count??0} items checked · ${new Date(source.last_scan).toLocaleString()}`
            :'Waiting for the first check';
        return `<li><strong>${esc(platformNames[source.platform])}</strong> · ${esc(result)}</li>`;
    }).join('');
    if(document.activeElement!==$('scanInterval'))$('scanInterval').value=data.source_interval_minutes;
}
document.querySelector('[data-page="cases"]').addEventListener('click',event=>{
    const button=event.target.closest('[data-complaint-queue]');
    if(!button)return;
    complaintQueue=button.dataset.complaintQueue;
    $('statusFilter').value='';
    $('queueFilter').value='';
    renderCases();
});
function menus(){for(const [selector,items,label] of [['.tenant-select',data.tenants,t=>t.id+' · '+t.unit_ref],['.condo-select',data.condos,c=>c.name+' · '+c.id]])document.querySelectorAll(selector).forEach(select=>{const before=select.value;select.innerHTML='<option value="">Choose a record…</option>'+items.map(x=>`<option value="${esc(x.id)}">${esc(label(x))}</option>`).join('');select.value=before;});}
function render(){window.dispatchEvent(new CustomEvent('belive:status',{detail:data}));$('operatorName').textContent=data.operator.name+' · '+data.operator.role;document.querySelectorAll('[data-admin]').forEach(e=>e.hidden=data.operator.role!=='ADMIN');menus();renderCases();$('recentCases').innerHTML=rows(data.cases.slice(0,5));const needs=data.cases.filter(staffAlert);$('staffAlertCount').textContent=needs.length;$('navCount').textContent=data.cases.filter(c=>!['CLOSED','SKIPPED','ANSWERED'].includes(c.status)).length;
$('aiStatus').textContent=data.readiness?.ai?'AI configured':'AI setup required · staff fallback';
$('metrics').innerHTML=[['Open complaints',data.cases.filter(c=>!['CLOSED','SKIPPED','ANSWERED'].includes(c.status)).length,'cases'],['Need staff',data.cases.filter(c=>c.status==='HUMAN_REVIEW').length,'cases'],['Overdue follow-ups',data.reports.overdue||0,'cases'],['Messages to review',data.outbox.filter(m=>m.status==='PENDING_APPROVAL').length,'notifications']].map(([label,n,view])=>`<button class="metric" data-go="${view}"><span>${label}</span><strong>${n}</strong><small>Open workspace →</small></button>`).join('');
const proactivePlatforms=new Set(['GOOGLE','FACEBOOK','THREADS','MANUAL_PUBLIC']);
const proactiveCases=data.cases.filter(c=>proactivePlatforms.has(c.platform));
const reactiveCases=data.cases.filter(c=>!proactivePlatforms.has(c.platform));
const activeSources=data.sources.filter(s=>s.enabled).length;
setText('proactiveSummary',`${activeSources} monitored source${activeSources===1?'':'s'} · ${proactiveCases.length} discovered case${proactiveCases.length===1?'':'s'}`);
setText('reactiveSummary',`${reactiveCases.length} tenant or staff-submitted case${reactiveCases.length===1?'':'s'} · ${data.tenants.length} verified tenant${data.tenants.length===1?'':'s'}`);
setText('learningCount',String(data.examples.length));
setText('learningSummary',data.examples.length?`${data.public_lesson_count||0} available for public replies. Open Self-learning to see which cases matched them.`:'Close a verified case and review its outcome before the system learns from it.');
$('attention').innerHTML=needs.slice(0,3).map(c=>`<div class="attention-item"><small>${esc(c.id)} · ${esc(alertReason(c))}</small><h3>${esc(c.title)}</h3><p>${esc(c.review_reason)}</p><button data-case="${c.id}">Review case →</button></div>`).join('')||'<p class="empty">No cases currently awaiting staff.</p>';
$('outboxList').innerHTML=data.outbox.map(m=>`<article class="record-card"><div class="card-heading"><strong>${esc(m.kind)} · ${esc(m.target)}</strong>${pill(m.status)}</div><p class="source-text">${esc(m.text)}</p><small>${esc(m.entity)} · ${esc(m.id)}</small><p class="muted">${esc(m.outcome||'No delivery confirmed')}</p><div class="case-actions">${m.status==='PENDING_APPROVAL'?`<button data-approve="${m.id}">Approve this exact message</button><button data-reject="${m.id}">Reject</button>`:''}${m.status==='APPROVED'?`<button class="primary" data-deliver="${m.id}">Deliver approved message</button>`:''}</div></article>`).join('')||'<p class="empty">No queued notifications.</p>';
$('sourcesList').innerHTML=data.sources.map(s=>`<section class="card"><div class="card-heading"><h2>${esc(s.platform)} · ${esc(s.resource)}</h2>${pill(s.enabled?'MONITORING':'PAUSED')}</div><p>${esc(s.status)} · ${esc(s.error||'No reported error')} · Last read: ${esc(s.last_scan||'Never')}${s.enabled?` · Next check: ${esc(new Date(s.next_scan).toLocaleString())}`:''}</p>${s.enabled&&data.operator.role==='ADMIN'?`<button data-scan="${s.id}">Check recent posts</button>`:''}<button data-admin data-toggle-source="${s.id}">${s.enabled?'Pause checks':'Resume checks'}</button></section>`).join('')||'<section class="card empty">No source configured. Nothing is collected automatically.</section>';
renderDiscoveries();
$('memoryExamples').innerHTML=data.examples.map(f=>`<section class="card example-card">
    <div class="card-heading"><strong>${f.public_active?'Public auto-reply active':f.public_question?'Outside the current public lesson set':'Writing example'}</strong><button class="text-button" data-case="${esc(f.case_id)}">Source case ${esc(f.case_id)} ↗</button></div>
    ${f.public_question?`<p><b>Matches:</b> ${esc(f.public_question)}</p>`:''}
    <blockquote>${esc(f.text)}</blockquote>
    ${f.public_active?`<p>Matched cases: <strong>${f.matched_cases}</strong></p>`:''}
    ${f.latest_match?`<button class="text-button" data-case="${esc(f.latest_match)}">Latest match ${esc(f.latest_match)} ↗</button>`:''}
    ${f.share?'<p>Shared via authenticated API</p>':''}
    <div class="case-actions"><button class="danger" data-revoke="${esc(f.case_id)}">Reject & revoke reuse</button></div></section>`).join('')||'<section class="card empty">No reviewed lessons yet. Open a completed complaint and use Teach future replies to add one.</section>';
renderKnowledge();renderAdmin();
$('resources').innerHTML=`<p>${data.condos.length} properties · ${data.tenants.length} verified tenants · ${data.records?.length||0} verified support records</p>`+data.condos.map(c=>`<p><b>${esc(c.id)}</b> — ${esc(c.name)} · ${esc(c.needs_review?'Re-enter verified support guidance':c.rules)}</p>`).join('');
const outcomes=data.reports.reply_outcomes||{};
const unchanged=outcomes.ai_drafts_sent
    ? `${outcomes.ai_drafts_unchanged} of ${outcomes.ai_drafts_sent} (${Math.round(100*outcomes.ai_drafts_unchanged/outcomes.ai_drafts_sent)}%)`
    : 'No reviewed AI drafts sent yet';
$('reports').innerHTML=`<h3>Complaint outcomes</h3><ul><li>Staff replies sent: ${outcomes.staff_replies||0}</li><li>AI drafts sent without edits: ${unchanged}</li><li>Distinct cases reopened after a reply: ${outcomes.reopened_after_reply||0}</li></ul><p class="muted">Counts start with this update. Reopened cases had previously been answered, verified or closed. Writing clarity scores are shown separately in Self-learning.</p><p>Human handovers: <b>${data.reports.human_handoffs||0}</b> · Verified closures: <b>${data.reports.verified_closures||0}</b></p><div class="report-bars">${Object.entries(data.reports.categories||{}).map(([k,n])=>`<div><span>${esc(k.replaceAll('_',' '))}</span><meter min="0" max="${Math.max(1,data.cases.length)}" value="${n}"></meter><b>${n}</b></div>`).join('')}</div>`;
renderDatabase();document.querySelectorAll('[data-admin]').forEach(e=>e.hidden=data.operator.role!=='ADMIN');
$('activityList').innerHTML=data.audit.map(a=>`<div class="activity-item"><span class="activity-dot">·</span><div><small>${esc(a.entity)}</small><br><strong>${esc(a.action)}</strong><p>${esc(a.detail)}</p></div><time>${esc(new Date(a.created_at).toLocaleString())}</time></div>`).join('')||'<p class="empty">No activity recorded.</p>';
}
function renderDatabase(){
const storage=data.storage||{};$('chooseDatabase').disabled=!storage.can_choose;
$('databaseLocation').innerHTML=`<p class="source-text"><b>Current file</b><br>${esc(storage.active||'Unavailable')}</p>${storage.restart_required?`<div class="verification"><b>Selected for next launch</b><p class="source-text">${esc(storage.selected)}</p><p>Restart the app to open the selected database. The current file is still in use.</p></div>`:''}`;
const query=$('recordSearch').value.toLowerCase();
const groups=[['Properties',['Reference','Name','Verified support guidance'],data.condos.map(c=>[c.id,c.name,c.needs_review?'Re-enter verified support guidance':c.rules])],['Tenants',['Reference','Property / unit','Verified by','Evidence reference'],data.tenants.map(t=>[t.id,t.condo_id+' / '+t.unit_ref,t.verified_by,t.evidence])],['Support context',['Reference','Tenant','Source reference','Verified context'],(data.records||[]).map(r=>[r.id,r.tenant_id,r.source,r.text])]];
$('databaseRecordCount').textContent=`${data.condos.length} properties · ${data.tenants.length} verified tenants · ${(data.records||[]).length} support records`;
$('databaseRecords').innerHTML=groups.map(([name,columns,items])=>{const visible=items.filter(row=>row.join(' ').toLowerCase().includes(query));return `<section class="saved-record-group"><h3>${name} <small>${visible.length} of ${items.length}</small></h3><div class="table-scroll"><table class="record-table"><thead><tr>${columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${visible.map(row=>`<tr>${row.map(cell=>`<td>${esc(cell)}</td>`).join('')}</tr>`).join('')||`<tr><td colspan="${columns.length}" class="empty">No matching records.</td></tr>`}</tbody></table></div></section>`;}).join('');
}
async function refresh(watchedCase){
    const snapshot=await request('status');
    if(snapshot.operator.role==='ADMIN')snapshot.users=(await request('users')).users;
    if(watchedCase && (busy||caseEdited||!$('caseDialog').open||selected!==watchedCase.id))return;
    const pending=assessmentPending(watchedCase);
    data=snapshot;
    render();
    if(watchedCase){
        const current=data.cases.find(c=>c.id===watchedCase.id);
        if(current && (current.revision!==watchedCase.revision || assessmentPending(current)!==pending)){
            renderDetail($('caseAssessment').open);
        }
    }
    if($('notice').textContent===connectionLostMessage){
        $('notice').textContent='';
        $('notice').hidden=true;
    }
}
function openLinkedCase(){
    const id=new URLSearchParams(location.search).get('case');
    if(!id||linkedCaseHandled)return;
    linkedCaseHandled=true;navigate('cases');
    if(data.cases.some(c=>c.id===id))openCase(id);
    else notice('That case is not available in this workspace.',true);
}
let caseEdited=false;
$('caseDetail').addEventListener('input',()=>{caseEdited=true;});
function openCase(id){selected=id;renderDetail();$('caseDialog').showModal();}
function assessmentPending(c,snapshot=data){
    return c && ((snapshot.tasks||[]).includes('ai-'+c.id) ||
        (!c.analysis&&!['HIGH','CRITICAL'].includes(c.severity)&&
            (['AI_PENDING','AWAITING_CONTACT'].includes(c.status)||c.ai_assistance_pending)));
}
function complaintNextStep(c){
    if(c.status==='FOLLOW_UP')return c.tenant_resolution?.resolved
        ?'The customer confirmed the issue is resolved. Record the outcome, check the confirmation, then close the complaint.'
        :'Wait for the customer to confirm the outcome. Reply here if they have questions.';
    const steps={
        HUMAN_REVIEW:'Read the conversation, then choose Take ownership to handle this complaint.',
        IN_PROGRESS:'Send a reply below. When the work is done, record the outcome and choose Mark handled · ask customer to confirm.',
        VERIFIED:'Review the outcome and outstanding work, then close the case.',
        CLOSED:c.closure_reason==='CUSTOMER_INACTIVE'?'Closed because the customer did not reply. Resolution was not confirmed. The customer can reopen with the same Complaint Code.':'Save reusable guidance under Teach future replies if this complaint has a useful lesson.',
        AI_PENDING:'AI is checking the complaint. Acknowledge it if staff needs to take over.',
        AWAITING_CONTACT:'Review the source and check whether the customer has contacted BeLive.',
        ANSWERED:'The customer accepted the informational answer.',
        SKIPPED:'This case was marked outside the support queue.'
    };
    return steps[c.status]||'Review the conversation and the latest case activity.';
}
function renderDetail(keepAssessmentOpen=false){
const c=data.cases.find(c=>c.id===selected);if(!c)return;
caseEdited=false;
const active=!['CLOSED','SKIPPED','ANSWERED'].includes(c.status);
const checking=assessmentPending(c);
const publicSource=!c.tenant_id&&c.entrypoint==='PUBLIC_SOURCE'&&['GOOGLE','FACEBOOK','THREADS'].includes(c.platform);
const preview=c.public_reply_preview?.source_version===c.source_versions.at(-1)?c.public_reply_preview:null;
const canPreview=active&&c.status!=='VERIFIED'&&c.analysis?.report_type==='COMPLAINT'
    &&c.analysis.relevance==='SUPPORT'&&!c.analysis.uncertainty;
const urgencyReason=c.severity==='CRITICAL'?'Immediate safety concern. Staff handles this case directly.'
    :c.severity==='HIGH'?'AI flagged this for urgent review. Staff confirms the urgency and decides how to respond.'
    :c.severity==='MEDIUM'?'The issue needs staff investigation or action.'
    :c.severity==='LOW'?'Routine issue. Approved guidance may be used when all reply checks pass.':'Awaiting severity assessment.';
let actions='';
if(['AI_PENDING','AWAITING_CONTACT','HUMAN_REVIEW'].includes(c.status))actions+='<button class="primary" data-act="acknowledge">Take ownership</button>';
if(c.status==='FOLLOW_UP'&&c.automatic_answer&&!c.owner)actions+='<button data-act="acknowledge">Take ownership</button>';
if(c.status==='IN_PROGRESS')actions+='<button class="primary" data-act="followup">Mark handled · ask customer to confirm</button>';
if(c.status==='FOLLOW_UP'&&(c.tenant_resolution?.resolved||c.tenant_id))actions+='<label><input id="caseResolutionConfirmed" type="checkbox"> I checked the customer confirmation and resolution evidence.</label><button class="primary" data-act="verify_close">Close complaint</button>';
if(c.status==='VERIFIED')actions+='<button class="primary" data-act="close">Close complaint</button>';
if(!active)actions+='<button data-act="reopen">Reopen for staff</button>';
$('caseDetail').innerHTML=`<div class="dialog-heading"><div><span class="eyebrow">${esc(c.id)}</span><h2>${esc(c.title)}</h2></div><button data-close="caseDialog" aria-label="Close case">×</button></div>
<div class="case-tags">${pill(c.status)}${pill(level(c))}${pill(c.category)}</div><p>${esc(urgencyReason)}</p>${c.staff_destination?`<p><strong>Assigned team</strong> ${esc(c.staff_destination)}</p>`:''}
<section class="case-next-step"><h3>Next step</h3><p>${esc(complaintNextStep(c))}</p></section>
${c.public_url?`<p><a href="${esc(c.public_url)}" target="_blank" rel="noopener noreferrer">Open original ${esc(c.platform)} source ↗</a></p>`:''}
${c.entrypoint==='TENANT_WEBSITE'? `<section class="case-section"><h3>Reported rental location</h3><p>${c.reported_location ? esc([c.reported_location.property,c.reported_location.unit].filter(Boolean).join(' · ')) : 'Location was not provided.'}</p>${c.reported_location?.address?`<p>${esc(c.reported_location.address)}</p>`:''}</section>` : ''}
<section class="case-section"><h3>Conversation</h3>${chat(c.conversation)}<p class="muted">Only published messages are shown to the tenant.</p></section>
<details class="case-section" id="caseAssessment" ${publicSource||checking||keepAssessmentOpen?'open':''}><summary>AI assessment</summary>
${checking?'<p role="status">Assessment is running in the background. This case updates automatically.</p>':''}
<p><b>Message:</b> ${esc(c.analysis?.report_type==='COMPLAINT'?'Complaint':c.analysis?.report_type==='ENQUIRY'?'Support question':c.analysis?.report_type==='NON_SUPPORT'?'Not a support request':'Awaiting check')} · <b>Staff destination:</b> ${esc(c.staff_destination||data.routing?.departments?.[c.category]||'Support team')}</p>
${agentTrace(c)}
${c.analysis?`<p>${esc(c.analysis.summary)}</p><p><b>AI suggestion:</b> ${esc(c.analysis.plan||'Staff handling required')}</p><p class="muted">Reviewed lessons provided to the reply agent: ${c.analysis.learning_used?.count||0}</p>`:checking?'':'<p>No AI assessment recorded.</p>'}
${c.review_reason?`<p class="verification">${esc(c.review_reason)}</p>`:''}
${!checking&&active&&!['HIGH','CRITICAL'].includes(c.severity)&&!['FOLLOW_UP','VERIFIED'].includes(c.status)?`<button data-analyse="${c.id}">Retry assessment</button>`:''}
</details>
${publicSource?`<section class="case-section"><h3>Public reply preview</h3>
       <p class="muted">For staff review before any reply on the source platform.</p>
       ${preview?`<p class="source-text">${esc(preview.text)}</p><small>Generated by ${esc(preview.agent)}</small>`
         :c.draft?`<p class="source-text">${esc(c.draft)}</p><small>${c.public_guidance_prepared?'Approved SIMPLE guidance · saved as a draft':'Current suggested wording'}</small>`:''}
       ${canPreview?`<div class="case-actions"><button class="primary" data-public-preview="${esc(c.id)}">${preview?'Regenerate preview':'Generate tailored preview'}</button></div>`:''}
     </section>`:`<section class="case-section"><h3>Reply to customer</h3>${c.conversation?.length? `<div class="muted"><strong>Latest customer message</strong><p>${esc([...c.conversation].reverse().find(m=>['TENANT','REPORTED_ISSUE'].includes(m.sender))?.text||'')}</p></div>`:''}${c.automatic_answer?'<p class="verification">Hermes has replied automatically. Staff can take ownership if further help is needed.</p>':'<p>Review or edit the reply, then send it directly to the customer’s Complaint Code conversation.</p>'}<label>Reply<textarea id="caseDraft" maxlength="2500" ${!active?'readonly':''}>${esc(c.draft)}</textarea></label>${active?'<label><input id="caseConfirmed" type="checkbox"> I reviewed this reply.</label><div class="case-actions"><button class="primary" data-act="send_reply">Send reply</button></div>':''}</section>`}
<section class="case-section" data-handling><h3>Case progress</h3>${c.tenant_resolution?`<p>Customer feedback: ${c.tenant_resolution.resolved?'Confirmed resolved':'Still unresolved'}</p><p>${esc(c.tenant_resolution.note)}</p>`:''}
<p class="muted">${c.owner?'Handled by '+esc(c.owner):'No staff owner yet.'}</p><label>Internal note / work completed<textarea id="caseNote" maxlength="2000" placeholder="Describe the work or evidence (at least 8 characters). This note is private; use Send reply to update the customer."></textarea></label>
<div class="case-actions">${actions}</div>
${c.status==='FOLLOW_UP'&&!c.tenant_resolution?.resolved?'<p class="muted">Waiting for the customer. They can open Track complaint with their Complaint Code and choose Issue resolved or Still unresolved.</p>':''}
${c.auto_close_at?`<p class="muted">No reply by ${esc(new Date(c.auto_close_at).toLocaleString())}: closes automatically with an unconfirmed outcome. The customer can reopen later.</p>`:''}
${c.verification?`<p class="verification">Resolution evidence: ${esc(c.verification)}</p>`:''}
</section>
<details class="case-section" data-more><summary>More options · internal notes and classification</summary><button id="reloadCase">Refresh case</button>
${active?`<div class="form-grid"><label>Category<select id="staffCategory">${Object.keys(data.reports.categories).map(k=>`<option value="${k}" ${k===c.category?'selected':''}>${esc(k.replaceAll('_',' '))}</option>`).join('')}</select></label><label>Complaint level<select id="staffSeverity">${['LOW','MEDIUM','HIGH','CRITICAL'].map(k=>`<option value="${k}" ${k===c.severity?'selected':''}>${k==='LOW'?'SIMPLE':k==='MEDIUM'?'MODERATE':k==='CRITICAL'?'HIGH — immediate danger':'HIGH'}</option>`).join('')}</select></label></div><button data-act="assess">Save staff assessment</button>`:''}
<div class="case-actions"><button data-act="plan" ${!active?'disabled':''}>Save next action</button><button data-act="note">Add private note</button></div>
<p class="muted">These actions use the internal note above.</p><label>Next-action deadline (optional)<input id="caseDue" type="datetime-local" value="${localDateTime(c.action_due)}" ${!active?'disabled':''}></label>
${c.status==='FOLLOW_UP'?'<button data-act="reassess">Return to Needs staff</button>':''}
${(data.workorders||[]).filter(w=>w.case_id===c.id).map(w=>`<p>${esc(w.department)} · ${esc(w.description)} · ${esc(w.status)} ${w.status==='OPEN'?`<button data-workorder="${w.id}">Record completion</button>`:''}</p>`).join('')}
</details>
${c.status==='CLOSED'&&c.closure_reason!=='CUSTOMER_INACTIVE'?'<section class="case-section"><h3>Teach future replies</h3><label>Reply as the customer should see it<textarea id="correctedExample" maxlength="2000" placeholder="Write directly to the customer. For example: Please tell us when the connection drops."></textarea></label><label>General question this answers (for public reuse)<input id="publicLessonQuestion" maxlength="240"></label><label><input id="publishPublicLesson" type="checkbox"> I reviewed this as general guidance safe for any customer. It contains no private, property-specific or account information.</label><label><input id="shareExample" type="checkbox"> Allow this style example through the protected shared-memory API</label><div class="case-actions"><button data-feedback="APPROVED">Use saved wording as a lesson</button><button data-feedback="CORRECTED">Save corrected lesson</button><button data-feedback="REJECTED">Reject lesson</button></div></section>':''}
<details class="case-section"><summary>Source evidence and activity</summary><p>${esc(c.description)}</p><p>Platform ${esc(c.platform)} · Saved versions ${esc(c.source_versions.join(', '))}</p>${c.public_url?`<p><a href="${esc(c.public_url)}" target="_blank" rel="noopener noreferrer">Open original listing ↗</a></p>`:''}${c.analysis?`<p>Exact source quote: ${esc(c.analysis.evidence)}</p>`:''}${(c.analysis?.record_refs||[]).map(r=>`<p><b>${esc(r.id)} · v${r.version}</b> ${esc(r.source)}<br>${esc(r.text)}</p>`).join('')}${(c.activity||[]).map(a=>`<p><b>${esc(a.action)}</b> · ${esc(new Date(a.created_at).toLocaleString())}<br>${esc(a.detail)}</p>`).join('')}</details><p id="caseError" role="alert" class="error"></p>`;}


function formData(form){const p=Object.fromEntries(new FormData(form));form.querySelectorAll('[type="checkbox"]').forEach(e=>p[e.name]=e.checked);return p;}
function bindForm(id,route,convert=p=>p){$(id).onsubmit=async e=>{e.preventDefault();try{const value=await run(route,convert(formData(e.target)));if(id==='intakeForm'){$('intakeDialog').close();openCase(value.id);}else e.target.reset();}catch(err){const el=e.target.querySelector('.form-error');if(el)el.textContent=err.message;notice(err.message,true);}};}
bindForm('intakeForm','intake');bindForm('tenantForm','tenant');bindForm('recordForm','record');bindForm('sourceForm','source',p=>({...p,enabled:true}));bindForm('condoForm','condo');
$('discoveryPlatform').onchange=renderDiscoveries;
$('sourceScheduleForm').onsubmit=async event=>{
    event.preventDefault();
    try{await run('source_schedule',{minutes:Number($('scanInterval').value)});}
    catch(error){notice(error.message,true);}
};
$('scanAllSources').onclick=async()=>{
    const button=$('scanAllSources');
    button.disabled=true;
    button.textContent='Collecting…';
    try{
        await request('scan-all',{});
        await refresh();
    }catch(error){
        renderDiscoveries();
        notice(error.message,true);
    }
};
const publicComplaintForm=$('publicComplaintForm');
if(publicComplaintForm)publicComplaintForm.onsubmit=async event=>{
    event.preventDefault();
    const error=publicComplaintForm.querySelector('.form-error');
    error.textContent='';
    try{
        const result=await run('intake',formData(publicComplaintForm));
        publicComplaintForm.reset();
        navigate('cases');
        openCase(result.id);
    }catch(err){error.textContent=err.message;}
};
for(const [key,value] of Object.entries(labels))$('statusFilter').insertAdjacentHTML('beforeend',`<option value="${key}">${value}</option>`);
$('newCase').onclick=()=>{$('intakeForm').reset();$('intakeDialog').showModal();};$('search').oninput=renderCases;$('statusFilter').onchange=renderCases;$('queueFilter').onchange=renderCases;
$('recordSearch').oninput=renderDatabase;
$('chooseDatabase').onclick=()=>run('select-database',{}).then(r=>notice(r.cancelled?'Database selection cancelled.':r.restart_required?'Database selected for next launch. Restart the app when ready; current records remain in the current file.':'The current database is selected.')).catch(e=>notice(e.message,true));
$('refresh').onclick=()=>refresh().catch(e=>notice(e.message,true));$('tick').onclick=()=>run('tick',{}).catch(e=>notice(e.message,true));$('syncMemory').onclick=()=>run('memory-sync',{}).then(r=>notice(`${r.entries} current example(s) loaded into native Hermes memory.`)).catch(e=>notice(e.message,true));
$('portalIssue').onclick=()=>{$('utilityContent').innerHTML=`<div class="dialog-heading"><h2>Issue verified tenant access</h2><button data-close="utilityDialog">×</button></div><p class="muted">This is optional and is not needed to submit a complaint. Use it only after identity verification when a tenant needs access to their full private history.</p><select id="portalTenant">${data.tenants.map(t=>`<option value="${esc(t.id)}">${esc(t.id)}</option>`).join('')}</select><button id="issueKey">Issue seven-day tenant access</button><button id="revokePortal">Revoke all tenant access keys</button><p id="portalKey" class="source-text"></p>`;$('utilityDialog').showModal();$('issueKey').onclick=async()=>{try{const r=await run('portal_issue',{tenant_id:$('portalTenant').value});$('portalKey').textContent='Verified tenant access (share through an authorised private channel): '+r.token;}catch(e){$('portalKey').textContent=e.message;}};};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='belive-tenant-support.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.close){$(b.dataset.close).close();return;}if(b.dataset.view||b.dataset.go){navigate(b.dataset.view||b.dataset.go);return;}if(b.dataset.case){openCase(b.dataset.case);return;}
try{
if(b.id==='reloadCase'){await run('status');renderDetail($('caseAssessment').open);}
if(b.id==='revokePortal'){await run('portal_revoke',{tenant_id:$('portalTenant').value,confirmed:true});$('portalKey').textContent='All portal access keys for this tenant have been revoked.';}
if(b.dataset.act){const more=!!b.closest('[data-more]');const c=data.cases.find(c=>c.id===selected);await run('case_action',{id:c.id,revision:c.revision,action:b.dataset.act,note:b.dataset.act==='draft'?$('caseDraft').value:$('caseNote').value,reviewed_reply:['send_reply','publish_response'].includes(b.dataset.act)?$('caseDraft').value:undefined,owner:data.operator.name,category:$('staffCategory')?.value,severity:$('staffSeverity')?.value,due_at:$('caseDue').value?new Date($('caseDue').value).toISOString():null,confirmed:b.dataset.act==='verify_close'?$('caseResolutionConfirmed')?.checked??false:$('caseConfirmed')?.checked??false});renderDetail();if(more)document.querySelector('#caseDetail [data-more]').open=true;}
if(b.dataset.workorder){const c=data.cases.find(c=>c.id===selected);await run('case_action',{id:c.id,revision:c.revision,action:'complete_workorder',workorder_id:b.dataset.workorder,note:$('caseNote').value});renderDetail();}
if(b.dataset.feedback){await run('feedback',{id:selected,verdict:b.dataset.feedback,text:$('correctedExample').value,share:$('shareExample').checked,publish_public:$('publishPublicLesson').checked,public_question:$('publicLessonQuestion').value});renderDetail();}
if(b.dataset.revoke)await run('feedback',{id:b.dataset.revoke,verdict:'REJECTED'});
if(b.dataset.publicPreview){
    const c=data.cases.find(item=>item.id===b.dataset.publicPreview);
    const buttonLabel=b.textContent;
    b.textContent='Preparing preview…';
    try{await run('public-preview',{id:c.id,revision:c.revision});}
    finally{b.textContent=buttonLabel;}
    renderDetail();
    notice('Public reply preview saved.');
}
if(b.dataset.analyse){await run('analyse',{id:b.dataset.analyse});renderDetail(true);}
if(b.dataset.approve)await run('approve_message',{id:b.dataset.approve});if(b.dataset.reject)await run('reject_message',{id:b.dataset.reject});
if(b.dataset.deliver){const r=await run('deliver',{id:b.dataset.deliver});notice('Delivery outcome: '+r.status,r.status!=='DELIVERED');}
if(b.dataset.scan)await run('scan',{id:b.dataset.scan});
if(b.dataset.toggleSource){const s=data.sources.find(x=>x.id===b.dataset.toggleSource);await run('source',{...s,enabled:!s.enabled});}
}catch(err){if($('caseDialog').open&&$('caseError'))$('caseError').textContent=err.message;notice(err.message,true);}});
document.querySelector('.brand').onclick=e=>{e.preventDefault();navigate('overview');};
boot().catch(e=>{$('authGate').hidden=false;$('authError').textContent='Cannot connect to the BeLive server: '+e.message;});
let polling=false;
setInterval(async()=>{
    if(!authState?.user||busy||polling||document.querySelector('input:focus,textarea:focus,select:focus'))return;
    const dialog=document.querySelector('dialog[open]');
    const current=data.cases.find(c=>c.id===selected);
    if(dialog && (dialog.id!=='caseDialog'||caseEdited||!assessmentPending(current)))return;
    polling=true;
    try{await refresh(dialog?current:undefined);}
    catch{
        try{await boot();}
        catch(error){notice(error instanceof TypeError?connectionLostMessage:error.message,true);}
    }finally{polling=false;}
},5000);

function chat(messages){return `<div class="conversation">${(messages||[]).map(m=>`<article class="chat-message ${['SUPPORT','AI_SUPPORT'].includes(m.sender)?'support':''}"><small>${esc(m.sender.replaceAll('_',' '))} · ${esc(new Date(m.at).toLocaleString())}</small><p>${esc(m.text)}</p></article>`).join('')||'<p>No published messages yet.</p>'}</div>`;}
function renderAdmin(){
const health=(data.health||[]).find(x=>x.id==='ai');$('aiCheckStatus').innerHTML=`<p>${esc(data.readiness.provider||'Configured provider')} · ${esc(data.readiness.model||'No model configured')}</p><p>${health?esc(health.status+' · '+(health.detail||'Checking provider')+' · '+new Date(health.at).toLocaleString()):'No real-provider connection check has been recorded.'}</p>`;
$('usersList').innerHTML=(data.users||[]).map(u=>`<p><b>${esc(u.name)}</b> · ${esc(u.id)} · ${esc(u.role)} · ${u.active?'Active':'Inactive'} ${u.active&&u.id!==data.operator.id?`<button data-deactivate="${esc(u.id)}">Deactivate account</button>`:''}</p>`).join('');
$('backupsList').innerHTML=(data.backups||[]).map(b=>`<article class="record-card"><b>${esc(new Date(b.at).toLocaleString())}</b> · ${esc(b.bytes)} bytes<p class="source-text">${esc(b.path)}</p><button data-recover="${b.id}">Recover into a separate workspace</button></article>`).join('')||'<p>No verified backups recorded for this database.</p>';
$('recordManagement').innerHTML=(data.records||[]).map(r=>`<article class="record-card"><b>${esc(r.source)}</b> · ${esc(r.id)} · v${r.version||1} · ${r.active===false?'Inactive':r.expires_at&&r.expires_at<new Date().toISOString()?'Expired':'Active'}<p>${esc(r.text)}</p><button data-record="${r.id}">Correct, deactivate or view versions</button></article>`).join('')||'<p>No verified support context recorded.</p>';
}
async function boot(){authState=await request('auth');if(!authState.user)document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('operatorApp').hidden=!authState.user;$('authGate').hidden=!!authState.user;$('authNameLabel').hidden=!authState.setup_required;$('authName').required=authState.setup_required;$('authTitle').textContent=authState.setup_required?'Create the first administrator':'Operator sign-in';$('authIntro').textContent=authState.setup_required?'Choose your own admin credentials for this database. There is no default password.':'Sign in with your staff or administrator account.';$('authSubmit').textContent=authState.setup_required?'Create admin & open dashboard':'Sign in';if(authState.user){await refresh();navigate(location.hash.slice(1)||'overview');openLinkedCase();}}
$('authForm').onsubmit=async e=>{e.preventDefault();$('authSubmit').disabled=true;try{await request(authState.setup_required?'setup':'login',formData(e.target));$('authPassword').value='';await boot();}catch(err){$('authError').textContent=err.message;}finally{$('authSubmit').disabled=false;}};
$('signOut').onclick=()=>request('logout',{}).then(()=>location.reload()).catch(e=>notice(e.message,true));
$('userForm').onsubmit=async e=>{e.preventDefault();try{await run('users',formData(e.target));e.target.reset();}catch(err){notice(err.message,true);}};
$('checkAi').onclick=()=>run('ai-check',{}).then(()=>notice('Real-provider connection check started. Refresh to see its outcome.')).catch(e=>notice(e.message,true));
$('createBackup').onclick=()=>run('backup',{}).then(()=>notice('Verified SQLite backup created.')).catch(e=>notice(e.message,true));
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{
if(b.dataset.deactivate)await run('deactivate-user',{id:b.dataset.deactivate});
if(b.dataset.recover){const id=b.dataset.recover;$('utilityContent').innerHTML=`<div class="dialog-heading"><h2>Recover a backup</h2><button data-close="utilityDialog">×</button></div><p>A new database copy will be selected for the next launch. Sources will be paused, pending notifications held and existing access sessions revoked. Support guidance and reusable examples will need fresh review. Review recovered cases before resuming work.</p><label><input id="confirmRecovery" type="checkbox"> I understand that recovery opens a separate workspace after restart</label><button id="recoverNow">Create recovered copy</button><p id="recoveryError" class="error"></p>`;$('utilityDialog').showModal();$('recoverNow').onclick=async()=>{try{await run('restore',{id,confirmed:$('confirmRecovery').checked});$('utilityDialog').close();notice('Recovered copy created for next launch. The current database remains in place.');}catch(err){$('recoveryError').textContent=err.message;}};}
if(b.dataset.record){const r=data.records.find(x=>x.id===b.dataset.record);$('utilityContent').innerHTML=`<div class="dialog-heading"><h2>Support record · v${r.version||1}</h2><button data-close="utilityDialog">×</button></div><label>Source reference<input id="recordSource" value="${esc(r.source)}"></label><label>Verified context<textarea id="recordText">${esc(r.text)}</textarea></label><label>Correction / deactivation reason<textarea id="recordReason"></textarea></label><label>Optional expiry (local time)<input id="recordExpiry" type="datetime-local" value="${localDateTime(r.expires_at)}"></label><label><input id="recordConfirmed" type="checkbox"> I checked the corrected facts against their source</label><button id="correctRecord">Save corrected version</button><button id="deactivateRecord">Deactivate from AI context</button><p id="recordError" class="error"></p><h3>Immutable versions</h3>${(r.history||[]).map(v=>`<p><b>v${v.version||1}</b> · ${esc(v.source)}<br>${esc(v.text)}</p>`).join('')}`;$('utilityDialog').showModal();const save=async action=>{try{await run('record_update',{id:r.id,version:r.version||1,action,source:$('recordSource').value,text:$('recordText').value,reason:$('recordReason').value,confirmed:$('recordConfirmed').checked,expires_at:$('recordExpiry').value?new Date($('recordExpiry').value).toISOString():null});$('utilityDialog').close();}catch(err){$('recordError').textContent=err.message;}};$('correctRecord').onclick=()=>save('CORRECT');$('deactivateRecord').onclick=()=>save('DEACTIVATE');}
}catch(err){notice(err.message,true);}});

function localDateTime(value){if(!value)return '';const d=new Date(value);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}


function renderKnowledge(){
 if($('closureDays')&&document.activeElement!==$('closureDays'))$('closureDays').value=data.closure_policy?.days||7;
 if($('closureStatus'))$('closureStatus').textContent=`Waiting for customer reply: ${data.closure_policy?.days||7} days. No-reply closures do not become learning examples.`;
 const enabled=!!data.automation?.enabled;
 const answers=data.answers||[];
 const active=answers.filter(a=>a.active&&a.verified&&(!a.expires_at||a.expires_at>new Date().toISOString()));
 $('routineSummary').textContent=(enabled?'On: SIMPLE replies are automatic. MODERATE drafts go to staff after AI assessment.':'Off: AI prepares drafts for staff review.')+' '+active.length+' active knowledge entries. '+(data.reports.accepted_answers||0)+' informational answers accepted.';
 $('automationStatus').textContent=enabled?'Routine automation is on. Staff handles exceptions.':'Routine automation is off. Add approved knowledge, then enable it when ready.';
 $('toggleAutomation').textContent=enabled?'Pause routine automation':'Enable routine automation';
 $('knowledgeList').innerHTML=answers.map(a=>`<article class="record-card"><div class="card-heading"><strong>${esc(a.question)}</strong><span>${esc(a.condo_id)} · ${esc(a.language)} · ${a.kind==='GUIDANCE'?'Guidance':'Exact reply'} · v${a.version} · ${a.active&&(!a.expires_at||a.expires_at>new Date().toISOString())?'Active':'Inactive / expired'}</span></div><p class="source-text">${esc(a.answer)}</p><small>${esc(a.source)}</small><div class="case-actions"><button data-edit-answer="${a.id}">Edit knowledge</button>${a.active?`<button data-deactivate-answer="${a.id}">Deactivate</button>`:''}</div></article>`).join('')||'<p>No approved knowledge yet. Add verified company information here. The app does not invent company rules.</p>';
}
$('toggleAutomation').onclick=()=>run('automation_settings',{enabled:!data.automation?.enabled}).then(()=>notice(data.automation.enabled?'Routine automatic replies enabled for new private tenant requests.':'Routine automatic replies paused.')).catch(e=>notice(e.message,true));
$('closureForm').onsubmit=async e=>{e.preventDefault();try{await run('closure_settings',{days:Number($('closureDays').value)});notice('Customer waiting period saved.');}catch(err){notice(err.message,true);}};
$('newKnowledge').onclick=()=>{$('knowledgeForm').reset();$('knowledgeForm').elements.id.value='';$('knowledgeForm').elements.version.value='';};
$('knowledgeForm').onsubmit=async e=>{e.preventDefault();const p=formData(e.target);if(p.version)p.version=Number(p.version);if(!p.id)delete p.id;p.expires_at=p.expires_at?new Date(p.expires_at).toISOString():null;try{await run('answer',p);$('newKnowledge').click();notice('Approved knowledge saved. The AI can use this version for the selected property.');}catch(err){notice(err.message,true);}};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const id=b.dataset.editAnswer||b.dataset.deactivateAnswer;if(!id)return;const a=data.answers.find(x=>x.id===id);try{if(b.dataset.deactivateAnswer){await run('answer_deactivate',{id:a.id,version:a.version});return;}const f=$('knowledgeForm');for(const key of ['id','version','condo_id','question','category','language','answer','source'])f.elements[key].value=a[key];f.elements.kind.value=a.kind||'EXACT';f.elements.expires_at.value=localDateTime(a.expires_at);f.elements.confirmed.checked=false;f.scrollIntoView({block:'start'});f.elements.question.focus();}catch(err){notice(err.message,true);}});

function agentTrace(c){
 const trace=c.analysis?.agent_trace||data.jobs.find(j=>j.case_id===c.id)?.agent_trace||[];
 return trace.length?'<ol class="agent-trace">'+trace.map(step=>`<li><strong>${esc(step.agent)}</strong><span>${esc(step.status==='COMPLETED'?'Finished':step.status==='FAILED'?'Needs review':'Working')}</span></li>`).join('')+'</ol>':'<p class="muted">The analysis and response agents will appear here after a run. Safety cases may stop before response generation.</p>';
}
window.addEventListener('belive:refresh',()=>refresh().catch(error=>notice(error.message,true)));

window.addEventListener('popstate',()=>navigate(location.hash.slice(1)||'overview'));
$('caseDialog').addEventListener('close',()=>{
    selected=null;
    const url=new URL(location.href);
    if(url.searchParams.has('case')){url.searchParams.delete('case');history.replaceState(null,'',url);}
});
