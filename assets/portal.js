const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let key='',busy=false;const drafts=new Map();
const topicTitles={wifi:'Wi-Fi support request',maintenance:'Repairs and maintenance',cleaning:'Cleaning concern',access:'Room or building access',utilities:'Water or utilities enquiry',billing:'Billing or other enquiry'};
const selectedTopic=new URLSearchParams(location.search).get('topic');
if(topicTitles[selectedTopic])$('tenantIntake').elements.title.value=topicTitles[selectedTopic];
function closeRecords(){key='';drafts.clear();$('tenantArea').hidden=true;$('tenantCases').replaceChildren();$('portalAccessCard').hidden=false;$('portalSignOut').hidden=true;$('accessKey').value='';}
function openDestination(){
    const conversations=location.hash==='#conversations';
    const target=$(conversations?'conversations':'report');
    target.scrollIntoView({block:'start'});
    (conversations?$('conversationHeading'):$('tenantIntake').elements.title).focus({preventScroll:true});
}
async function request(route,p){const r=await fetch('/api/portal'+route,{method:p?'POST':'GET',headers:{'Authorization':'Bearer '+key,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:p?JSON.stringify(p):undefined});const j=await r.json();if(!r.ok){if(r.status===401)closeRecords();throw Error(j.error||'Request failed');}return j;}
async function refresh(){const d=await request('');$('tenantArea').hidden=false;$('portalAccessCard').hidden=true;$('portalSignOut').hidden=false;$('tenantCases').innerHTML=d.cases.map(c=>`<article class="record-card"><h3>${esc(c.title)}</h3><p>${esc(c.id)} · ${esc(c.status)}</p><div class="conversation">${c.conversation.map(m=>`<div class="chat-message ${m.sender==='SUPPORT'?'support':''}"><small>${esc(m.sender.replaceAll('_',' '))} · ${esc(new Date(m.at).toLocaleString())}</small><p>${esc(m.text)}</p></div>`).join('')}</div><label>Reply or outcome details<textarea data-note="${c.id}">${esc(drafts.get(c.id)||'')}</textarea></label><div class="case-actions">${!['CLOSED','SKIPPED'].includes(c.status)?`<button data-update="${c.id}">Send reply to support</button><button data-resolved="${c.id}">Issue resolved</button>`:''}<button data-unresolved="${c.id}">Still unresolved</button></div><p class="muted">Your feedback is recorded for staff review. Staff verifies the outcome before closing a case.</p></article>`).join('')||'<p>No cases yet.</p>';}
async function operation(fn){if(busy)return;busy=true;const locked=[...document.querySelectorAll('button,input,textarea')].filter(e=>!e.disabled);locked.forEach(e=>e.disabled=true);try{await fn();}catch(err){$('portalNotice').textContent=err.message;}finally{locked.forEach(e=>e.disabled=false);busy=false;}}
$('portalAccess').onsubmit=e=>{e.preventDefault();operation(async()=>{key=$('accessKey').value.trim();drafts.clear();$('tenantArea').hidden=true;await refresh();$('accessKey').value='';$('portalNotice').textContent='Your support conversations are loaded.';}).then(()=>{if(!$('tenantArea').hidden)openDestination();});};
$('portalSignOut').onclick=()=>{if(busy)return;closeRecords();$('portalNotice').textContent='Your support records are closed on this page.';$('accessKey').focus();};
$('refreshPortal').onclick=()=>operation(refresh);
$('tenantIntake').onsubmit=e=>{e.preventDefault();const payload=Object.fromEntries(new FormData(e.target));operation(async()=>{const result=await request('/intake',payload);e.target.reset();await refresh();$('portalNotice').textContent='Support request '+result.id+' saved. Follow replies in My conversations below.';});};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const id=b.dataset.update||b.dataset.resolved||b.dataset.unresolved;if(!id)return;operation(async()=>{const note=document.querySelector(`[data-note="${id}"]`).value;if(b.dataset.update)await request('/update',{id,note});else await request('/feedback',{id,note,resolved:!!b.dataset.resolved});drafts.delete(id);document.querySelector(`[data-note="${id}"]`).value='';await refresh();$('portalNotice').textContent=b.dataset.update?'Your reply was saved for support.':'Your outcome feedback was saved for staff review.';});});
setInterval(()=>{if(key&&!busy&&!document.querySelector('textarea:focus,input:focus'))operation(refresh);},10000);

document.addEventListener('input',e=>{if(e.target.dataset.note)drafts.set(e.target.dataset.note,e.target.value);});
