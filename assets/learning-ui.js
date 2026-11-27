const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let csrf=document.querySelector('meta[name="csrf-token"]').content;
let data=null,selected,lessonRun=null,topicOptions='';
let displayedRun=null,submitting=false,formMessage='';
const attempts=new Map();
async function send(route,payload){
    const signature=JSON.stringify(payload);let attempt=attempts.get(route);
    if(!attempt||attempt.signature!==signature){attempt={signature,id:crypto.randomUUID()};attempts.set(route,attempt);}
    const options={method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':attempt.id},body:signature};
    let response=await fetch('/api/'+route,options);
    let result=await response.json();
    if(response.status===403&&result.code==='STALE_CSRF'){
        const authResponse=await fetch('/api/auth');
        const auth=await authResponse.json();
        if(authResponse.ok&&auth.csrf_token){
            csrf=auth.csrf_token;
            options.headers['X-CSRF-Token']=csrf;
            response=await fetch('/api/'+route,options);
            result=await response.json();
        }
    }
    if(!response.ok)throw Error(result.error||'The action could not be completed');
    attempts.delete(route);window.dispatchEvent(new Event('belive:refresh'));return result;
}
function matchedLesson(run){const answer=run?.experience?.answer||'';const tip=run?.writing_tip?.tip||'';return answer+(answer&&tip?'\n\nWriting improvement tip: ':'')+tip;}
function card(title,value){
    if(!value)return `<section class="card"><h2>${title}</h2><p>The reply will appear here when the agent run finishes.</p></section>`;
    if(value.checks)return `<section class="card"><span class="eyebrow">${value.real_model?'REAL MODEL REPLY':'TEST DOUBLE REPLY'}</span><h2>${title}</h2><p class="learning-answer">${esc(value.response)}</p><p>${value.experience_used?'Approved experience supplied: '+esc(value.experience_used.question):'No complaint knowledge supplied for this reply.'}</p>${value.writing_tip_used?`<p>Approved feedback-derived writing tip: ${esc(value.writing_tip_used.tip)}</p>`:''}<p class="muted">Passed the guidance/safety and location-relevance checks. Compare usefulness yourself; this is not a formatting score or proof of improvement.</p></section>`;
    const labels={numbered_steps:'Two numbered points, starting with point 1',one_question:'One clarifying question',short_reply:'90 words or fewer'};
    return `<section class="card"><span class="eyebrow">${value.real_model?'REAL MODEL REPLY':'TEST DOUBLE REPLY'}</span><h2>${title}</h2><p class="learning-answer">${esc(value.response)}</p><strong>${value.score.passed} of ${value.score.total} clarity checks</strong><p class="muted">${value.score.word_count??value.response.split(/\s+/).length} words</p><ul>${Object.entries(value.score.checks).map(([key,passed])=>`<li>${passed?'✓':'—'} ${labels[key]}</li>`).join('')}</ul><p class="muted">Reviewed examples used: ${value.learning_used?.count||0}</p>${(value.agent_trace||[]).length?`<small>${value.agent_trace.map(x=>esc(x.agent)).join(' → ')}</small>`:''}</section>`;
}
function render(status){
    data=status;
    renderReplyFeedback(status);
    $('demoSetupStatus').textContent=data.demo?.available?'Fictional demo is ready. Tenant sign-in needs no copied key.':'Demo sign-in is off. Prepare fictional data here to enable it.';
    $('toggleDemo').hidden=!data.demo?.available;
    $('learningModel').textContent=data.readiness?.model?'Model · '+data.readiness.model:'Set up your AI model to run a comparison.';
    const scenarios=data.learning_scenarios||[];
    const experiencePicker=$('learningExperience');
    const previousExperience=experiencePicker.value;
    const experienceOptions='<option value="">Automatically match my question</option>'+(data.learning_experiences||[]).map(x=>`<option value="${esc(x.id)}">${x.sample_data?'SAMPLE · ':''}${esc(x.question)} · ${esc(x.case_id||"Shared team memory")}</option>`).join('');
    if(experiencePicker.innerHTML!==experienceOptions){experiencePicker.innerHTML=experienceOptions;experiencePicker.value=previousExperience;}
    const topics=$('learningTopic');
    const options=scenarios.map(topic=>`<option value="${esc(topic.category)}">${esc(topic.label)}</option>`).join('')
        ||'<option value="">No approved topics</option>';
    if(options!==topicOptions){
        const previous=topics.value;
        topics.innerHTML=options;
        if(scenarios.some(topic=>topic.category===previous))topics.value=previous;
        else if(!$('learningQuestion').value){topics.value=scenarios.some(topic=>topic.category==='OTHER')?'OTHER':scenarios[0]?.category||'';$('learningQuestion').value=scenarios.find(topic=>topic.category===topics.value)?.question||'';}
        topicOptions=options;
    }
    const runs=data.learning_runs||[];
    if(selected===undefined)selected=runs.find(r=>r.mode==='experience'&&['BASELINE_QUEUED','BASELINE_RUNNING','BASELINE_READY',
        'IMPROVED_QUEUED','IMPROVED_RUNNING'].includes(r.status))?.id||null;
    $('learningRunPicker').innerHTML=runs.length?runs.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''}>${esc(r.topic_label||'Wi-Fi')} · ${esc(new Date(r.at).toLocaleString())} · ${esc(r.status==='COMPLETE'?'Comparison complete':r.status.replaceAll('_',' ').toLowerCase())}</option>`).join(''):'<option value="">No comparisons yet</option>';
    const run=runs.find(r=>r.id===selected);
    if(run&&run.id!==displayedRun){
        if(scenarios.some(topic=>topic.category===run.category))topics.value=run.category;
        $('learningQuestion').value=run.question;
        displayedRun=run.id;
        experiencePicker.value=run.experience?.id||'';
    }
    const picker=$('learningRunPicker');
    if(!run&&runs.length){
        picker.prepend(new Option('Choose a saved comparison',''));
        picker.value='';
    }
    $('learningRunQuestion').hidden=!run;
    $('learningRunQuestion').textContent=run?`Question used · ${run.topic_label||'Wi-Fi'} · ${run.question}`:'';
    $('approvedLearningLesson').hidden=!run?.lesson;
    $('approvedLearningLesson').textContent=run?.lesson?(run.mode==='experience'?'Approved complaint experience used: ':'Legacy writing tip used: ')+run.lesson:'';
    const pending=submitting||Boolean(selected&&!run)||Boolean(run&&['BASELINE_QUEUED','BASELINE_RUNNING','IMPROVED_QUEUED','IMPROVED_RUNNING'].includes(run.status));
    topics.disabled=!scenarios.length||pending;
    $('learningQuestion').disabled=pending;
    picker.disabled=pending;
    $('learningStart').querySelector('button').disabled=!data.readiness?.ai||!scenarios.length||pending;
    experiencePicker.disabled=pending;
    $('learningLessonCard').hidden=!run||!['BASELINE_READY','IMPROVED_QUEUED','IMPROVED_RUNNING','COMPLETE'].includes(run.status);
    const hasLearning=Boolean(run?.experience||run?.writing_tip);
    $('learningImprove').hidden=run?.status!=='BASELINE_READY'||(run?.mode==='experience'&&!hasLearning);
    $('learningNoExperience').hidden=!(run?.mode==='experience'&&!hasLearning);
    $('learningExperienceSource').innerHTML=(run?.experience?`<p><strong>${esc(run.experience.provenance)}</strong> · ${run.experience.case_id?`<button type="button" class="text-button" data-case="${esc(run.experience.case_id)}">Source case ${esc(run.experience.case_id)}</button>`:"Shared team memory"}</p><p>Matches: ${esc(run.experience.question)}</p>`:'')+(run?.writing_tip?`<p><strong>${run.writing_tip.sample_data?'SAMPLE · ':''}Approved writing improvement from customer feedback</strong> · ${run.writing_tip.case_id?`<button type="button" class="text-button" data-case="${esc(run.writing_tip.case_id)}">Source case ${esc(run.writing_tip.case_id)}</button>`:"Shared team memory"}</p>`:'');
    $('learningImprove').querySelector('button').disabled=submitting||run?.status!=='BASELINE_READY';
    if(run?.id!==lessonRun&&document.activeElement!==$('learningLesson')){
        $('learningLesson').value=run?.mode==='experience'?matchedLesson(run):run?.lesson||'';
        lessonRun=run?.id;
    }
    const messages={BASELINE_QUEUED:'Starting the first reply…',BASELINE_RUNNING:'The agents are preparing the first reply…',BASELINE_READY:'First reply ready. Review the lesson below, then generate the next reply.',IMPROVED_QUEUED:'Starting the reply with reviewed feedback…',IMPROVED_RUNNING:'The agents are using the reviewed lesson for the next reply…',STALE:'The knowledge changed. Start a fresh comparison.',INTERRUPTED:'This run was interrupted. Start a fresh comparison.'};
    let text=run?messages[run.status]||'':pending?'Starting your new comparison…':!data.readiness?.ai
        ?'Set up the AI model in System setup to generate replies. You can still open Past comparisons to read a saved run.'
        :'Enter your question and generate the first reply, or open Past comparisons to view a saved run.';
    if(run?.status==='FAILED'){
        const errors={
            AI_LEARNING_TOPIC_MISMATCH:'The question did not match the chosen guide. Pick a different topic or edit the question.',
            AI_UNGROUNDED_GUIDANCE:'This reply could not pass the guide and safety checks. Try a routine question that the guide covers.'
        };
        text=errors[run.error]||'The real AI run could not complete ('+run.error+'). Check the model in Setup, then start a new comparison.';
    }
    if(run?.status==='COMPLETE')text=run.change>0?`This test improved by ${run.change} clarity check(s). The reviewed lesson was saved automatically for future demo replies.`:run.improved_clarity?`Both replies passed all checks, and the next reply used ${run.words_saved} fewer words (at least 20% shorter). The reviewed lesson was saved for future demo replies.`:run.change===0?'No improvement measured in this run. The scores stayed the same, so no new lesson was automatically saved.':'The next reply passed fewer checks in this run. No lesson was automatically saved.';
    if(run?.mode==='experience'&&run.status==='BASELINE_READY')text=hasLearning?'First reply ready. Review the matched complaint experience / writing improvement below, then generate the next reply.':'First reply ready. No relevant approved experience or feedback-derived writing tip matched. Review actual customer feedback in the section above to develop an improvement; no fixed formatting tip will be invented.';
    if(run?.mode==='experience'&&run.status==='COMPLETE')text=run.comparison_note;
    $('learningStatus').textContent=formMessage||text;
    $('learningComparison').innerHTML=run?card(run.mode==='experience'?'Without reviewed experience / tips':'Legacy writing demo: before',run.baseline)+card(run.mode==='experience'?'With reviewed experience / writing tip':'Legacy writing demo: after',run.improved):'';
    $('learnedStyles').innerHTML=(data.learned_styles||[]).filter(s=>s.active).map(s=>`<article class="record-card"><strong>SAMPLE · Legacy writing tip for ${esc(scenarios.find(topic=>topic.category===(s.scope_category||'WIFI'))?.label||s.scope_category||'Wi-Fi')} demo replies</strong><p>${esc(s.text)}</p><button data-revoke-lesson="${esc(s.id)}">Stop using this lesson</button></article>`).join('')||'<p class="muted">No legacy demo tips saved.</p>';
}
window.addEventListener('belive:status',event=>render(event.detail));
$('learningRunPicker').onchange=()=>{
    selected=$('learningRunPicker').value||null;
    displayedRun=null;
    formMessage='';
    if(data)render(data);
};
function editPracticeQuestion(){
    if(selected===null&&!formMessage)return;
    selected=null;
    displayedRun=null;
    formMessage='';
    if(data)render(data);
}
$('learningTopic').onchange=()=>{
    const topic=(data?.learning_scenarios||[]).find(item=>item.category===$('learningTopic').value);
    $('learningQuestion').value=topic?.question||'';
    editPracticeQuestion();
};
$('learningQuestion').oninput=editPracticeQuestion;
$('learningExperience').onchange=()=>{const selectedExperience=(data?.learning_experiences||[]).find(x=>x.id===$('learningExperience').value);if(selectedExperience){$('learningQuestion').value=selectedExperience.question;$('learningTopic').value=selectedExperience.category;}editPracticeQuestion();};
$('learningStart').onsubmit=async event=>{
    event.preventDefault();
    if(submitting)return;
    const input={mode:'experience',category:$('learningTopic').value,question:$('learningQuestion').value,experience_id:$('learningExperience').value||undefined};
    selected=null;
    displayedRun=null;
    submitting=true;
    formMessage='';
    render(data);
    try{
        const result=await send('learning_start',input);
        selected=result.id;
    }catch(error){formMessage=error.message;}
    finally{submitting=false;render(data);}
};
$('learningImprove').onsubmit=async event=>{
    event.preventDefault();
    if(submitting)return;
    submitting=true;
    formMessage='Generating the next reply with reviewed feedback…';
    render(data);
    try{
        await send('learning_improve',{id:selected,lesson:$('learningLesson').value,confirmed:true});
        formMessage='';
    }catch(error){formMessage=error.message;}
    finally{submitting=false;render(data);}
};
$('prepareDemo').onclick=async()=>{
    $('prepareDemo').disabled=true;
    try{await send('demo_prepare',{confirmed:true});$('demoSetupStatus').textContent='Fictional demo is ready. If AI is configured, enable SIMPLE automatic replies below.';}
    catch(error){$('demoSetupStatus').textContent=error.message;}
    finally{$('prepareDemo').disabled=false;}
};
$('toggleDemo').onclick=()=>send('demo_settings',{enabled:false}).catch(error=>$('demoSetupStatus').textContent=error.message);
document.addEventListener('click',event=>{
    const button=event.target.closest('[data-revoke-lesson]');
    if(button)send('lesson_revoke',{id:button.dataset.revokeLesson}).catch(error=>$('learningStatus').textContent=error.message);
});

let routingShown='';
let replyFeedbackBusy=false;
const replyFeedbackDrafts=new Map();
function renderReplyFeedback(status){
    const list=$('replyFeedbackList');
    if(document.activeElement?.closest('#replyFeedbackList')&&['INPUT','TEXTAREA'].includes(document.activeElement.tagName))return;
    const names={PENDING:'Waiting for analysis',ANALYSING:'Examining the reply and customer feedback…',PROPOSED:'Improvement tip needs your review',OBSERVED:'Customer reaction recorded',APPROVAL_QUEUED:'Waiting for tip safety review',REVIEWING:'Checking the reviewed tip…',APPROVED:'Approved for relevant future replies',REJECTED:'Tip revoked',FAILED:'Analysis could not complete'};
    const reactions=status.feedback_reactions||{};
    const summary=`<p class="muted">Customer follow-ups checked · ${reactions.DISSATISFIED||0} dissatisfied · ${reactions.POSITIVE||0} positive · ${reactions.NEUTRAL||0} neutral · ${reactions.UNCLEAR||0} unclear</p>`;
    list.innerHTML=summary+((status.reply_learning||[]).map(item=>{
        const busy=replyFeedbackBusy||['ANALYSING','REVIEWING','APPROVAL_QUEUED'].includes(item.status);
        const tip=replyFeedbackDrafts.get(item.id)??item.tip;
        return `<article class="record-card" data-reply-feedback="${esc(item.id)}"><div class="card-heading"><strong>${esc(names[item.status]||item.status)}</strong><button type="button" class="text-button" data-case="${esc(item.case_id)}">Source case ${esc(item.case_id)}</button></div>
        <p class="eyebrow">${item.sample_data?'SAMPLE / TEST conversation':'Recorded complaint conversation'}</p>
        ${item.feedback_attribution?`<p>Feedback linked by: ${esc(item.feedback_attribution==='EXPLICIT_WHATSAPP_QUOTE'?'customer’s quoted WhatsApp reply':'latest WhatsApp reply; review topic relevance')}</p>`:''}<p><b>Original question</b> ${esc(item.question)}</p><p><b>Reply we sent</b></p><blockquote>${esc(item.reply)}</blockquote><p><b>Customer feedback afterward</b></p><blockquote>${esc(item.customer_feedback)}</blockquote>
        ${item.tone?`<p><b>Customer tone</b> ${esc(item.tone.toLowerCase())} · <b>Reaction</b> ${esc(item.reaction.toLowerCase())}</p>`:''}
        ${item.reason?`<p><b>AI assessment · ${esc(item.cause.replaceAll('_',' '))}</b> ${esc(item.reason)}</p><p class="muted">This is an assessment, not proof of what caused the complaint.${item.cause==='SERVICE_ACTION'?' Staff action is still needed; a writing tip does not resolve it.':''}</p>`:''}
        ${item.tip?`<label>Writing improvement tip from this feedback<textarea data-feedback-tip="${esc(item.id)}" maxlength="1000" ${item.status==='PROPOSED'?'':'readonly'}>${esc(tip)}</textarea></label>`:''}
        ${item.status==='PROPOSED'?`<label><input type="checkbox" data-tip-confirm="${esc(item.id)}"> I reviewed this as reusable writing advice without private facts or unverified promises.</label>`:''}
        <div class="case-actions">${!item.approved?`<button type="button" data-reply-learning-action="analyse" data-feedback-id="${esc(item.id)}" ${busy?'disabled':''}>${item.status==='PROPOSED'?'Reanalyse feedback':'Generate improvement tip'}</button>`:''}
        ${item.status==='PROPOSED'?`<button class="primary" type="button" data-reply-learning-action="approve" data-feedback-id="${esc(item.id)}" ${busy?'disabled':''}>Approve & use writing tip</button>`:''}
        ${item.approved?`<button type="button" data-reply-learning-action="test" data-feedback-id="${esc(item.id)}" ${busy||['QUEUED','RUNNING'].includes(item.preview_status)?'disabled':''}>Test improved reply</button>`:''}
        ${item.tip&&item.status!=='REJECTED'?`<button type="button" data-reply-learning-action="revoke" data-feedback-id="${esc(item.id)}" ${replyFeedbackBusy?'disabled':''}>Reject / revoke tip</button>`:''}</div>
        ${item.latest_case?`<button type="button" class="text-button" data-case="${esc(item.latest_case)}">Open latest reply using this tip →</button>`:''}
        ${item.approved?`<p class="muted">Writing tip provided to ${item.provided_count||0} published reply agent runs; ${item.negative_after_use||0} received further dissatisfied feedback · ${item.positive_after_use||0} received positive feedback. Open the source conversation to review the outcome. ${item.scope_condo?'Reuse is limited to the same property.':'Reuse is limited to matching questions.'}</p>`:''}
        ${item.preview_status==='RUNNING'||item.preview_status==='QUEUED'?'<p role="status">Generating a new draft using the reviewed writing tip…</p>':''}
        ${item.preview?`<p><b>New draft using the reviewed tip · not sent</b></p><blockquote>${esc(item.preview)}</blockquote><p class="muted">${esc(item.comparison_note)}</p>`:''}
        ${item.error?`<p class="error" role="alert">${esc(item.error)}. Review the tip or retry analysis.</p>`:''}</article>`;
    }).join('')||'<p>No dissatisfied follow-up after a published reply has been recorded yet. Check past replies, or use a test complaint to send a reply and then report Still unresolved. Luna checks the conversation and proposes a correction when the customer is dissatisfied.</p>');
}
document.addEventListener('input',event=>{if(event.target.matches('[data-feedback-tip]'))replyFeedbackDrafts.set(event.target.dataset.feedbackTip,event.target.value);});
$('scanReplyFeedback').onclick=async()=>{try{const result=await send('reply_learning_scan',{});$('replyFeedbackStatus').textContent=`${result.captured} feedback signal(s) recorded. Pending analysis runs in the background.`;}catch(error){$('replyFeedbackStatus').textContent=error.message;}};
document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-reply-learning-action]');if(!button||replyFeedbackBusy)return;
    const item=(data?.reply_learning||[]).find(x=>x.id===button.dataset.feedbackId);if(!item)return;
    const row=button.closest('[data-reply-feedback]');
    const payload={id:item.id,revision:item.revision,action:button.dataset.replyLearningAction,
        tip:row.querySelector('[data-feedback-tip]')?.value,confirmed:row.querySelector('[data-tip-confirm]')?.checked??false};
    replyFeedbackBusy=true;button.disabled=true;
    try{const result=await send('reply_learning_action',payload);replyFeedbackDrafts.delete(item.id);if(data)data.reply_learning=data.reply_learning.map(x=>x.id===result.id?result:x);$('replyFeedbackStatus').textContent=payload.action==='revoke'?'Writing tip revoked immediately.':'Saved. The background agent will update this feedback item.';}
    catch(error){$('replyFeedbackStatus').textContent=error.message;}
    finally{replyFeedbackBusy=false;if(data)renderReplyFeedback(data);}
});
window.addEventListener('belive:status',event=>{
 const route=event.detail.routing||{departments:{},version:0};
 if(routingShown===JSON.stringify(route))return;routingShown=JSON.stringify(route);
 const names={MAINTENANCE:'Maintenance',CLEANING:'Cleaning',WIFI:'Wi-Fi',ACCESS:'Access',UTILITIES:'Water and utilities',BILLING:'Billing',HOUSE_RULES:'House rules',OTHER:'Other support'};
 const fields=document.getElementById('routingFields');fields.replaceChildren();
 for(const [category,name] of Object.entries(names)){
  const label=document.createElement('label');label.textContent=name;
  const input=document.createElement('input');input.name=category;input.maxLength=80;input.placeholder='Support team';input.value=route.departments[category]||'';label.append(input);fields.append(label);
 }
});
document.getElementById('routingForm').onsubmit=async event=>{
 event.preventDefault();const form=event.target;const departments={};
 for(const input of form.querySelectorAll('#routingFields input'))departments[input.name]=input.value.trim();
 const status=document.getElementById('routingStatus');
 try{
  await send('routing_settings',{departments,confirmed:form.elements.confirmed.checked});
  status.textContent='Routing saved. Future staff handovers use these destinations.';
 }catch(error){status.textContent=error.message;}
};
