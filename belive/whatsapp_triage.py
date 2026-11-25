"""Validated WhatsApp assessment and the shared complaint-level sending policy."""
from belive.ai import CATEGORIES
from belive.store import bounded
from belive.workflow import complaint_level


def assess(service, context):
    from belive.whatsapp_ai import ask
    conversation=context['conversation']
    customer_indexes=[i for i,item in enumerate(conversation) if item['role']=='CUSTOMER' and isinstance(item.get('text'),str)]
    if not customer_indexes:
        raise ValueError('No customer message available for assessment')
    props={
        'report_type':{'type':'string','enum':['COMPLAINT','ENQUIRY','NON_SUPPORT']},
        'category':{'type':'string','enum':CATEGORIES},
        'severity':{'type':'string','enum':['LOW','MEDIUM','HIGH','CRITICAL']},
        'summary':{'type':'string'},'level_reason':{'type':'string'},
        'uncertainty':{'type':'boolean'},
        'evidence_index':{'type':'integer','enum':customer_indexes},
    }
    result=ask(service,'Complaint Analysis Agent',
        'Assess the latest customer intent in this conversation, including relevant earlier facts and photo observations. '
        'Distinguish a complaint about an actual problem from an enquiry, greeting, thanks or unrelated content. '
        'Choose the support category by meaning. LOW/SIMPLE covers safe information or clarification. '
        'MEDIUM/MODERATE covers faults needing investigation, physical repairs, account decisions or explicit staff help. '
        'HIGH covers serious sustained loss of essential services, repeated unresolved reports, serious access/security '
        'issues or major impact. CRITICAL means immediate danger. Do not infer tenant blame. '
        'Explain the level using facts actually reported. Select a customer evidence_index; the app extracts its exact '
        'message. Missing repair details alone do not make a physical fault SIMPLE. Do not give a reply or invent actions.',
        {'conversation':conversation,'photo_confirmation_required':context.get('photo_confirmation_required',False)},props)
    if result['report_type'] not in {'COMPLAINT','ENQUIRY','NON_SUPPORT'} or result['category'] not in CATEGORIES:
        raise ValueError('Invalid complaint assessment')
    if result['severity'] not in {'LOW','MEDIUM','HIGH','CRITICAL'} or type(result['uncertainty']) is not bool:
        raise ValueError('Invalid complaint level')
    if type(result['evidence_index']) is not int or result['evidence_index'] not in customer_indexes:
        raise ValueError('Invalid complaint evidence')
    result={**result,'summary':bounded(result['summary'],4,1200),'level_reason':bounded(result['level_reason'],8,1200)}
    result['evidence']=conversation[result.pop('evidence_index')]['text']
    result['relevance']='NON_SUPPORT' if result['report_type']=='NON_SUPPORT' else 'SUPPORT'
    result['requires_human']=result['uncertainty'] or result['severity']!='LOW'
    result['complaint_level']=complaint_level(result)
    result['agent_trace']=[{'role':'Complaint Analysis Agent','status':'COMPLETED'}]
    return result


def preserve_priority(assessment, previous_case, waiting_for_staff):
    previous=previous_case.get('analysis') or {}
    rank={'LOW':0,'MEDIUM':1,'HIGH':2,'CRITICAL':3}
    if waiting_for_staff and rank.get(previous.get('severity'),0)>rank[assessment['severity']]:
        assessment.update(category=previous_case['category'],severity=previous['severity'],requires_human=True)
        assessment['level_reason']+=' The previously reported issue is still waiting for staff; its priority has been retained.'
    assessment['complaint_level']=complaint_level(assessment)
    return assessment


def emergency(question):
    return {'report_type':'COMPLAINT','relevance':'SUPPORT','category':'MAINTENANCE','severity':'CRITICAL',
        'summary':'Potential immediate safety risk in the customer report.',
        'level_reason':'Immediate danger was detected before routine AI troubleshooting. Urgent staff handling is required.',
        'uncertainty':False,'evidence':question,'requires_human':True,'complaint_level':'HIGH',
        'agent_trace':[{'role':'Immediate safety screen','status':'COMPLETED'}]}


def failed(question):
    return {'report_type':'COMPLAINT','relevance':'UNCERTAIN','category':'OTHER','severity':'MEDIUM',
        'summary':'The complaint assessment could not be validated.',
        'level_reason':'AI assessment failed; staff must assess the message before substantive advice is sent.',
        'uncertainty':True,'evidence':question,'requires_human':True,'complaint_level':'MODERATE',
        'agent_trace':[{'role':'Complaint Analysis Agent','status':'FAILED'}]}


def acknowledgement(question, high=False):
    import re
    if re.search(r'[\u4e00-\u9fff]',question):
        return '收到你的反馈。我正在请工作人员优先查看这个问题，你可以继续在这里补充情况。' if high else '收到你的反馈。我正在请工作人员协助处理，你可以继续在这里补充情况。'
    if re.search(r'\b(saya|tolong|rosak|masih|tidak|belum|bilik)\b',question,re.I):
        return 'Saya terima aduan anda dan sedang meminta pasukan kami menyemaknya'+(' dengan segera' if high else '')+'. Anda boleh terus menghantar maklumat di sini.'
    return 'I received your report and am asking our team to review it'+(' as a priority' if high else '')+'. You can keep sending details in this chat.'


def apply_policy(assessment, draft, context, urgent=False):
    """Only SIMPLE advice is automatic; verified staff solutions may be relayed after review."""
    assessment=dict(assessment);draft=dict(draft)
    staff_relay=context.get('latest_sender')=='STAFF_INTERNAL' and bool(context.get('staff_guidance'))
    needs_staff=bool(draft['needs_staff'] or draft['needs_maintenance'] or context.get('explicit_staff_requested'))
    if not urgent and not staff_relay and needs_staff and assessment['severity']=='LOW':
        assessment.update(severity='MEDIUM',requires_human=True)
        assessment['level_reason']+=' Staff guidance or physical action is required for the next step.'
    if assessment['uncertainty']:
        assessment['requires_human']=True
    assessment['complaint_level']=complaint_level(assessment)
    if urgent:
        return assessment,draft,'URGENT_ACKNOWLEDGEMENT',None
    if staff_relay:
        return assessment,draft,'VERIFIED_STAFF_GUIDANCE',None
    if assessment['severity']!='LOW' or assessment['uncertainty'] or context.get('explicit_staff_requested'):
        original=draft['reply']
        draft.update(reply=acknowledgement(assessment.get('evidence',''),assessment['severity'] in {'HIGH','CRITICAL'}),
                     needs_staff=True,staff_question=draft['staff_question'] or assessment['level_reason'])
        assessment['requires_human']=True
        return assessment,draft,'ACKNOWLEDGEMENT',original
    return assessment,draft,'SIMPLE',None
