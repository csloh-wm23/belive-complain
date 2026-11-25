"""Opt-in native Hermes rehearsals on an isolated, labelled demonstration database.

No customer database is copied. Only the encrypted reviewed company knowledge is
restored. WhatsApp uses the production processing path with simulated senders;
the external Meta transport is blocked during every rehearsal.
"""
import argparse
import base64
import json
import re
import secrets
import struct
import sys
import zlib
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from belive.service import Service
from belive.access import Access
from belive.store import now
from belive.workspace import selected_database
from belive.settings import load_settings
from belive.hermes_native import conversation_scope,runtime_info,runtime_python
from belive import whatsapp,whatsapp_ai,repository_memory,shared_memory,learning

ACTOR='Fictional rehearsal reviewer'
QUESTION='How should I report repeated late-night noise in a shared corridor without confronting neighbours?'
GENERAL_LESSON=('For repeated late-night noise in a shared corridor, record the dates and approximate times, '
                'which shared area is affected, and whether it is happening now. Describe what you observed '
                'without posting neighbours\' names or private details. Avoid confrontation; staff can review '
                'the report against the applicable quiet-hours guidance. Do not promise enforcement or penalties.')


def safe_error(error):
    value=str(error)
    return value if (isinstance(error,AssertionError) or value.startswith(('HERMES_','AI_'))) and len(value)<160 else type(error).__name__


def rows(service,kind):
    with service.store.connect() as db:return service.store.all(db,kind)


def saved_case(service,case_id):
    with service.store.connect() as db:return service.store.get(db,'case',case_id)


def command(service,name,**payload):
    return service.command(name,{**payload,'_actor':ACTOR},secrets.token_hex(16))


def action(service,case_id,name,**payload):
    return command(service,'case_action',id=case_id,revision=saved_case(service,case_id)['revision'],action=name,**payload)


def process(service,intake):
    whatsapp.process_thread(service,intake['thread_id'])
    outputs=[x for x in rows(service,'wa_outgoing') if x['thread_id']==intake['thread_id']]
    if not outputs:raise AssertionError('No WhatsApp output was saved')
    output=outputs[0]
    if output['status'] not in {'SIMULATED','AWAITING_STAFF_REVIEW','DRAFT'}:
        raise AssertionError('The rehearsal produced an unexpected delivery status')
    if any('fallback' in step.lower() for step in output.get('steps',[])):
        raise AssertionError('The real agent path fell back; inspect the saved turn before claiming success')
    return output


def simulate(service,customer,text,image=None):
    payload=dict(customer=customer,text=text,message_id='native-rehearsal-'+secrets.token_hex(10))
    if image is not None:payload['image']='data:image/png;base64,'+base64.b64encode(image).decode()
    intake=command(service,'wa_simulate',**payload)
    return intake,process(service,intake)


def executions_since(service,started):
    return [x for x in rows(service,'native_execution') if x['at']>=started]


def setup(directory):
    directory.mkdir(parents=True,exist_ok=True)
    active_database=selected_database()
    service=Service(directory/'rehearsal.db')
    # Use the active installation's configuration only in memory. Customer rows
    # and encrypted API credentials are never copied into the rehearsal database.
    service.settings=load_settings(active_database)
    service.ai.settings=service.settings
    if service.settings.agent_engine!='hermes':raise ValueError('The rehearsal requires the native Hermes engine')
    if not service.ai.readiness():raise ValueError('Native Hermes and the model must be configured first')
    if not runtime_info().get('version'):raise ValueError('Install the pinned Hermes runtime before this rehearsal')
    if runtime_python()!=Path(runtime_info()['python']):raise ValueError('The selected runtime differs from the pinned installation')
    if not rows(service,'memory_connection'):
        recovery=active_database.parent/'knowledge-backup.key'
        repository_memory.import_key(service,recovery.read_text(encoding='ascii'))
    if not rows(service,'user'):
        password=secrets.token_urlsafe(24)
        user={'username':'native-rehearsal-admin','password':password,'name':'Fictional rehearsal admin'}
        Access(service).create(user,bootstrap=True)
        (directory/'operator-login.json').write_text(json.dumps(user,indent=2),encoding='utf-8')
    return service


