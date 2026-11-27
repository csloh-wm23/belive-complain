"""Validated WhatsApp assessment and the shared complaint-level sending policy."""
from belive.ai import CATEGORIES
from belive.store import bounded
from belive.workflow import complaint_level


def assess(service, context):
    from belive.whatsapp_ai import ask
    from belive import photo_context
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
        'research':{'type':'string','enum':['NONE','COMPANY','TECHNICAL']},
        'search_query':{'type':'string'},
        'use_prior_device_context':{'type':'boolean'},
        'research_purpose':{'type':'string','enum':['GUIDANCE','IDENTIFICATION']},
        'unavailable_details':{'type':'array','items':{'type':'string','enum':['BRAND','MODEL','LABEL','CLEARER_PHOTO']}},
    }
    props.update(photo_context.properties(context))
    result=ask(service,'Complaint Analysis Agent',
        'Assess the latest customer intent in this conversation, including relevant earlier facts and photo observations. '
        'Distinguish a complaint about an actual problem from an enquiry, greeting, thanks or unrelated content. '
        'Choose the support category by meaning. LOW/SIMPLE covers safe information or clarification. '
        'MEDIUM/MODERATE covers faults needing investigation, physical repairs, account decisions or explicit staff help. '
        'HIGH covers serious sustained loss of essential services, repeated unresolved reports, serious access/security '
        'issues or major impact. CRITICAL means immediate danger. Do not infer tenant blame. '
        'Explain the level using facts actually reported. Select a customer evidence_index; the app extracts its exact '
        'message. Missing repair details alone do not make a physical fault SIMPLE. Separately decide '
        'whether an official public lookup could help with the NEXT step before handing off. '
        'Use research TECHNICAL with a generic brand/model/code/topic query when reliable public '
        'guidance is missing for an identified safe technical question. research_purpose '
        'IDENTIFICATION means search visible product-line words, distinctive panel labels '
        'and other non-private photo clues to find candidate devices in official sources. '
        'Unknown brand/model does NOT block this identification lookup. If the customer '
        'cannot supply them or cannot find a label, use the available clues rather than '
        'asking the same question again. GUIDANCE is for an already identified device or '
        'public support question. Prefer distinctive series/badge wording among the '
        'identification_clues; do not concatenate every generic programme name into a '
        'long search query. unavailable_details lists details explicitly unavailable '
        'or already requested but the customer could not supply; never invent that '
        'a detail is unavailable just because it has not been asked yet. GUIDANCE is for an identified device or '
        'public question. Recent research_history is scoped to a photo; reuse it when '
        'nothing relevant changed rather than requesting the same lookup. New confirmed '
        'device facts or a genuinely different identification clue may justify a refined lookup. '
        'public support question. An identification candidate is not a confirmed device. '
        'Use COMPANY only for missing '
        'public company information. Actual physical damage/repair, danger or private payment '
        'exceptions are not solved by a lookup. An earlier AI handover is not proof that a '
        'newly clarified issue cannot be helped with safe public guidance. Use approved SOP first; '
        'never search private contract conflicts or override a rule. Queries must exclude '
        'customer identities, contacts, locations, SOP text and private case details. Set an '
        'empty query for NONE. For a current photo, use_prior_device_context is true '
        'ONLY if the customer explicitly says it is the earlier device or quotes a '
        'message identifying that device. Another appliance photo in the same chat '
        'is not itself a link. Otherwise set false, so earlier device identifiers '
        'and unrelated staff instructions are excluded from the photo reply. '
        'For a follow-up about a photo, select photo_message_id and the relevant '
        'photo_context_message_ids, including earlier customer confirmations about that '
        'photo. If the customer typed the displayed code, return confirmed_error_code '
        'and its code_confirmation_message_id; the application validates the literal '
        'customer evidence. Never treat OCR or an AI answer as typed confirmation. '
        'A customer-typed code takes priority over tentative E/F or similar OCR readings. '
        'Do not give a customer reply or invent actions.',
        {'conversation':conversation,'current_photo':context.get('current_photo'),'research_history':context.get('research_history',[]),'current_message':context.get('current_message',{}),'sop':context.get('sop',[]),'explicit_staff_requested':context.get('explicit_staff_requested',False),
         'photo_confirmation_required':context.get('photo_confirmation_required',False)},props)
    if result['report_type'] not in {'COMPLAINT','ENQUIRY','NON_SUPPORT'} or result['category'] not in CATEGORIES:
        raise ValueError('Invalid complaint assessment')
    if result['severity'] not in {'LOW','MEDIUM','HIGH','CRITICAL'} or type(result['uncertainty']) is not bool:
        raise ValueError('Invalid complaint level')
    if type(result['evidence_index']) is not int or result['evidence_index'] not in customer_indexes:
        raise ValueError('Invalid complaint evidence')
    if result.get('research') not in {'NONE','COMPANY','TECHNICAL'}:raise ValueError('Invalid assessment research decision')
    result['search_query']=bounded(result.get('search_query',''),0 if result['research']=='NONE' else 1,300)
    if result['research']=='NONE' and result['search_query']:raise ValueError('Unused assessment research query')
    if type(result.get('use_prior_device_context',False)) is not bool:raise ValueError('Invalid photo context decision')
    if result.get('research_purpose','GUIDANCE') not in {'GUIDANCE','IDENTIFICATION'}:raise ValueError('Invalid research purpose')
    photo_context.validate(result,context)
    unavailable=result.get('unavailable_details',[])
    if not isinstance(unavailable,list) or any(x not in {'BRAND','MODEL','LABEL','CLEARER_PHOTO'} for x in unavailable) or len(set(unavailable))!=len(unavailable):raise ValueError('Invalid unavailable detail')
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


