"""Isolated real-model comparison of replies before and after reviewed style feedback."""
import re
from copy import deepcopy
from pathlib import Path
from belive.store import bounded,now,redact
from belive.ai import SupportAI,failure_code
from belive import automation,demo

LESSON=('Use two short numbered points, starting with 1. and 2. Put one safe check in the first point and one short clarifying question in the second. '
        'Keep the whole reply below 90 words. Use only the approved facts and safe steps. Never claim the issue is fixed.')
QUESTION='How can I check a Wi-Fi connection problem on my device?'

def score(text):
    points=re.findall(r'(?m)^\s*(\d)[.)]\s+\S',text)
    checks={'numbered_steps':points==['1','2'] and bool(re.match(r'^\s*1[.)]\s',text)),
            'one_question':text.count('?')+text.count('？')==1,
            'short_reply':len(text.split())<=90}
    return {'checks':checks,'passed':sum(checks.values()),'total':len(checks),'word_count':len(text.split())}

def command(service,db,name,p):
    if name=='lesson_revoke':
        item=service.store.get(db,'learned_style',p.get('id'));item['active']=False
        service.store.put(db,'learned_style',item);service.store.event(db,item['id'],'LESSON_REVOKED','Excluded from future replies')
        return {'revoked':True}
    if name=='learning_start':
        if not service.ai.readiness():raise ValueError('Configure the real AI model in Setup before running the comparison')
        if not demo.info(service,db)['available']:raise ValueError('Prepare the fictional demo in Setup first')
        question=bounded(p.get('question') or QUESTION,10,1000)
        from belive.service import risk,uid
        if risk(question) or automation.exception_reason(question):raise ValueError('Use a safe informational question for this fictional learning test')
        answers=[a for a in automation.active_answers(service.store,db) if a['condo_id']==demo.PROPERTY and a.get('kind')=='GUIDANCE' and a['category']=='WIFI' and a['language']=='en']
        if not answers:raise ValueError('An approved English demo Wi-Fi guide is needed')
        guide=answers[0];run_id=uid('LEARN')
        context={'case':{'title':'Fictional learning practice','description':question,'category':'WIFI','severity':'LOW'},
            'tenant_verified':True,'condo_rules':'Fictional local support practice only.',
            'conversation':[{'sender':'TENANT','text':question}],
            'verified_records':[{'id':guide['id'],'version':guide['version'],'source':guide['source'],'text':guide['answer'],'knowledge':True}],
            'approved_answers':[guide],'automatic':{'input_id':run_id,'policy_version':0}}
        item={'id':run_id,'status':'BASELINE_QUEUED','question':question,'context':context,'at':now(),
              'baseline':None,'improved':None,'lesson':'','revision':1,'demo_only':True}
    else:
        item=service.store.get(db,'learning_run',p.get('id'))
        if item['status']!='BASELINE_READY':raise ValueError('Finish the first reply before applying a lesson')
        if p.get('confirmed') is not True:raise ValueError('Review and approve the style lesson first')
        item.update(lesson=redact(bounded(p.get('lesson'),8,320)),status='IMPROVED_QUEUED',revision=item['revision']+1,
                    reviewed_by=p.get('_actor','operator'),reviewed_at=now())
    service.store.put(db,'learning_run',item)
    service.store.event(db,item['id'],name.upper(),'Isolated fictional comparison; no tenant reply is published')
    return {'id':item['id'],'status':item['status']}

def execute(service,run_id):
    with service.lock,service.store.connect() as db:
        run=service.store.get(db,'learning_run',run_id)
        if run['status'] not in {'BASELINE_QUEUED','IMPROVED_QUEUED'}:return
        baseline=run['status']=='BASELINE_QUEUED';revision=run['revision']
        run['status']='BASELINE_RUNNING' if baseline else 'IMPROVED_RUNNING'
        service.store.put(db,'learning_run',run)
    stage='baseline' if baseline else 'improved'
    examples=[] if baseline else [{'id':run_id+'-APPROVED','text':run['lesson']}]
    # The comparison has its own native memory and never overwrites operational examples.
    ai=SupportAI(service.settings,service.store.path.parent/'hermes_memory/learning-demo'/run_id/stage) if isinstance(service.ai,SupportAI) else service.ai
    try:
        result=ai.analyse(deepcopy(run['context']),examples)
        if not result.get('guidance_review_passed') or not result.get('response'):
            raise ValueError('AI_UNGROUNDED_GUIDANCE')
        value={'response':result['response'],'score':score(result['response']),
               'agent_trace':result.get('agent_trace',[]),'learning_used':result.get('learning_used',{'count':len(examples)}),
               'guide_id':run['context']['approved_answers'][0]['id'],'real_model':isinstance(ai,SupportAI),'at':now()}
        error=''
    except Exception as exc:value=None;error=failure_code(exc)
    with service.lock,service.store.connect() as db:
        current=service.store.get(db,'learning_run',run_id)
        guide=service.store.get(db,'answer',run['context']['approved_answers'][0]['id'])
        if current['revision']!=revision or guide!=run['context']['approved_answers'][0]:
            current.update(status='STALE',error='Knowledge or lesson changed; start a new comparison')
        elif error:current.update(status='FAILED',error=error)
        else:
            current[stage]=value
            current['status']='BASELINE_READY' if baseline else 'COMPLETE'
            if not baseline:
                current['change']=value['score']['passed']-current['baseline']['score']['passed']
                before=current['baseline']['score'];after=value['score']
                current['words_saved']=before['word_count']-after['word_count']
                current['improved_clarity']=current['change']>0 or (after['passed']==after['total'] and before['passed']==after['passed'] and 12<=after['word_count']<=before['word_count']*.8)
                if current['improved_clarity']:
                    lesson={'id':run_id+'-STYLE','text':run['lesson'],'verdict':'CORRECTED','active':True,
                            'scope_condo':demo.PROPERTY,'source_run':run_id,'reviewed_by':run['reviewed_by'],'at':now()}
                    service.store.put(db,'learned_style',lesson)
                    current['adopted_lesson_id']=lesson['id']
                    service.store.event(db,lesson['id'],'DEMO_LESSON_LEARNED','Reviewed style; improved this comparison; fictional property only')
        service.store.put(db,'learning_run',current)
        service.store.event(db,run_id,'LEARNING_'+current['status'],'Measured clarity checks only; no overall accuracy or retraining claim')

def public(item):
    return {k:v for k,v in item.items() if k!='context'}
