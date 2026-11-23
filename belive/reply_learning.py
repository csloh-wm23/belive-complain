"""Learn reviewed communication improvements from actual post-reply customer feedback."""
import re
from belive.store import now,bounded,digest,redact
from belive import relevance
from belive.conversations import conversation


def negative(text):
    return bool(re.search(r"still (?:not|unresolved|broken|doesn|happening)|(?:didn.t|doesn.t|not) help|not (?:resolved|fixed|working|helpful)|already (?:told|tried|said)|keep (?:repeating|complaining)|same (?:answer|reply|problem)|wrong answer|answer.{0,15}wrong|not what I asked|don.t understand|you (?:misunderstood|didn.t understand)|why.{0,30}room number|没解决|还没好|一直重复|没帮助|还是不行",text,re.I))


def add(service,db,case,reply,customer,question,*,signal=True,explicit_unresolved=False):
    key='RLF-'+digest(case['id']+':'+reply['id']+':'+customer['id'])[:18]
    if any(x['id']==key for x in service.store.all(db,'reply_learning')):return
    condo=None;sample=relevance.sample_case(case)
    if case.get('tenant_id'):
        tenant=service.store.get(db,'tenant',case['tenant_id']);condo=tenant['condo_id'];sample=sample or tenant.get('demo_only',False)
    item=dict(id=key,case_id=case['id'],question=redact(question),reply=redact(reply['text']),
              customer_feedback=redact(customer['text']),reply_id=reply['id'],feedback_id=customer['id'],
              category=case['category'],scope_condo=condo,sample_data=sample,status='PENDING',approved=False,
              revision=1,at=now(),tip='',reason='',cause='',preview=None,
              signal=signal,explicit_unresolved=explicit_unresolved,reaction='',tone='')
    service.store.put(db,'reply_learning',item)
    action = 'REPLY_FEEDBACK_CAPTURED' if signal else 'CUSTOMER_REACTION_QUEUED'
    service.store.event(db,case['id'],action,key+': reply and customer follow-up saved for review')


def discover(service,db,case_id=None):
    for case in service.store.all(db,'case'):
        if case_id and case['id']!=case_id:continue
        last_reply=None;question=case['description'];before_reply=question
        for message in conversation(service.store,db,case):
            if message['sender'] in {'SUPPORT','AI_SUPPORT'}:
                last_reply=message;before_reply=question
            elif message['sender']=='TENANT':
                explicitly_unresolved=case.get('tenant_resolution',{}).get('resolved') is False and case['tenant_resolution'].get('note')==message['text']
                signal = negative(message['text']) or explicitly_unresolved
                inspect_reaction = case_id is not None and getattr(service.ai,'checks_feedback_reactions',False)
                if last_reply and (signal or inspect_reaction):
                    add(service,db,case,last_reply,message,before_reply,
                        signal=signal,explicit_unresolved=explicitly_unresolved)
                question=message['text']


def matching(service,db,question,condo_id=None):
    from belive import automation
    from belive import shared_memory
    results=[]
    common=shared_memory.enabled(service,db)
    items=shared_memory.tips(service,db) if common else service.store.all(db,'reply_learning')
    for item in items:
        if not item.get('approved') or item['status']!='APPROVED' or (not common and item.get('scope_condo')!=condo_id):continue
        score=relevance.match_score(question,item['question'])
        general=not relevance.domains(item['question']) and item['category']=='OTHER' and not relevance.domains(question) and not automation.exception_reason(item['question']) and relevance.location_scope(item['question'])=='NONE'
        if score>0 or general:results.append(item)
    return results[:3]


def command(service,db,name,p):
    from belive.service import require
    if name=='reply_learning_scan':
        discover(service,db)
        return {'captured':len(service.store.all(db,'reply_learning'))}
    item=service.store.get(db,'reply_learning',p.get('id'))
    require(item['revision']==p.get('revision'),'Feedback changed; refresh before acting')
    action=p.get('action')
    if action=='analyse':
        require(not item.get('approved'),'Revoke an approved tip before reanalysing it')
        item.update(status='PENDING',error='')
    elif action=='approve':
        require(item['status']=='PROPOSED','Analyse the customer feedback before approving a tip')
        require(p.get('confirmed') is True,'Review this as reusable writing advice with no private facts or unverified promises')
        tip=bounded(p.get('tip'),8,1000)
        require(not re.search(r'\[(?:email|number) removed\]|password|\botp\b|bank account|guarantee|we (?:have |will )(?:repaired|refunded)|密码',tip,re.I),'Use general writing advice; exclude private facts, secrets and promises')
        item.update(tip=tip,status='APPROVAL_QUEUED',approved=False,reviewed_by=p.get('_actor','operator'),reviewed_at=now(),error='')
    elif action=='revoke':item.update(status='REJECTED',approved=False,preview_status=None)
    elif action=='test':
        require(item.get('approved') and item['status']=='APPROVED','Approve the improvement tip before testing it')
        item.update(preview_status='QUEUED',preview=None,error='')
    else:raise ValueError('Choose analyse, approve, test or revoke')
    item['revision']+=1;service.store.put(db,'reply_learning',item)
    service.store.event(db,item['case_id'],'REPLY_LEARNING_'+action.upper(),item['id'])
    return item


