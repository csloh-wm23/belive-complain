"""Compare one actual question with and without relevant, approved case experience."""
from belive.store import bounded,now
from belive import relevance


def writing_tips(service,db,question):
    from belive.reply_learning import matching
    return [{k:x.get(k) for k in ('id','tip','case_id','sample_data','reviewed_at')} for x in matching(service,db,question)]


def lesson_text(item):
    answer=item['experience']['answer'] if item.get('experience') else ''
    tip=item.get('writing_tip',{}).get('tip','') if item.get('writing_tip') else ''
    return answer+('\n\nWriting improvement tip: ' if answer and tip else '')+tip


def experiences(service,db):
    approved=service.public_lessons(db)
    feedback={f['id']:f for f in service.store.all(db,'feedback')}
    result=[]
    for key,(question,answer) in approved.items():
        case=service.store.get(db,'case',feedback[key]['case_id'])
        category=case['category']
        if category=='OTHER':
            topics=relevance.domains(question)
            mapping={'wifi':'WIFI','water_pressure':'UTILITIES','air_conditioning':'MAINTENANCE','refrigerator':'MAINTENANCE','washer':'MAINTENANCE','cleaning':'CLEANING','access':'ACCESS','billing':'BILLING','rules':'HOUSE_RULES'}
            category=next((mapping[topic] for topic in sorted(topics) if topic in mapping),'OTHER')
        result.append({'id':key,'question':question,'answer':answer,'case_id':case['id'],
                       'category':category,'sample_data':relevance.sample_case(case),
                       'provenance':'Sample / test complaint experience' if relevance.sample_case(case) else 'Staff-approved complaint experience'})
    return result


def command(service,db,name,p):
    from belive.service import require,uid,risk
    from belive.learning import SCENARIOS
    if name=='learning_start':
        require(service.ai.readiness(),'Configure the AI model in Setup before running the comparison')
        category=p.get('category','OTHER')
        require(category in SCENARIOS,'Choose a supported practice topic')
        question=bounded(p.get('question') or SCENARIOS[category][1],10,1000)
        require(not risk(question),'Use Complaints for immediate safety risks; this comparison never contacts staff or customers')
        candidates=experiences(service,db)
        requested=p.get('experience_id')
        relevant=[x for x in candidates if relevance.match_score(question,x['question'])>0]
        relevant.sort(key=lambda x:relevance.match_score(question,x['question']),reverse=True)
        if requested:
            selected=next((x for x in relevant if x['id']==requested),None)
            require(selected is not None,'That approved experience does not match this question. Select a relevant lesson or change the question.')
        else:selected=relevant[0] if relevant else None
        tips=writing_tips(service,db,question)
        item={'id':uid('LEARN'),'mode':'experience','status':'BASELINE_QUEUED','question':question,'category':category,
              'experience':selected,'writing_tip':tips[0] if tips else None,'at':now(),'baseline':None,'improved':None,'lesson':'','revision':1,
              'demo_only':bool((selected and selected['sample_data']) or (tips and tips[0]['sample_data']))}
    else:
        item=service.store.get(db,'learning_run',p.get('id'))
        require(item['status']=='BASELINE_READY','Finish the first reply before applying experience')
        require(p.get('confirmed') is True,'Review and approve the matched complaint experience first')
        selected=item.get('experience')
        tip=item.get('writing_tip')
        require(selected is not None or tip is not None,'No relevant approved complaint experience or feedback-derived writing tip matched this question. No default writing tip will be applied.')
        require(not selected or selected in experiences(service,db),'The approved experience changed or was revoked. Start a new comparison.')
        require(not tip or tip in writing_tips(service,db,item['question']),'The approved writing tip changed or was revoked. Start a new comparison.')
        lesson=lesson_text(item)
        require(p.get('lesson',lesson)==lesson,'Use the approved experience as saved; review corrections on the source complaint first')
        item.update(lesson=lesson,status='IMPROVED_QUEUED',revision=item['revision']+1,reviewed_by=p.get('_actor','operator'),reviewed_at=now())
    service.store.put(db,'learning_run',item)
    service.store.event(db,item['id'],name.upper(),'Approved complaint-experience comparison; no customer message sent')
    return {'id':item['id'],'status':item['status']}


def execute(service,run_id):
    from belive.ai import SupportAI,failure_code
    with service.lock,service.store.connect() as db:
        run=service.store.get(db,'learning_run',run_id)
        if run['status'] not in {'BASELINE_QUEUED','IMPROVED_QUEUED'}:return
        baseline=run['status']=='BASELINE_QUEUED';revision=run['revision']
        run['status']='BASELINE_RUNNING' if baseline else 'IMPROVED_RUNNING';service.store.put(db,'learning_run',run)
    stage='baseline' if baseline else 'improved'
    selected=None if baseline else run.get('experience')
    tip=None if baseline else run.get('writing_tip')
    ai=SupportAI(service.settings,service.store.path.parent/'hermes_memory/experience-comparison'/run_id/stage) if isinstance(service.ai,SupportAI) else service.ai
    try:
        guidance=selected
        if tip:guidance={**(selected or {'question':run['question'],'answer':''}),'writing_tip':tip['tip']}
        reply=ai.experience_reply(run['question'],guidance)
        value={'response':reply,'at':now(),'real_model':isinstance(ai,SupportAI),
               'experience_id':selected['id'] if selected else None,'experience_used':selected,
               'writing_tip_used':tip,
               'checks':{'safety_review_passed':True,'location_relevant':not relevance.unnecessary_location(reply,run['question'])}}
        if not value['checks']['location_relevant']:raise ValueError('AI_UNNECESSARY_LOCATION')
        error=''
    except Exception as exc:value=None;error=failure_code(exc)
    with service.lock,service.store.connect() as db:
        current=service.store.get(db,'learning_run',run_id)
        if current['revision']!=revision or (run.get('experience') and run['experience'] not in experiences(service,db)) or (run.get('writing_tip') and run['writing_tip'] not in writing_tips(service,db,run['question'])):
            current.update(status='STALE',error='The approved experience changed or was revoked. Start a new comparison.')
        elif error:current.update(status='FAILED',error=error)
        else:
            current[stage]=value;current['status']='BASELINE_READY' if baseline else 'COMPLETE'
            if not baseline:current['comparison_note']='Compare relevance and helpfulness yourself. Supplying approved experience does not prove the second answer is better. No formatting score or duplicate lesson is created.'
        service.store.put(db,'learning_run',current)
        service.store.event(db,run_id,'LEARNING_'+current['status'],'Actual question and approved experience; no retraining or automatic improvement claim')
