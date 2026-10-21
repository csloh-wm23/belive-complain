import test from 'node:test';
import assert from 'node:assert/strict';
import {seed,createCase,act,examples,redact} from '../core.mjs';
const input={title:'A service connection problem',description:'The connection stops repeatedly during a session.',category:'Service',severity:'MEDIUM',source:'Operator entry'};

test('intake is independent, operator-triaged, redacted and deduplicated',()=>{
 const state=seed(),c=createCase(state,{...input,description:input.description+' Contact sample@example.com or +60123456789.'});
 assert.equal(c.status,'NEW');assert.equal(c.demo,false);assert(!c.description.includes('example.com'));assert(!c.description.includes('60123456789'));
 assert.throws(()=>createCase(state,{...input,description:input.description+' Contact sample@example.com or +60123456789.'}),/already saved/);
 assert.equal(createCase(state,{...input,title:'An urgent safety concern',severity:'CRITICAL'}).status,'HUMAN_REVIEW');
 assert.equal(seed().cases.length,4);
});
test('closure requires acknowledgement, follow-up and verification evidence',()=>{
 const state=seed(),c=createCase(state,input);
 assert.throws(()=>act(state,c.id,'close'),/verification/);
 assert.throws(()=>act(state,c.id,'followup',{note:'Staff checked the report.'}),/acknowledge/);
 act(state,c.id,'acknowledge',{owner:'Support team'});
 assert.throws(()=>act(state,c.id,'acknowledge',{owner:'Other team'}),/already/);
 assert.throws(()=>act(state,c.id,'verify',{note:'Evidence from customer.'}),/follow-up/);
 act(state,c.id,'followup',{note:'Staff reviewed the report; awaiting customer confirmation.'});
 assert.throws(()=>act(state,c.id,'verify',{note:''}),/meaningful/);
 act(state,c.id,'verify',{note:'Operator records that the demo customer confirmed the check.'});
 act(state,c.id,'close');assert.equal(c.status,'CLOSED');assert(state.audit.some(a=>a.action==='Case closed locally'));
});
test('approved or corrected feedback is revocable and reopening withdraws reuse',()=>{
 const state=seed(),c=state.cases.find(c=>c.status==='CLOSED');
 assert.equal(examples(state).length,1);
 act(state,c.id,'feedback',{verdict:'REJECTED'});assert.equal(examples(state).length,0);
 act(state,c.id,'feedback',{verdict:'CORRECTED',note:'Ask which steps have been tried. Contact sample@example.com.'});
 assert.equal(examples(state).length,1);assert(!examples(state)[0].text.includes('example.com'));
 assert.throws(()=>act(state,c.id,'draft',{note:'Changed after closure'}),/Reopen/);
 act(state,c.id,'reopen',{note:'Customer raised an additional concern.'});assert.equal(examples(state).length,0);assert.equal(c.status,'HUMAN_REVIEW');
 assert.throws(()=>act(state,c.id,'feedback',{verdict:'APPROVED'}),/Complete/);
});
test('unresolved follow-up returns to staff without inventing a resolution',()=>{
 const state=seed(),c=state.cases.find(c=>c.status==='FOLLOW_UP');act(state,c.id,'reassess',{note:'The reported issue is still present.'});assert.equal(c.status,'HUMAN_REVIEW');assert.equal(c.verification,'');
});
test('invalid transitions and missing response wording cannot become learning',()=>{
 const state=seed(),c=state.cases.find(c=>c.status==='CLOSED');c.draft='';
 assert.throws(()=>act(state,c.id,'feedback',{verdict:'APPROVED'}),/wording/);
 assert.throws(()=>act(state,c.id,'publish'),/Unknown/);
 assert.throws(()=>act(state,'missing','close'),/not found/);
 assert.throws(()=>createCase(state,{...input,severity:'UNKNOWN'}),/severity/);
 assert.equal(redact('No private details.'),'No private details.');
});
