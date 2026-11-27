"""Authorised deidentified photo rehearsal; real Hermes, simulated WhatsApp transport."""
import base64,json,secrets,sys,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from belive.service import Service
from belive.settings import load_settings
from belive.workspace import selected_database
from belive import whatsapp as wa
from rehearse_autonomous_support import seed_approved

def main():
    source=selected_database();settings=load_settings(source)
    assert settings.agent_engine=='hermes' and settings.llm_provider=='openai'
    image=Path(sys.argv[1]);mime='image/png' if image.suffix.lower()=='.png' else 'image/jpeg'
    folder=ROOT/'data/photo-context-rehearsal'/secrets.token_hex(4);folder.mkdir(parents=True)
    s=Service(folder/'qa.db');s.settings=settings;s.ai.settings=settings
    snapshot=seed_approved(s,source)
    # Historical context deliberately contains a different device identifier.
    s.command('wa_simulate',{'customer':'photo-context-qa','text':'之前那台是 Samsung WW90T554DAX，显示 4C。'},secrets.token_hex(16))
    with s.store.connect() as db:
        for turn in s.store.all(db,'wa_turn'):
            turn['status']='COMPLETE';s.store.put(db,'wa_turn',turn)
    caption='我不知道牌子型号，也找不到标签。屏幕显示F06，只有这张照片，现在怎么办？' if '--unknown-brand' in sys.argv else '请问洗衣机发生了什么问题？'
    result=s.command('wa_simulate',{'customer':'photo-context-qa','text':caption,'image':'data:'+mime+';base64,'+base64.b64encode(image.read_bytes()).decode()},secrets.token_hex(16))
    reused=None
    if '--received-followup' in sys.argv:
        # Replay the received photo observation and last delivered reply, not a
        # fabricated model response. The live database is strictly read-only.
        db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        records=lambda kind:[json.loads(r[0]) for r in db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC',(kind,))]
        actual=next(m for m in records('wa_message') if (m.get('media') or {}).get('file')==image.name and m.get('vision'))
        past=next(m for m in records('wa_message') if m['case_id']==actual['case_id'] and m['direction']=='AI' and m['at']>=actual['at'])
        original_out=next(o for o in records('wa_outgoing') if o.get('reply_to_message_id')==actual['id'] and 'Photo read' in o.get('steps',[]))
        events={e['id']:e for e in records('native_execution')}
        vision_executor=next(events[i] for i in original_out['native_execution_ids'] if events[i]['role']=='WhatsApp Photo Agent')
        assert vision_executor['engine']=='hermes-native' and vision_executor['agent_class']=='run_agent.AIAgent' and vision_executor['api_calls']>0
        reused={k:vision_executor.get(k) for k in ('engine','agent_class','role','api_calls')};db.close()
        with s.store.connect() as db:
            photo=next(m for m in s.store.all(db,'wa_message') if m['kind']=='image');photo['vision']=actual['vision'];s.store.put(db,'wa_message',photo)
            for turn in s.store.all(db,'wa_turn'):
                turn['status']='COMPLETE';s.store.put(db,'wa_turn',turn)
            from belive.store import now
            s.store.put(db,'wa_message',{'id':'QA-REPLAYED-REPLY','thread_id':result['thread_id'],'case_id':photo['case_id'],'direction':'AI','kind':'text','text':past['text'],'at':now()})
        result=s.command('wa_simulate',{'customer':'photo-context-qa','text':'牌子和型号我真的不知道，标签也确实找不到，屏幕就是F06，现在还能怎么办？'},secrets.token_hex(16))
    wa.process_thread(s,result['thread_id'])
    first=None
    if '--repeat-unavailable' in sys.argv:
        with s.store.connect() as db:
            o=s.store.all(db,'wa_outgoing')[0];first={k:o.get(k) for k in ('text','handling','steps','research_sources','decision_trace')}
        result=s.command('wa_simulate',{'customer':'photo-context-qa','text':'型号确实找不到，标签也没有，照片也没办法再拍清楚，只有刚才那张图。'},secrets.token_hex(16))
        wa.process_thread(s,result['thread_id'])
    with s.store.connect() as db:
        out=s.store.all(db,'wa_outgoing')[0];photo=next(m for m in s.store.all(db,'wa_message') if m['kind']=='image')
        executions=s.store.all(db,'native_execution');requests=s.store.all(db,'wa_staff')
    assert out['status']=='SIMULATED'
    assert {'WhatsApp Customer Support Agent','WhatsApp Reply Safety Agent'}<={e['role'] for e in executions}
    assert reused or 'WhatsApp Photo Agent' in {e['role'] for e in executions}
    assert all(e['engine']=='hermes-native' and e['agent_class']=='run_agent.AIAgent' and e['api_calls']>0 for e in executions)
    observed={'knowledge_snapshot':snapshot,'first_reply':first,'reused_received_vision_executor':reused,'vision':photo.get('vision'),**{k:out.get(k) for k in ('text','status','handling','delivery_kind','decision_trace','steps','research_sources','research_purpose','identification_only')},'staff_requests':len(requests),'native_executions':[{k:e.get(k) for k in ('engine','agent_class','role','api_calls','executed_tools')} for e in executions]}
    if '--check-review' in sys.argv:
        from belive import whatsapp_ai
        context={'conversation':[{'role':'CUSTOMER','text':'Brand and model are unknown; the label is unavailable.'}],
                 'current_photo':{'observations':photo['vision']},'identification_only':True,'research_sources':out.get('research_sources',[]),
                 'research_summary':'Only possible product families have been found; the customer exact machine is not confirmed.',
                 'unavailable_details':['BRAND','MODEL','LABEL']}
        safe=whatsapp_ai.review(s,context,'These family pages confirm your exact washing machine model and prove its motor has failed.',{'needs_staff':False})
        assert not safe,'Unconfirmed product-family matches must not become a certain diagnosis'
        observed['unsupported_diagnosis_rejected']=context.get('_review_feedback')
    (folder/'results.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(observed,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
