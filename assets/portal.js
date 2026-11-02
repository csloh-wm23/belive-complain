const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let key='',busy=false,cases=new Map(),selectedCase=null,currentView='report';
const drafts=new Map(),notices=new Map(),attempts=new Map();
const topicTitles={wifi:'Wi-Fi support request',maintenance:'Repairs and maintenance',cleaning:'Cleaning concern',access:'Room or building access',utilities:'Water or utilities enquiry',billing:'Billing or other enquiry'};
const selectedTopic=new URLSearchParams(location.search).get('topic');
if(topicTitles[selectedTopic])$('tenantIntake').elements.title.value=topicTitles[selectedTopic];

function closeRecords(){
    key='';selectedCase=null;drafts.clear();notices.clear();attempts.clear();cases.clear();
    $('tenantArea').hidden=true;$('tenantCases').replaceChildren();$('requestList').replaceChildren();$('tenantIdentity').textContent='';
    $('portalAccessCard').hidden=false;$('portalSignOut').hidden=true;$('accessKey').value='';
}

function showView(view){
    currentView=view;
    $('report').hidden=view!=='report';$('conversations').hidden=view!=='conversations';
    document.querySelectorAll('[data-portal-view]').forEach(button=>{
        const active=button.dataset.portalView===view;
        button.classList.toggle('active',active);button.setAttribute('aria-current',active?'page':'false');
    });
}
function renderRequests(){
    $('requestCount').textContent=cases.size?'('+cases.size+')':'';
    $('requestList').hidden=!!selectedCase;$('allRequests').hidden=!selectedCase;
    $('conversationHeading').textContent=selectedCase?'Your conversation':'My requests';
    $('requestList').innerHTML=[...cases.values()].map(c=>`<button class="portal-request-row" data-open-request="${esc(c.id)}"><span><strong>${esc(c.title)}</strong><small>${esc(status(c)[0])}</small></span><span>${esc(c.complaint_level||'CHECKING')} →</span></button>`).join('')||'<p>No requests yet. Choose New request to get started.</p>';
    $('tenantCases').innerHTML=selectedCase&&cases.has(selectedCase)?renderCase(cases.get(selectedCase)):'';
}
function openDestination(){
    const requested=new URLSearchParams(location.search).get('case');
    if(requested&&cases.has(requested))selectedCase=requested;
    showView(selectedCase||location.hash==='#conversations'?'conversations':'report');renderRequests();
    const target=selectedCase?document.getElementById('portal-case-'+selectedCase):$(currentView);
    target?.scrollIntoView({block:'start'});
}

async function request(route,p,requestId){
    let response;
    try{
        response=await fetch('/api/portal'+route,{method:p?'POST':'GET',headers:{
            'Authorization':'Bearer '+key,'Content-Type':'application/json',
            'Idempotency-Key':requestId||crypto.randomUUID()
        },body:p?JSON.stringify(p):undefined});
    }catch(error){
        if(error instanceof TypeError)throw Error(p?'Could not confirm your update. Your text is kept. Try the same action again.':'Could not load your conversations. Please try Refresh conversations.');
        throw error;
    }
    const result=await response.json();
    if(!response.ok){
        if(response.status===401)closeRecords();
        throw Error(result.error||'Request failed');
    }
    return result;
}

async function send(action,route,payload){
    const signature=JSON.stringify(payload);
    let attempt=attempts.get(action);
    // A lost receipt can follow a committed update. Retry the same action with its original key.
    if(!attempt||attempt.signature!==signature){
        attempt={signature,id:crypto.randomUUID()};attempts.set(action,attempt);
    }
    const result=await request(route,payload,attempt.id);
    attempts.delete(action);
    return result;
}

