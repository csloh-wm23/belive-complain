"""Manual genuine-Hermes voice rehearsal; fictional text only, no WhatsApp sends."""
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from belive import whatsapp_ai as ai,whatsapp_triage as triage
from belive.settings import load_settings
from belive.workspace import selected_database

def main():
    settings=load_settings(selected_database());assert settings.agent_engine=='hermes' and settings.llm_provider=='openai'
    folder=ROOT/'data/tone-rehearsal'/secrets.token_hex(4);folder.mkdir(parents=True)
    events=[];service=SimpleNamespace(settings=settings,store=SimpleNamespace(path=folder/'qa.db'),record_native_execution=events.append)
    scenarios=[
      ('casual_en','bro my phone wifi damn slow la, what can i try myself?',[],False),
      ('formal_en','Good afternoon. Could you advise on the initial checks I can perform on my own phone before reporting a Wi-Fi issue?',[],False),
      ('frustrated_en',"I already turned Wi-Fi off and on three times. You're repeating yourself. What ELSE can I check?",[{'role':'AI','text':'Try turning Wi-Fi off and on.'}],False),
      ('casual_ms','bro wifi sy asyik putus la, sy dh on off wifi. skrg nk check apa?',[],False),
      ('casual_zh','欸，我手机wifi又断了啦，已经关了再开了，还有啥能试？',[],False),
      ('casual_handover','bro can my cousin stay overnight tmr? idk if allowed, ask staff first pls',[],True),
    ];results=[]
    for label,text,history,handover in scenarios:
        if '--handover-only' in sys.argv and not handover:continue
        context={'conversation':history+[{'role':'CUSTOMER','text':text}],'current_message':{'role':'CUSTOMER','text':text},'latest_sender':'CUSTOMER',
                 'sop':[],'approved_experiences':[],'staff_guidance':[],'support_requests':[],'reviewed_writing_tips':[],
                 'research_sources':[],'research_attempted':False,'explicit_staff_requested':handover,'waiting_for_staff':False}
        assessment=triage.greeting(text)
        if handover:assessment.update(severity='MEDIUM',requires_human=True)
        context['assessment']=assessment
        draft=ai.reply(service,context)
        assessment,public,kind,private=triage.apply_policy(assessment,draft,context)
        review_context={**context,'acknowledgement_only':private is not None,'private_staff_draft':private}
        passed=ai.review(service,review_context,public['reply'],public)
        if not passed:print('REVIEW BLOCKED: '+json.dumps({'scenario':label,'reply':public['reply'],'private_draft':private,'feedback':review_context.get('_review_feedback',{})},ensure_ascii=True),flush=True)
        assert passed,'Reply failed safety review: '+label
        if handover:assert public['reply']==draft['handover_reply'] and kind=='ACKNOWLEDGEMENT' and public['needs_staff']
        else:assert not public['needs_staff'],'Routine phone question unexpectedly routed to staff: '+label
        row={'scenario':label,'customer':text,'reply':public['reply'],'review_passed':passed,'delivery_kind':kind}
        results.append(row);print(json.dumps(row,ensure_ascii=True),flush=True)
    assert all(e.get('engine')=='hermes-native' and e.get('agent_class')=='run_agent.AIAgent' and e.get('api_calls',0)>0 for e in events)
    (folder/'results.json').write_text(json.dumps({'scenarios':results,'executions':events},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: '+str(len(results))+' genuine native reply/review scenarios. '+str(folder/'results.json'),flush=True)

if __name__=='__main__':main()