def learning_rehearsal(service):
    started=now();suffix=secrets.token_hex(3)
    intake,initial=simulate(service,'noise-source-'+suffix,
        'People keep making loud noise in the shared corridor after midnight and I cannot sleep. '
        'I do not want to confront anyone. Can the team help?')
    print('Source complaint assessed; preparing verified test staff guidance.',flush=True)
    thread=next(x for x in rows(service,'wa_thread') if x['id']==intake['thread_id'])
    staff_guidance=('This is a fictional rehearsal, not a real tenant incident. The test staff member has checked '
        'the reported shared corridor and confirmed that the gathering has ended. Tell the test customer not to '
        'confront anyone. If noise returns, ask for the affected shared area, approximate time, and whether it is '
        'happening now. Do not promise enforcement, penalties or compensation.')
    command(service,'wa_staff_reply',thread_id=thread['id'],revision=thread['revision'],guidance=staff_guidance,confirmed=True)
    relay=process(service,intake)
    print('Native Hermes relayed the verified test staff guidance.',flush=True)
    source=saved_case(service,intake['case_id'])
    if source.get('draft')!=relay['text']:
        raise AssertionError('The case draft must preserve the actual AI relay before solved-case approval')
    # The staff verifies a SCRIPTED test outcome. It is never presented as a real
    # tenant resolution, and the reusable answer deliberately omits that outcome.
    action(service,source['id'],'staff_followup',note='Fictional rehearsal: the test reporter confirmed the shared-corridor noise had stopped; no real tenant outcome is claimed.')
    action(service,source['id'],'verify_staff_close',note='Fictional test outcome checked by the rehearsal reviewer. The staff-guided AI reply was delivered only in simulation.',confirmed=True)
    approved=command(service,'feedback',id=source['id'],verdict='CORRECTED',text=GENERAL_LESSON,public_question=QUESTION,publish_public=True)
    shared_memory.sync(service)
    print('The test case is verified closed and its redacted general lesson is approved.',flush=True)
    lesson_id='SHARED-'+approved['id']
    with service.store.connect() as db:
        experience=next(x for x in shared_memory.experiences(service,db) if x['id']==lesson_id)
    if experience.get('sample_data') is not True:raise AssertionError('The new lesson must retain its test provenance')
    comparison=command(service,'learning_start',category='HOUSE_RULES',question=QUESTION,experience_id=lesson_id)
    learning.execute(service,comparison['id'])
    with service.store.connect() as db:before=service.store.get(db,'learning_run',comparison['id'])
    if before['status']!='BASELINE_READY':raise AssertionError('The real baseline comparison did not complete')
    print('Real comparison baseline completed without the saved experience.',flush=True)
    command(service,'learning_improve',id=comparison['id'],confirmed=True)
    learning.execute(service,comparison['id'])
    with service.store.connect() as db:comparison_result=service.store.get(db,'learning_run',comparison['id'])
    if comparison_result['status']!='COMPLETE':raise AssertionError('The real approved-experience comparison did not complete')
    print('Real comparison completed with the approved experience; testing a later matching conversation.',flush=True)
    later_intake,later=simulate(service,'noise-match-'+suffix,
        'How should I report late-night noise in the shared corridor without confronting neighbours? '
        'What information is useful if it happens again?')
    executions=executions_since(service,started)
    checks={'native_source_reply':initial.get('native_reply_verified') is True,
        'native_staff_relay':relay.get('native_reply_verified') is True,
        'source_verified_closed':saved_case(service,source['id'])['status']=='CLOSED',
        'reviewed_general_lesson_saved':experience['enabled'] is True,
        'test_provenance_retained':experience['sample_data'] is True,
        'baseline_used_no_experience':comparison_result['baseline'].get('experience_id') is None,
        'improved_received_new_approved_experience':comparison_result['improved'].get('experience_id')==lesson_id,
        'later_native_reply':later.get('native_reply_verified') is True,
        'later_supplied_new_lesson':('experience:'+approved['id']) in later.get('shared_revisions',{}),
        'later_cited_new_lesson':lesson_id in later.get('sources',[]),
        'no_external_delivery':all(x['status'] in {'SIMULATED','AWAITING_STAFF_REVIEW','DRAFT'} for x in (initial,relay,later))}
    return {'started_at':started,'source_case':intake,'initial_response':initial,'verified_staff_guidance':staff_guidance,
        'actual_staff_guided_ai_reply':relay,'feedback':approved,'approved_experience':experience,
        'comparison':comparison_result,'later_case':later_intake,'later_reply':later,'checks':checks,
        'native_executions':executions,
        'measurement_note':'The same question was generated with and without the reviewed experience. Both are real model outputs. No automatic quality-improvement score or real customer-satisfaction result is claimed. Staff outcome/approval are explicitly scripted test actions.'}