def greeting(question):
    return {'report_type':'ENQUIRY','relevance':'SUPPORT','category':'OTHER','severity':'LOW',
        'summary':'Greeting with no support issue or operational request.',
        'level_reason':'Strict greeting-only input and conversation checks passed; no business facts or actions are authorised.',
        'uncertainty':False,'evidence':question,'requires_human':False,'complaint_level':'SIMPLE',
        'agent_trace':[{'role':'Greeting eligibility check','status':'COMPLETED'}]}


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
    """Allow reviewed clarification/guidance; preserve urgent and staff-only action gates."""
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
    # An already-open team request does not prohibit separately reviewed public
    # technical guidance. Keep that request open; never claim staff work is done.
    existing_issue=any(x.get('id')==draft.get('related_request_id') and x.get('status')=='OPEN' for x in context.get('support_requests',[]))
    public_evidence=set(draft.get('sources_used',[])) & {x['id'] for x in context.get('research_sources',[]) if x.get('kind')=='TECHNICAL'}
    private_policy=context.get('sop_lookup_uncertain') or any(x.get('policy')=='CONFLICT_REVIEW' for x in context.get('sop',[]))
    # Verified instructions remain usable when the customer answers their next
    # question; uncertainty about the fault alone must not reopen that task.
    related=draft.get('related_request_id')
    verified_ids={g['id'] for g in context.get('staff_guidance',[]) if g.get('verified_solution')}
    continuing_verified=any(r.get('id')==related and r.get('status')=='ANSWERED' for r in context.get('support_requests',[]))
    checked_work={r['id'] for r in context.get('staff_work_updates',[]) if r.get('state') in {'ACCEPTED','IN_PROGRESS','BLOCKED','WORK_DONE'}}
    active_work=any(r.get('id')==related and r.get('status') in {'OPEN','ANSWERED'} for r in context.get('support_requests',[]))
    if (not needs_staff and not private_policy and not context.get('explicit_staff_requested')
            and assessment['severity'] in {'LOW','MEDIUM','HIGH'} and draft.get('handling') in {'ANSWER','CLARIFY'}
            and active_work and related in checked_work and related in draft.get('sources_used',[])):
        return assessment,draft,'VERIFIED_STAFF_GUIDANCE',None
    if (not needs_staff and not private_policy and not context.get('explicit_staff_requested')
            and assessment['severity'] in {'LOW','MEDIUM'} and draft.get('handling') in {'ANSWER','CLARIFY'}
            and continuing_verified and related in verified_ids and related in draft.get('sources_used',[])):
        return assessment,draft,'VERIFIED_STAFF_GUIDANCE',None
    if needs_staff and existing_issue and public_evidence and not private_policy and not context.get('explicit_staff_requested') and assessment['severity'] in {'LOW','MEDIUM'}:
        return assessment,draft,'REVIEWED_TEAM_GUIDANCE',None
    if not needs_staff and not context.get('explicit_staff_requested') and assessment['severity'] in {'LOW','MEDIUM'}:
        if draft.get('handling')=='CLARIFY':
            return assessment,draft,'CLARIFICATION',None
        cited=set(draft.get('sources_used',[]))
        researched={x['id'] for x in context.get('research_sources',[])}
        supported=set(researched)
        supported|={x['id'] for x in context.get('sop',[]) if x.get('policy')=='GENERAL_GUIDANCE'}
        supported|={x['id'] for x in context.get('approved_experiences',[])}
        # Uncertainty about the underlying fault is not automatically uncertainty
        # about a bounded next step supported by freshly retrieved official evidence.
        # Keep the unresolved assessment and require independent public-reply review.
        grounded_next_step=not assessment['uncertainty'] or (context.get('research_attempted') and bool(cited & researched))
        if draft.get('handling')=='ANSWER' and grounded_next_step and cited & supported:
            return assessment,draft,'REVIEWED_GUIDANCE',None
    if assessment['severity']!='LOW' or assessment['uncertainty'] or context.get('explicit_staff_requested'):
        original=draft['reply']
        draft.update(reply=draft.get('handover_reply') or acknowledgement(assessment.get('evidence',''),assessment['severity'] in {'HIGH','CRITICAL'}),
                     needs_staff=True,handling='TEAM',staff_question=draft['staff_question'] or assessment['level_reason'])
        assessment['requires_human']=True
        return assessment,draft,'ACKNOWLEDGEMENT',original
    if context.get('waiting_for_staff') or context.get('ongoing_support'):
        # Keep the reviewed low-risk conversation going without treating an
        # unresolved staff handover as a completed SIMPLE case.
        return assessment,draft,'ACKNOWLEDGEMENT',None
    return assessment,draft,'SIMPLE',None