function status(c){
    if(c.automatic_pending)return ['AI is reviewing your request','Your message was received. SIMPLE requests can receive an automatic reply.'];
    if(c.ai_assistance_pending)return ['AI is preparing help for staff','Your request is already in the staff queue. AI is checking the details and preparing a draft for the team.'];
    if(c.ai_draft_ready)return ['AI draft ready for staff review','AI has assessed this request and prepared guidance. The support team will review it before sending a reply.'];
    const states={
        HUMAN_REVIEW:['Waiting for the support team','Your request is in the staff queue. AI replies are paused while the team reviews it. You can add more details below.'],
        IN_PROGRESS:['Support team is handling your request','Your messages are saved in this conversation for the support team.'],
        FOLLOW_UP:['Waiting for your feedback',c.informational_answer?'AI has replied below. You can send a follow-up, accept the answer, or choose Still unresolved to ask the support team to take over.':'Check the support reply below. Tell the team whether the issue is resolved or still needs attention.'],
        ANSWERED:['Answer accepted','You accepted the information. If the problem remains, choose Still unresolved to ask the support team to take over.'],
        VERIFIED:['Outcome checked by support','The support team has recorded an outcome check. You can report if the issue remains unresolved.'],
        CLOSED:['Request closed','The support team closed this request after checking the outcome. Choose Still unresolved if you need it reviewed again.'],
        SKIPPED:['Request marked outside support','Choose Still unresolved if you need the support team to review this decision.'],
        AWAITING_CONTACT:['Tenant verification needed','The support team needs to verify tenancy before providing personal assistance.']
    };
    return states[c.status]||['Request received','Your request is saved for support review. New replies will appear here.'];
}

function renderCase(c){
    const [label,explanation]=status(c),notice=notices.get(c.id);
    const active=!['CLOSED','SKIPPED','ANSWERED'].includes(c.status);
    return `<article class="record-card" id="portal-case-${esc(c.id)}">
        <h3 tabindex="-1">${esc(c.title)}</h3><p class="muted">Request ${esc(c.id)} <span class="pill ${String(c.complaint_level||'CHECKING').toLowerCase()}">${esc(c.complaint_level||'CHECKING')}</span></p>
        <div class="portal-case-state" data-case-state="${esc(c.status)}"><strong>${esc(label)}</strong><p>${esc(explanation)}</p></div>
        <div class="conversation">${c.conversation.map(m=>`<div class="chat-message ${['SUPPORT','AI_SUPPORT'].includes(m.sender)?'support':''}"><small>${esc(m.sender.replaceAll('_',' '))} · ${esc(new Date(m.at).toLocaleString())}</small><p>${esc(m.text)}</p></div>`).join('')}</div>
        <label>Reply or outcome details<textarea data-note="${esc(c.id)}">${esc(drafts.get(c.id)||'')}</textarea></label>
        <div class="case-actions">${active?`<button data-update="${esc(c.id)}">Send reply to support</button><button data-resolved="${esc(c.id)}">${c.informational_answer?'This answers my question':'Issue resolved'}</button>`:''}<button data-unresolved="${esc(c.id)}">Still unresolved</button></div>
        <p class="portal-case-notice ${notice?.error?'error':''}" data-case-notice="${esc(c.id)}" role="status" aria-live="polite" tabindex="-1" ${notice?'':'hidden'}>${esc(notice?.text||'')}</p>
        <p class="muted">${c.informational_answer?'Accepting a routine answer records that your question was answered. It does not confirm repairs or close a maintenance case.':'Still unresolved saves your message and asks the support team to handle the request. Staff checks the outcome before closing it.'}</p>
    </article>`;
}

async function refresh(){
    const data=await request('');cases=new Map(data.cases.map(c=>[c.id,c]));
    $('tenantArea').hidden=false;$('portalAccessCard').hidden=true;$('portalSignOut').hidden=false;
    $('tenantIdentity').textContent=data.property_name+' · '+data.unit_ref;
    $('demoTenantBanner').hidden=!data.demo_only;
    if(selectedCase&&!cases.has(selectedCase))selectedCase=null;
    renderRequests();showView(currentView);
}
async function demoSignIn(){
    const response=await fetch('/api/demo/session',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:'{}'});
    const result=await response.json();if(!response.ok)throw Error(result.error||'Demo access is unavailable');
    key=result.token;drafts.clear();notices.clear();attempts.clear();
    await refresh();openDestination();$('portalNotice').textContent='You are using a fictional demo tenant. Start a new request or open My requests.';
    const url=new URL(location.href);url.searchParams.delete('demo');history.replaceState(null,'',url);
}
async function loadEntry(){
    try{
        const response=await fetch('/api/demo');const demo=await response.json();
        $('demoEntry').hidden=!demo.available;$('privateAccess').open=!demo.available;
        if(demo.available&&new URLSearchParams(location.search).get('demo')==='1')await operation(demoSignIn);
    }catch{ $('privateAccess').open=true; }
}

