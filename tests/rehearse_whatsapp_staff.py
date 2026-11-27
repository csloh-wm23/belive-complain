"""Manual genuine-Hermes rehearsal with fictional customers; never sends to Meta."""
import json
from pathlib import Path
import re
import secrets
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.settings import load_settings
from belive.workspace import selected_database
from belive.service import Service
from belive import whatsapp as wa,whatsapp_ai
from test_backend import FakeAI

def understand(service):
    props={k:{'type':'string'} for k in ('malay_request','english_request','chinese_request','xpe_meaning','xde_meaning','u_meaning')};props['does_xpe_confirm_repair']={'type':'boolean'}
    result=whatsapp_ai.ask(service,'Language Understanding Agent',
        'Internal comprehension check. These are THREE INDEPENDENT messages, not one conversation. '
        'Use English for the three summaries. malay_request must summarise ONLY ms, english_request '
        'must summarise ONLY en, and chinese_request must summarise ONLY zh. Do not combine or '
        'translate all three messages into each field. Preserve negation and what the sender asks. '
        'Explain xpe and xde in full Malay words, and u in full English. Does xpe alone prove repair?',
        {'independent_test_messages':[
            {'id':'ms','text':'sy xde wifi skrg, u blh tolong? xpe if kena tunggu.'},
            {'id':'en','text':"u said reset b4, but it still wont connect. pls dont repeat the same thing."},
            {'id':'zh','text':'我只是问怎么查进度，不是说问题解决了。'}]},props)
    assert 'tak apa' in result['xpe_meaning'].lower() and 'tak ada' in result['xde_meaning'].lower()
    assert 'you' in result['u_meaning'].lower() and result['does_xpe_confirm_repair'] is False
    assert 'wi' in result['malay_request'].lower() and 'reset' not in result['malay_request'].lower()
    assert 'reset' in result['english_request'].lower() and 'progress' not in result['english_request'].lower()
    assert 'progress' in result['chinese_request'].lower() and 'reset' not in result['chinese_request'].lower()
    return result

def main():
    settings=load_settings(selected_database())
    if settings.agent_engine!='hermes' or settings.llm_provider!='openai' or not settings.llm_api_key:raise RuntimeError('Configure the native Hermes/OpenAI connection first')
    folder=ROOT/'data'/'staff-support-rehearsal'/secrets.token_hex(4);folder.mkdir(parents=True)
    service=Service(folder/'qa.db',FakeAI());service.settings=settings
    if '--language-only' in sys.argv:
        result=understand(service)
        (folder/'language-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS: independent Malay, English and Chinese messages, negation and abbreviations. '+json.dumps(result,ensure_ascii=True),flush=True)
        return
    def rows(kind):
        with service.store.connect() as db:return service.store.all(db,kind)
    def incoming(text):return service.command('wa_simulate',{'customer':'fictional-staff-rehearsal','text':text},secrets.token_hex(16))
    def report(label):
        out=rows('wa_outgoing')[0]
        assert out['status']=='SIMULATED' and out.get('native_reply_verified'),out.get('error','Native reply missing')
        result={k:out.get(k) for k in ('status','text','staff_draft','request_id','reply_to_message_id','delivery_kind','native_reply_verified')}
        print(label+': '+json.dumps(result),flush=True);return result
    results={}
    with patch('belive.whatsapp.request_json',side_effect=AssertionError('No real WhatsApp sends in this rehearsal')), \
         patch('belive.whatsapp_ai.research',return_value={'summary':'No verified public information settles this fictional private visitor approval. Ask staff for the applicable decision.','sources':[]}):
        first=incoming('sy nk sepupu stay dlm bilik malam ni. blh approve? agreement x tulis pasal ni.')
        wa.process_thread(service,first['thread_id']);results['malay_staff_request']=report('Malay request')
        request=rows('wa_staff')[0];assert request['status']=='OPEN'
        service.command('wa_staff_reply',{'thread_id':request['thread_id'],'request_id':request['id'],'request_revision':request['revision'],
            'guidance':'Ask the visitor date and how many nights first. The overnight visit is not approved yet. Staff will review the request once those details are provided. Do not promise approval.',
            'confirmed':True},secrets.token_hex(16))
        incoming('While waiting, what can u check on ur own phone before reporting a Wi-Fi fault?')
        wa.process_thread(service,first['thread_id'])
        outputs=rows('wa_outgoing');staff=next(o for o in outputs if o.get('request_id')==request['id'])
        phone=next(o for o in outputs if o['id']!=staff['id'] and o['id']!=outputs[-1]['id'])
        assert phone['status']=='SIMULATED' and phone['native_reply_verified'] and not phone.get('request_id')
        assert staff['status']=='SIMULATED' and staff['reply_to_message_id']==request['origin_message_id']
        assert not any(r['status']=='OPEN' for r in rows('wa_staff'))
        results['english_phone_question']={k:phone.get(k) for k in ('text','status','reply_to_message_id','native_reply_verified')}
        results['malay_staff_relay']=report('Staff-guided quoted Malay reply')
        incoming('先不说访客，我只是想问：手机连不上WiFi时，我自己可以先检查什么？')
        wa.process_thread(service,first['thread_id']);results['chinese_question']=report('Chinese question')
        assert re.search(r'[\u4e00-\u9fff]',results['chinese_question']['text'])
        assert results['chinese_question']['request_id'] is None
        assert rows('case')[0]['status']!='CLOSED'
        results['understanding']=understand(service)
        results['native_executions']=[{k:x.get(k) for k in ('engine','agent_class','role','api_calls')} for x in rows('native_execution')]
        assert all(x['engine']=='hermes-native' and x['agent_class']=='run_agent.AIAgent' and x['api_calls']>0 for x in results['native_executions'])
        (folder/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS: native issue separation, quoted staff relay and multilingual understanding. '+str(folder/'results.json'),flush=True)

if __name__=='__main__':main()
