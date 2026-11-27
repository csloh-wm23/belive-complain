"""Manual unbiased routing rehearsal: live Hermes, approved knowledge and real web tools.

Customer messages contain no requested route. No AI, SOP retrieval, research or reviewer
is mocked. Only the existing simulated delivery channel avoids real customer messages.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import sys
from types import SimpleNamespace,MethodType
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from belive.service import Service
from belive.store import Store,now,digest
from belive.settings import load_settings
from belive.workspace import selected_database
from belive import whatsapp as wa,shared_memory,experience_learning

class ReadStore(Store):
    def __init__(self,path):self.path=path
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()

def seed_approved(service,source):
    proxy=SimpleNamespace(store=ReadStore(source));proxy.public_lessons=MethodType(Service.public_lessons,proxy)
    with proxy.store.connect() as db:
        knowledge=wa.sop(proxy,db,{'property_ref':''});documents=shared_memory.documents(proxy,db)
        experiences=experience_learning.experiences(proxy,db)
        tips=shared_memory.tips(proxy,db) if shared_memory.enabled(proxy,db) else [x for x in proxy.store.all(db,'reply_learning') if x.get('approved') and x.get('status')=='APPROVED' and x.get('scope_condo') is None]
        routing=proxy.store.all(db,'routing')
    with service.store.connect() as db:
        for item in knowledge:service.store.put(db,'wa_knowledge',item)
        for item in documents:service.store.put(db,'sop_document',{k:item.get(k) for k in ('id','active','filename','revision')})
        for item in routing:service.store.put(db,'routing',item)
        for exp in experiences:
            cid='QA-APPROVED-'+digest(exp['id'])[:12]
            service.store.put(db,'case',{'id':cid,'status':'CLOSED','closure_reason':'VERIFIED','category':exp['category'],'sample_data':exp.get('sample_data',False)})
            service.store.put(db,'feedback',{'id':exp['id'],'case_id':cid,'verdict':'CORRECTED','public_question':exp['question'],'text':exp['answer'],'at':now()})
        for tip in tips:
            service.store.put(db,'reply_learning',{k:tip.get(k) for k in ('id','question','tip','category','scope_condo','revision','approved','status','at','case_id')})
    return {'sop':len(knowledge),'documents':len(documents),'approved_experiences':len(experiences),'approved_tips':len(tips)}

def main():
    source=selected_database();settings=load_settings(source)
    assert settings.agent_engine=='hermes' and settings.llm_provider=='openai'
    folder=ROOT/'data/autonomy-rehearsal'/secrets.token_hex(4);folder.mkdir(parents=True)
    service=Service(folder/'qa.db');service.settings=settings;service.ai.settings=settings
    result={'knowledge_snapshot':seed_approved(service,source),'rounds':[]}
    print('Current approved knowledge copied privately: '+json.dumps(result['knowledge_snapshot']),flush=True)
    if '--prior-handover' in sys.argv:
        # Reproduce the observed old conversation state, not an expected model decision.
        old=service.command('wa_simulate',{'customer':'normal-washer','text':'洗衣机屏幕上有个错误代码，刚开始就停住了，怎么办？'},secrets.token_hex(16))
        with service.store.connect() as db:
            thread=service.store.get(db,'wa_thread',old['thread_id']);case=service.store.get(db,'case',thread['case_id'])
            case.update(category='MAINTENANCE',severity='MEDIUM');service.store.put(db,'case',case)
            message=next(x for x in service.store.all(db,'wa_message') if x['thread_id']==thread['id'])
            wa._staff_request(service,db,thread,'确认洗衣机故障下一步如何处理。',True,origin_message_id=message['id'])
            service.store.put(db,'wa_thread',thread)
            service.store.put(db,'wa_message',{'id':'QA-HISTORICAL-ACK','thread_id':thread['id'],'case_id':case['id'],'direction':'AI','text':'洗衣机刚启动就停了，确实挺不方便。我先跟团队确认一下这个情况；方便的话，把屏幕上的错误代码、品牌和型号发我。','kind':'text','at':now()})
            for turn in service.store.all(db,'wa_turn'):
                turn['status']='COMPLETE';service.store.put(db,'wa_turn',turn)
        result['historical_state']='Observed earlier washer handover; subsequent model decision remains unconstrained.'
    scenarios=[
        ('phone','我的手机连不上 Wi-Fi，但室友的手机可以，我能先检查什么？'),
        ('washer','洗衣机屏幕上有个代码，停住了，我现在要怎么办？'),
        ('washer','Samsung WW90T554DAX，屏幕是4C，刚开始进水就停了，地上没有水。'),
        ('rules','晚上几点之后需要保持安静？'),
        ('deposit','Boleh bayar deposit dalam tiga kali?'),
        ('door','房门钥匙转不动，我人在走廊，门开不了，怎么办？'),
        ('handle','房间门把手掉下来了，现在门关不牢，怎么办？'),
        ('company','你们的官网是什么？我想看看房源。'),
    ]
    if '--washer-only' in sys.argv:scenarios=[x for x in scenarios if x[0]=='washer']
    selected={arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--case=')}
    if selected:scenarios=[x for x in scenarios if x[0] in selected]
    if '--prior-handover' in sys.argv:scenarios=[x for x in scenarios if x[0]=='washer' and x[1].startswith('Samsung')]
    for customer,text in scenarios:
        response=service.command('wa_simulate',{'customer':'normal-'+customer,'text':text},secrets.token_hex(16))
        wa.process_thread(service,response['thread_id'])
        with service.store.connect() as db:
            outputs=[o for o in service.store.all(db,'wa_outgoing') if o['thread_id']==response['thread_id']]
            out=outputs[0];requests=[r for r in service.store.all(db,'wa_staff') if r['thread_id']==response['thread_id']]
            events={e['id']:e for e in service.store.all(db,'native_execution')}
            jobs=[o for o in service.store.all(db,'outbox') if o['entity']==out['case_id']]
        assert out['status']=='SIMULATED','This rehearsal must never send to Meta'
        executions=[events[i] for i in out.get('native_execution_ids',[])]
        assert out.get('native_reply_verified') and any(e['role']=='WhatsApp Reply Safety Agent' for e in executions)
        row={'customer':customer,'message':text,'reply':out['text'],'private_draft':out.get('staff_draft'),'assessment':out['assessment'],
             'delivery_kind':out['delivery_kind'],'handling':out.get('handling'),'decision_reason':out.get('decision_reason'),'decision_trace':out.get('decision_trace'),'steps':out['steps'],'sources':out.get('sources',[]),'research_sources':out.get('research_sources',[]),
             'staff_questions':[{'question':r['question'],'maintenance':r.get('maintenance'),'assigned_team':r.get('assigned_team'),'routing_confirmed':r.get('routing_confirmed'),'status':r['status']} for r in requests],
             'notification_queues':[{'kind':j['kind'],'target':j['target'],'status':j['status']} for j in jobs],
             'executions':[{k:e.get(k) for k in ('engine','agent_class','role','api_calls','executed_tools')} for e in executions]}
        result['rounds'].append(row);(folder/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(row,ensure_ascii=True),flush=True)
    print('COMPLETE — observed decisions only; no expected answers supplied. '+str(folder/'results.json'),flush=True)

if __name__=='__main__':main()