function caseNotice(id,text,error=false){
    notices.set(id,{text,error});
    const target=document.querySelector(`[data-case-notice="${id}"]`);
    if(target){
        target.textContent=text;target.hidden=false;target.classList.toggle('error',error);
        target.focus({preventScroll:true});target.scrollIntoView({block:'nearest'});
    }
}

async function operation(fn,caseId){
    if(busy)return;
    busy=true;
    const locked=[...document.querySelectorAll('button,input,textarea')].filter(e=>!e.disabled);
    locked.forEach(e=>e.disabled=true);
    try{await fn();}
    catch(error){
        $('portalNotice').textContent=error.message;
        if(caseId&&key)caseNotice(caseId,error.message,true);
    }finally{locked.forEach(e=>e.disabled=false);busy=false;}
}

$('portalAccess').onsubmit=event=>{
    event.preventDefault();
    operation(async()=>{
        key=$('accessKey').value.trim();drafts.clear();notices.clear();attempts.clear();$('tenantArea').hidden=true;
        await refresh();$('accessKey').value='';$('portalNotice').textContent='Your support conversations are loaded.';
    }).then(()=>{if(!$('tenantArea').hidden)openDestination();});
};
$('portalSignOut').onclick=()=>{
    if(busy)return;
    closeRecords();$('portalNotice').textContent='Your support records are closed on this page.';$('accessKey').focus();
};
$('refreshPortal').onclick=()=>operation(refresh);
$('tenantIntake').onsubmit=event=>{
    event.preventDefault();
    const payload=Object.fromEntries(new FormData(event.target));
    operation(async()=>{
        const result=await send('intake','/intake',payload);
        event.target.reset();selectedCase=result.id;currentView='conversations';await refresh();
        $('portalNotice').textContent='Support request '+result.id+' saved. Follow replies in My requests.';
        const current=cases.get(result.id);
        caseNotice(result.id,current?.automatic_pending?'Your request was saved. AI is reviewing it.':'Your request was saved. Check the support status above for the next step.');
    });
};
document.addEventListener('click',event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.dataset.portalView){selectedCase=null;showView(button.dataset.portalView);renderRequests();return;}
    if(button.dataset.openRequest){selectedCase=button.dataset.openRequest;showView('conversations');renderRequests();document.getElementById('portal-case-'+selectedCase)?.scrollIntoView({block:'start'});return;}
    const id=button.dataset.update||button.dataset.resolved||button.dataset.unresolved;
    if(!id)return;
    const note=document.querySelector(`[data-note="${id}"]`).value;
    operation(async()=>{
        caseNotice(id,'Saving your update…');
        if(button.dataset.update)await send('update-'+id,'/update',{id,note});
        else await send('feedback-'+id,'/feedback',{id,note,resolved:!!button.dataset.resolved});
        drafts.delete(id);await refresh();
        const current=cases.get(id);
        let message;
        if(button.dataset.unresolved)message='Your message was saved. This request is now waiting for the support team. You can add more details here.';
        else if(current?.status==='HUMAN_REVIEW')message='Your message was saved for the support team. The request remains open.';
        else if(current?.status==='ANSWERED')message='You accepted the answer. You can still choose Still unresolved if you need more help.';
        else if(current?.automatic_pending)message='Your message was sent. AI is reviewing it and will reply here.';
        else message=button.dataset.update?'Your message was saved for support.':'Your feedback was saved. Staff will check the outcome before closing the request.';
        caseNotice(id,message);$('portalNotice').textContent=message;
    },id);
});
document.addEventListener('input',event=>{
    if(event.target.dataset.note)drafts.set(event.target.dataset.note,event.target.value);
});
setInterval(()=>{
    if(key&&!busy&&!document.querySelector('textarea:focus,input:focus'))operation(refresh);
},10000);

$('allRequests').onclick=()=>{selectedCase=null;renderRequests();};
$('tryDemoTenant').onclick=()=>operation(demoSignIn);
loadEntry();
