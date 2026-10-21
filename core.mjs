export const STATES = {NEW:'New intake',HUMAN_REVIEW:'Needs staff',IN_PROGRESS:'In progress',FOLLOW_UP:'Follow-up',VERIFIED:'Verified',CLOSED:'Closed'};
export const KEY = 'belive-complaints-prototype:v1';
export const redact = text => String(text ?? '').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,'[email removed]').replace(/(?:\+?\d[\d ()-]{7,}\d)/g,'[number removed]');
const id = () => crypto.randomUUID();
export function log(state, caseId, action, detail) { state.audit.unshift({id:id(),caseId,action,detail:redact(detail),at:new Date().toISOString()}); }
export function createCase(state, input) {
  const title=redact(input.title).trim(), description=redact(input.description).trim();
  if(title.length<4 || title.length>120 || description.length<10 || description.length>3000)throw Error('Enter a title of 4–120 characters and details of 10–3,000 characters.');
  if(!['LOW','MEDIUM','HIGH','CRITICAL'].includes(input.severity))throw Error('Choose a valid severity.');
  if(!['Service','Billing','Product','Other'].includes(input.category))throw Error('Choose a category.');
  if(!['Operator entry','Public-source reference'].includes(input.source))throw Error('Choose an intake source.');
  const duplicate=state.cases.find(c=>c.title.toLowerCase()===title.toLowerCase()&&c.description.toLowerCase()===description.toLowerCase());
  if(duplicate)throw Error(`This intake is already saved as ${duplicate.id}.`);
  const c={id:`BL-${String(state.nextId++).padStart(4,'0')}`,title,description,severity:input.severity,category:input.category,source:input.source,status:['HIGH','CRITICAL'].includes(input.severity)?'HUMAN_REVIEW':'NEW',owner:'',draft:'',notes:[],verification:'',demo:false,createdAt:new Date().toISOString()};
  state.cases.unshift(c);log(state,c.id,'Intake recorded','Severity selected by operator; AI has not assessed this case.');return c;
}
export function act(state, caseId, action, input={}) {
  const c=state.cases.find(c=>c.id===caseId);if(!c)throw Error('Case not found.');
  const note=redact(input.note).trim(), owner=redact(input.owner).trim();
  const needNote=()=>{if(note.length<8||note.length>2000)throw Error('Add a meaningful note of 8–2,000 characters.');};
  if(action==='acknowledge') {
    if(!['NEW','HUMAN_REVIEW'].includes(c.status))throw Error('This case has already been acknowledged.');
    if(owner.length<2||owner.length>80)throw Error('Enter a staff name or role of 2–80 characters.');
    c.owner=owner;c.status='IN_PROGRESS';log(state,c.id,'Staff acknowledged',owner+' accepted local ownership. No notification was sent.');
  } else if(action==='followup') {
    if(c.status!=='IN_PROGRESS')throw Error('A staff member must acknowledge this case first.');needNote();
    c.status='FOLLOW_UP';c.notes.push({text:note,at:new Date().toISOString()});log(state,c.id,'Follow-up recorded',note);
  } else if(action==='reassess') {
    if(c.status!=='FOLLOW_UP')throw Error('Only a follow-up case can be reassessed.');needNote();c.status='HUMAN_REVIEW';c.verification='';log(state,c.id,'Returned to staff review',note);
  } else if(action==='verify') {
    if(c.status!=='FOLLOW_UP')throw Error('Record follow-up before verification.');needNote();
    c.verification=note;c.status='VERIFIED';log(state,c.id,'Operator recorded verification',note);
  } else if(action==='close') {
    if(c.status!=='VERIFIED'||!c.verification)throw Error('Record verification evidence before closing.');
    c.status='CLOSED';log(state,c.id,'Case closed locally','Closure follows operator-recorded verification; the application did not independently verify the outcome.');
  } else if(action==='reopen') {
    if(c.status!=='CLOSED')throw Error('Only closed cases can be reopened.');needNote();c.status='HUMAN_REVIEW';c.verification='';
    state.feedback.push({caseId:c.id,verdict:'REJECTED',text:'',at:new Date().toISOString()});log(state,c.id,'Case reopened',note+' Previous learning example revoked.');
  } else if(action==='draft') {
    if(!note||note.length>2000)throw Error('Enter response wording of 1–2,000 characters.');
    if(c.status==='CLOSED')throw Error('Reopen this case before editing its response.');
    c.draft=note;log(state,c.id,'Local response saved','Operator-written response; nothing sent.');
  } else if(action==='feedback') {
    if(c.status!=='CLOSED')throw Error('Complete the case before evaluating reusable wording.');
    if(!['APPROVED','CORRECTED','REJECTED'].includes(input.verdict))throw Error('Choose a valid feedback outcome.');
    const text=input.verdict==='CORRECTED'?note:c.draft;
    if(input.verdict!=='REJECTED'&&!text.trim())throw Error('Save response wording before approving an example.');
    state.feedback.push({caseId:c.id,verdict:input.verdict,text:input.verdict==='REJECTED'?'':redact(text),at:new Date().toISOString()});
    log(state,c.id,'Learning '+input.verdict.toLowerCase(),'Latest verdict controls reuse; style guidance only.');
  } else throw Error('Unknown case action.');
  return c;
}
export function examples(state) {
  const latest=new Map();for(const f of state.feedback)latest.set(f.caseId,f);
  return [...latest.values()].filter(f=>f.verdict!=='REJECTED'&&f.text&&state.cases.some(c=>c.id===f.caseId&&c.status==='CLOSED'));
}
export function seed() {
  const state={version:1,nextId:1005,cases:[],feedback:[],audit:[]};
  const rows=[
    ['BL-1004','Repeated interruptions during a live session','Fictional scenario: a customer reports three interruptions while using a live service. The cause has not been established.','Service','HIGH','HUMAN_REVIEW','Public-source reference',''],
    ['BL-1003','Unexpected duplicate charge','Fictional scenario: the customer believes the same service was charged twice. Payment records have not been checked.','Billing','MEDIUM','IN_PROGRESS','Operator entry','Billing team'],
    ['BL-1002','Replacement accessory still not working','Fictional scenario: a staff member recorded a replacement action. Customer confirmation and verification are still pending.','Product','MEDIUM','FOLLOW_UP','Operator entry','Support team'],
    ['BL-1001','Unclear setup instructions','Fictional scenario: the customer needed a clearer explanation of the setup sequence. A demonstration verification note is recorded.','Service','LOW','CLOSED','Operator entry','Support team']
  ];
  for(const [caseId,title,description,category,severity,status,source,owner] of rows) {
    state.cases.push({id:caseId,title,description,category,severity,status,source,owner,demo:true,createdAt:new Date().toISOString(),notes:[],verification:status==='CLOSED'?'Fictional verification: the demo customer confirmed the steps were clear.':'',draft:status==='CLOSED'?'Explain one step at a time and ask which step needs clarification.':''});
  }
  state.feedback.push({caseId:'BL-1001',verdict:'APPROVED',text:'Explain one step at a time and ask which step needs clarification.',at:new Date().toISOString()});
  log(state,'Workspace','Fictional demo loaded','Four sample cases and one approved style example. No real customer activity.');return state;
}