def photo_fixture():
    width,height=520,340;pixels=bytearray([235,237,236])*(width*height)
    def rectangle(x0,y0,x1,y1,color):
        for y in range(y0,y1):
            for x in range(x0,x1):pixels[(y*width+x)*3:(y*width+x)*3+3]=bytes(color)
    glyphs={'4':['10010','10010','10010','11111','00010','00010','00010'],
            'C':['01111','10000','10000','10000','10000','10000','01111'],
            'D':['11110','10001','10001','10001','10001','10001','11110'],
            'E':['11111','10000','10000','11110','10000','10000','11111'],
            'M':['10001','11011','10101','10101','10001','10001','10001'],
            'O':['01110','10001','10001','10001','10001','10001','01110'],
            'T':['11111','00100','00100','00100','00100','00100','00100'],
            'S':['01111','10000','10000','01110','00001','00001','11110']}
    def text(value,x,y,scale,color):
        for character in value:
            if character!=' ':
                for gy,row in enumerate(glyphs[character]):
                    for gx,on in enumerate(row):
                        if on=='1':rectangle(x+gx*scale,y+gy*scale,x+(gx+1)*scale,y+(gy+1)*scale,color)
            x+=6*scale
    rectangle(24,24,496,316,(180,185,184));rectangle(40,40,480,260,(25,31,29));rectangle(105,78,414,224,(145,230,155))
    text('4C',150,95,16,(12,39,20));text('DEMO TEST',86,282,5,(27,51,40))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\x00'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


def photo_rehearsal(service,directory):
    started=now();image=photo_fixture();(directory/'synthetic-washer-display.png').write_bytes(image)
    intake,reply=simulate(service,'photo-test-'+secrets.token_hex(3),
        'This is a labelled test photo of a shared washing-machine display. What text can you read? '
        'I have not typed the code from the display. Do not diagnose or repair the machine.',image=image)
    messages=[x for x in rows(service,'wa_message') if x['thread_id']==intake['thread_id'] and x.get('vision')]
    vision=messages[0]['vision'] if messages else {}
    executions=executions_since(service,started)
    return {'started_at':started,'test_fixture':'Synthetic display image labelled DEMO TEST; not a real tenant photo.',
        'expected_visible_code':'4C','intake':intake,'vision':vision,'reply':reply,'native_executions':executions,
        'checks':{'vision_observation_saved':bool(vision),'exact_visible_text_read':bool(re.search(r'\b4C\b',vision.get('observations',''),re.I)) and '4C' in reply.get('text','').upper(),
            'photo_uncertainty_retained':vision.get('uncertain') is True,
            'native_photo_agent_ran':any(x['role']=='WhatsApp Photo Agent' and (x.get('api_calls') or 0)>0 for x in executions),
            'no_external_delivery':reply['status'] in {'SIMULATED','AWAITING_STAFF_REVIEW','DRAFT'}}}


def research_rehearsal(service):
    started=now();query='Samsung washing machine 4C error meaning and safe user checks official support'
    with conversation_scope('official-research-rehearsal-'+secrets.token_hex(4)):
        result=whatsapp_ai.research(service,query,'TECHNICAL')
    executions=executions_since(service,started)
    from urllib.parse import urlsplit
    allowed=whatsapp_ai.domains('TECHNICAL')
    return {'started_at':started,'query':query,'result':result,'native_executions':executions,
        'checks':{'native_official_research_agent_ran':any(x['role']=='Official Source Research Agent' and (x.get('api_calls') or 0)>0 for x in executions),
            'bounded_search_tool_executed':any('search_official_support' in x.get('executed_tools',[]) for x in executions),
            'citable_official_sources_found':bool(result['sources']),
            'all_sources_allowed':all(urlsplit(x['url']).scheme=='https' and any((urlsplit(x['url']).hostname or '')==d or (urlsplit(x['url']).hostname or '').endswith('.'+d) for d in allowed) for x in result['sources'])},
        'privacy_note':'Only this generic technical query reached web search. No customer conversation, contact information or SOP text was sent to web search.'}