def execute(service,item_id):
    from belive.ai import failure_code,SupportAI
    with service.lock,service.store.connect() as db:
        item=service.store.get(db,'reply_learning',item_id)
        testing=item.get('preview_status')=='QUEUED' and item.get('approved')
        approving=item['status']=='APPROVAL_QUEUED'
        if not testing and not approving and item['status']!='PENDING':return
        if testing:item['preview_status']='RUNNING'
        else:item['status']='REVIEWING' if approving else 'ANALYSING'
        item['revision']+=1;revision=item['revision'];service.store.put(db,'reply_learning',item)
        from belive.experience_learning import experiences
        relevant=[x for x in experiences(service,db) if relevance.match_score(item['question'],x['question'])>0]
        experience=relevant[0] if relevant else {'question':item['question'],'answer':''}
    error='';error_type='';value=None
    ai=SupportAI(service.settings,service.store.path.parent/'hermes_memory/reply-feedback'/item_id) if isinstance(service.ai,SupportAI) else service.ai
    try:
        if testing:
            value=ai.experience_reply(item['question'],{**experience,'writing_tip':item['tip'],
                'conversation_feedback':{'previous_reply':item['reply'],'customer_followup':item['customer_feedback']}})
        elif approving:
            if not ai.review_writing_tip(item['tip']):raise ValueError('AI_UNSAFE_TIP')
            value=True
        else:
            value=ai.reply_improvement(item['question'],item['reply'],item['customer_feedback'])
            if value.get('cause') not in {'COMMUNICATION','SERVICE_ACTION','UNCLEAR'}:raise ValueError('Invalid feedback diagnosis')
            reaction = value.get('reaction','DISSATISFIED')
            tone = value.get('tone','UNCLEAR')
            if (reaction not in {'DISSATISFIED','POSITIVE','NEUTRAL','UNCLEAR'}
                    or tone not in {'ANGRY','FRUSTRATED','CALM','UNCLEAR'}):
                raise ValueError('Invalid customer reaction')
            if item.get('explicit_unresolved'):
                reaction = 'DISSATISFIED'
            value={'cause':value['cause'],'reason':bounded(value.get('reason'),8,1500),
                   'reaction':reaction,'tone':tone,
                   'tip':bounded(value.get('tip'),8,1000) if reaction=='DISSATISFIED' and value.get('tip') else ''}
    except Exception as exc:
        error=failure_code(exc)
        error_type=type(exc).__name__
    with service.lock,service.store.connect() as db:
        current=service.store.get(db,'reply_learning',item_id)
        if current['revision']!=revision:return
        current.pop('error_type',None)
        if error:
            if testing:current['preview_status']='FAILED'
            else:current.update(status='PROPOSED' if approving else 'FAILED',approved=False)
            current['error']=error
            current['error_type']=error_type
        elif testing:
            current.update(preview_status='READY',preview=value,preview_at=now(),comparison_note='Original published reply versus a new draft using reviewed feedback. This test does not prove resolution or improvement; compare helpfulness and observe later customer feedback.')
        elif approving:current.update(status='APPROVED',approved=True,error='')
        else:
            dissatisfied = value['reaction']=='DISSATISFIED'
            status = 'PROPOSED' if dissatisfied and value['tip'] else 'OBSERVED'
            current.update(status=status,signal=dissatisfied,**value,error='')
        current['revision']+=1;service.store.put(db,'reply_learning',current)
        service.store.event(db,current['case_id'],'REPLY_LEARNING_'+current['status'],current['id']+': reviewed communication feedback; not a repair claim')


def usage(service,db,case,reply_id,tips):
    if not tips or not reply_id:return
    key='USE-'+digest(case['id']+':'+reply_id)[:18]
    if any(x['id']==key for x in service.store.all(db,'reply_tip_usage')):return
    service.store.put(db,'reply_tip_usage',dict(id=key,case_id=case['id'],reply_id=reply_id,tip_ids=[x['id'] for x in tips],at=now()))
