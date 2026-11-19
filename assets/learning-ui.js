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
function card(title,value){
    if(!value)return `<section class="card"><h2>${title}</h2><p>The reply will appear here when the agent run finishes.</p></section>`;
    const labels={numbered_steps:'Two numbered points, starting with point 1',one_question:'One clarifying question',short_reply:'90 words or fewer'};
    return `<section class="card"><span class="eyebrow">${value.real_model?'REAL MODEL REPLY':'TEST DOUBLE REPLY'}</span><h2>${title}</h2><p class="learning-answer">${esc(value.response)}</p><strong>${value.score.passed} of ${value.score.total} clarity checks</strong><p class="muted">${value.score.word_count??value.response.split(/\s+/).length} words</p><ul>${Object.entries(value.score.checks).map(([key,passed])=>`<li>${passed?'✓':'—'} ${labels[key]}</li>`).join('')}</ul><p class="muted">Reviewed examples used: ${value.learning_used?.count||0}</p>${(value.agent_trace||[]).length?`<small>${value.agent_trace.map(x=>esc(x.agent)).join(' → ')}</small>`:''}</section>`;
}
function render(status){
    data=status;
    $('demoSetupStatus').textContent=data.demo?.available?'Fictional demo is ready. Tenant sign-in needs no copied key.':'Demo sign-in is off. Prepare fictional data here to enable it.';
    $('toggleDemo').hidden=!data.demo?.available;
    $('learningModel').textContent=data.readiness?.model?'Model · '+data.readiness.model:'Set up your AI model to run a comparison.';
    const scenarios=data.learning_scenarios||[];
    const topics=$('learningTopic');
    const options=scenarios.map(topic=>`<option value="${esc(topic.category)}">${esc(topic.label)}</option>`).join('')
        ||'<option value="">No approved topics</option>';
    if(options!==topicOptions){
        const previous=topics.value;
        topics.innerHTML=options;
        if(scenarios.some(topic=>topic.category===previous))topics.value=previous;
        else if(!$('learningQuestion').value) $('learningQuestion').value=scenarios[0]?.question||'';
        topicOptions=options;
    }
    const runs=data.learning_runs||[];
    if(selected===undefined)selected=runs.find(r=>['BASELINE_QUEUED','BASELINE_RUNNING','BASELINE_READY',
        'IMPROVED_QUEUED','IMPROVED_RUNNING'].includes(r.status))?.id||null;
    $('learningRunPicker').innerHTML=runs.length?runs.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''}>${esc(r.topic_label||'Wi-Fi')} · ${esc(new Date(r.at).toLocaleString())} · ${esc(r.status==='COMPLETE'?'Comparison complete':r.status.replaceAll('_',' ').toLowerCase())}</option>`).join(''):'<option value="">No comparisons yet</option>';
    const run=runs.find(r=>r.id===selected);
    if(run&&run.id!==displayedRun){
        if(scenarios.some(topic=>topic.category===run.category))topics.value=run.category;
        $('learningQuestion').value=run.question;
        displayedRun=run.id;
    }
    const picker=$('learningRunPicker');
    if(!run&&runs.length){
        picker.prepend(new Option('Choose a saved comparison',''));
        picker.value='';
    }
    $('learningRunQuestion').hidden=!run;
    $('learningRunQuestion').textContent=run?`Question used · ${run.topic_label||'Wi-Fi'} · ${run.question}`:'';
    $('approvedLearningLesson').hidden=!run?.lesson;
    $('approvedLearningLesson').textContent=run?.lesson?'Tip used: '+run.lesson:'';
    const pending=submitting||Boolean(selected&&!run)||Boolean(run&&['BASELINE_QUEUED','BASELINE_RUNNING','IMPROVED_QUEUED','IMPROVED_RUNNING'].includes(run.status));
    topics.disabled=!scenarios.length||pending;
    $('learningQuestion').disabled=pending;
    picker.disabled=pending;
    $('learningStart').querySelector('button').disabled=!data.demo?.available||!scenarios.length||pending;
    $('learningLessonCard').hidden=!run||!['BASELINE_READY','IMPROVED_QUEUED','IMPROVED_RUNNING','COMPLETE'].includes(run.status);
    $('learningImprove').hidden=run?.status!=='BASELINE_READY';
    $('learningImprove').querySelector('button').disabled=submitting||run?.status!=='BASELINE_READY';
    if(run?.id!==lessonRun&&document.activeElement!==$('learningLesson')){
        $('learningLesson').value=data.learning_lesson||'';
        lessonRun=run?.id;
    }
    const messages={BASELINE_QUEUED:'Starting the first reply…',BASELINE_RUNNING:'The agents are preparing the first reply…',BASELINE_READY:'First reply ready. Review the lesson below, then generate the next reply.',IMPROVED_QUEUED:'Starting the reply with reviewed feedback…',IMPROVED_RUNNING:'The agents are using the reviewed lesson for the next reply…',STALE:'The knowledge changed. Start a fresh comparison.',INTERRUPTED:'This run was interrupted. Start a fresh comparison.'};
    let text=run?messages[run.status]||'':pending?'Starting your new comparison…':!data.demo?.available
        ?'Prepare the demo in Setup, then generate a reply to begin.'
        :'Choose a practice topic and generate the first reply for this question.';
    if(run?.status==='FAILED'){
        const errors={
            AI_LEARNING_TOPIC_MISMATCH:'The question did not match the chosen guide. Pick a different topic or edit the question.',
            AI_UNGROUNDED_GUIDANCE:'This reply could not pass the guide and safety checks. Try a routine question that the guide covers.'
        };
        text=errors[run.error]||'The real AI run could not complete ('+run.error+'). Check the model in Setup, then start a new comparison.';
    }
    if(run?.status==='COMPLETE')text=run.change>0?`This test improved by ${run.change} clarity check(s). The reviewed lesson was saved automatically for future demo replies.`:run.improved_clarity?`Both replies passed all checks, and the next reply used ${run.words_saved} fewer words (at least 20% shorter). The reviewed lesson was saved for future demo replies.`:run.change===0?'No improvement measured in this run. The scores stayed the same, so no new lesson was automatically saved.':'The next reply passed fewer checks in this run. No lesson was automatically saved.';
    $('learningStatus').textContent=formMessage||text;
    $('learningComparison').innerHTML=run?card('Before reviewed feedback',run.baseline)+card('After reviewed feedback',run.improved):'';
    $('learnedStyles').innerHTML=(data.learned_styles||[]).filter(s=>s.active).map(s=>`<article class="record-card"><strong>Lesson saved for ${esc(scenarios.find(topic=>topic.category===(s.scope_category||'WIFI'))?.label||s.scope_category||'Wi-Fi')} demo replies</strong><p>${esc(s.text)}</p><button data-revoke-lesson="${esc(s.id)}">Stop using this lesson</button></article>`).join('')||'<p class="muted">No measured improvement has been saved as a demo lesson yet.</p>';
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
$('learningStart').onsubmit=async event=>{
    event.preventDefault();
    if(submitting)return;
    const input={category:$('learningTopic').value,question:$('learningQuestion').value};
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