def verify_native_evidence(service,result):
    evidence=result.get('native_executions',[]);runtime=runtime_info()
    checks=result.setdefault('checks',{})
    checks['configured_engine_is_hermes']=service.settings.agent_engine=='hermes'
    checks['official_native_identity_recorded']=bool(evidence) and all(x.get('engine')=='hermes-native' and x.get('agent_class')=='run_agent.AIAgent' for x in evidence)
    checks['pinned_runtime_version_and_commit_recorded']=bool(evidence) and all(x.get('version')==runtime.get('version') and x.get('commit')==runtime.get('commit') and bool(x.get('commit')) for x in evidence)
    checks['genuine_model_calls_recorded']=bool(evidence) and all((x.get('api_calls') or 0)>0 for x in evidence)
    result['passed']=all(checks.values())
    return result


def write_report(directory,report):
    (directory/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Native Hermes local rehearsal','',report['disclosure'],'',f"Model: {report['model']} · runtime: {report['runtime'].get('version')}", '']
    for phase,result in report['phases'].items():
        lines.extend(['## '+phase,'',json.dumps(result.get('checks',{}),indent=2),''])
        if result.get('error'):lines.extend(['Failure: '+result['error'],''])
        if result.get('native_executions'):
            calls=sum(x.get('api_calls') or 0 for x in result['native_executions'])
            roles=sorted({x.get('role','') for x in result['native_executions']})
            lines.extend(['Real native model calls: '+str(calls),'','Roles: '+', '.join(roles),''])
        if phase=='photo' and result.get('vision'):
            lines.extend([result['test_fixture'],'','Observed: '+result['vision']['observations'],'',
                          'Actual reply: '+result['reply']['text'],''])
            if result.get('assertion_correction'):lines.extend([result['assertion_correction'],''])
        if phase=='research' and result.get('result'):
            lines.extend(['Generic query: '+result['query'],'',result['result']['summary'],''])
            lines.extend(['- ['+x['title']+']('+x['url']+')' for x in result['result']['sources']])
            lines.extend(['',result['privacy_note'],''])
        if phase=='learning' and result.get('later_reply'):
            lines.extend(['### Actual staff-guided reply','',result['actual_staff_guided_ai_reply']['text'],'',
                          '### Approved general lesson','',result['approved_experience']['answer'],'',
                          '### Same-question baseline without reviewed experience','',result['comparison']['baseline']['response'],'',
                          '### Same-question reply with the reviewed experience','',result['comparison']['improved']['response'],'',
                          '### Later matching reply','',result['later_reply']['text'],'',
                          'Cited sources: '+', '.join(result['later_reply'].get('sources',[])),'',result['measurement_note'],''])
    (directory/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true',help='Opt into paid configured-model and web-search calls.')
    parser.add_argument('--phase',choices=['learning','photo','research','all'],default='all')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts'/'native-support-rehearsal')
    args=parser.parse_args()
    if not args.run_live:
        print('Prepared: isolated WhatsApp staff/learning, synthetic-photo and official-source research rehearsals. Pass --run-live to call the configured real model. No external messages are sent.')
        return
    directory=args.output.resolve()
    if not directory.is_relative_to((ROOT/'artifacts').resolve()):raise ValueError('Keep live-rehearsal data under the ignored artifacts directory')
    service=setup(directory)
    path=directory/'results.json'
    report=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {
        'created_at':now(),'disclosure':'A genuine configured-model rehearsal using a separate test database, fictional customers, scripted staff review and test outcomes. No real tenant result, model retraining or external WhatsApp delivery is claimed.',
        'runtime':runtime_info(),'model':service.settings.llm_model,'phases':{}}
    phases=['learning','photo','research'] if args.phase=='all' else [args.phase]
    failed=False
    with patch('belive.whatsapp.request_json',side_effect=AssertionError('External WhatsApp transport is prohibited in this rehearsal')):
        for phase in phases:
            print('Running '+phase+' with the real native Agent...',flush=True)
            try:
                result=learning_rehearsal(service) if phase=='learning' else photo_rehearsal(service,directory) if phase=='photo' else research_rehearsal(service)
                result=verify_native_evidence(service,result)
            except Exception as error:
                result={'passed':False,'error':safe_error(error)}
            report['phases'][phase]=result;write_report(directory,report)
            print(json.dumps({'phase':phase,'passed':result['passed'],'checks':result.get('checks'),'error':result.get('error')},ensure_ascii=True),flush=True)
            failed=failed or not result['passed']
    print('Private rehearsal evidence: '+str(directory/'results.json'),flush=True)
    if failed:raise SystemExit(1)


if __name__=='__main__':main()
