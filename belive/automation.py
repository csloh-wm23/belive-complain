"""Reviewed property knowledge and bounded, information-only portal automation."""
import re
import secrets
from datetime import datetime, timezone
from belive.store import bounded, now
from belive.conversations import post, conversation
from belive.ai import CATEGORIES as SUPPORT_CATEGORIES

CATEGORIES = set(SUPPORT_CATEGORIES)
LANGUAGES = {'en', 'ms', 'zh'}
TERMINAL = {'CLOSED', 'SKIPPED', 'VERIFIED', 'ANSWERED'}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def exception_reason(text):
    if re.search(r'\b(human|person|agent|staff|staf)\b|人工|真人', text, re.I):
        return 'Tenant requests staff assistance'
    if re.search(r'\b(refund|rent|payment|balance|bank|otp|password|unlock|locked out|broken|broke|repair|injur\w*|leak\w*|sparks?|smoke|fire|gas|electric\w*|inspect\w*|compensat\w*)\b|退款|付款|密码|漏水|维修|受伤|煤气|kebakaran|bayaran|rosak|bocor', text, re.I):
        return 'The request needs a staff decision, account check or physical action'
    if re.search(r'ignore (?:all |previous |prior )?instructions|system prompt|execute (?:shell|command)|reveal.{0,20}(?:key|secret|password)', text, re.I):
        return 'Instruction-like content requires staff review'
    return ''


def unresolved(text):
    return bool(re.search(r"\b(unresolved|not resolved|did not help|didn't help|does not help|doesn't help|did not work|didn't work|still not working|still broken)\b|belum selesai|masih (?:tak|tidak)|还没解决|没有解决|还是不行|仍然", text, re.I))


PUBLIC_COMPLAINT_ANSWERS = {
    'how do i report a wi-fi connection problem': 'In this conversation, tell us which devices are affected, when Wi-Fi disconnects and whether it happens in your room or a shared area. If you need someone to investigate, choose Still unresolved.',
    'how do i track my complaint': 'On the BeLive complaint page, choose Track an existing complaint and enter your private Complaint Code. Keep that code private.',
    'how can i add more details to my complaint': 'Open your complaint with your Complaint Code. Type the extra details in Reply or outcome details and send the reply. Keep everything in the same conversation.',
    '如何查询投诉进度': '在投诉页面选择 Track an existing complaint，输入提交时收到的 Complaint Code，即可查看进度和回复。请保管好这个代码。',
}

PUBLIC_GUIDANCE = {
    'track': ('How to check the status or replies of a complaint', PUBLIC_COMPLAINT_ANSWERS['how do i track my complaint']),
    'recover': ('How to recover a lost Complaint Code or reference', None),
    'add_details': ('How to add a message or correct details in an existing complaint', PUBLIC_COMPLAINT_ANSWERS['how can i add more details to my complaint']),
    'report_wifi': ('What information to include when reporting Wi-Fi trouble', PUBLIC_COMPLAINT_ANSWERS['how do i report a wi-fi connection problem']),
    'wifi_checks': ('How to do a basic Wi-Fi check on the customer’s own device, without requesting maintenance', 'Check that Wi-Fi is on and airplane mode is off. Try reconnecting to the network and checking whether another device is affected. If the problem persists, tell us which devices are affected and choose Still unresolved.'),
    'location': ('What location information to provide in the complaint form', 'Enter the name of your building or residence. If the problem is in a specific unit, room or shared area, add that location so the team can find it.'),
    'outcome': ('How to say the issue is resolved or request more help on an existing complaint', 'Open your complaint and choose Issue resolved if it has been fixed, or Still unresolved if you need the BeLive team to review it.'),
    'privacy': ('What sensitive information to leave out of the complaint form', 'Describe the issue and where it happened. Leave out passwords, payment details, access codes and identity documents. Keep your Complaint Code private.'),
    'maintenance_details': ('What details to include when reporting a maintenance problem; no repair advice', 'Include the building and unit or shared area, when the issue started, and what you noticed. Say whether it is still happening. For an immediate safety risk, use your building’s emergency channel.'),
    'cleaning_details': ('How to describe a cleaning or shared-space issue in a report', 'Name the building and shared area, such as the lobby or laundry room. Include the date, time and what needs attention so the team can find it.'),
    'noise_details': ('What information to include when reporting repeated noise', 'Include the building, where you heard it, approximate times and how often it happens. Describe what you observed. Leave out neighbours’ personal details.'),
    'recovery_email': ('Whether email is required to submit a complaint and why the form asks for it', 'Recovery email is optional. You can submit without it. Save your Complaint Code and complaint reference after submitting. Email recovery also depends on whether BeLive has enabled email delivery.'),
    'staff_followup': ('How to ask for further help after an automatic answer', 'Open the complaint with your Complaint Code, add what you tried or what still needs attention, then select Still unresolved to ask the team to review it.'),
}


def acknowledgement_only(text):
    cleaned = re.sub(r'[\W_]+', ' ', text.casefold()).strip()
    return bool(re.fullmatch(
        r'(?:(?:oh )?(?:ok(?:ay)?|got it|understood|noted)(?: (?:thank|thanks|thx|tq|thank you|thank you for the help|thank for the help))?'
        r'|thank|thx|tq|thanks(?: for (?:the|your) help)?|thank you(?: for (?:the|your) help)?|谢谢(?:你|你的帮助)?|好的 ?谢谢|terima kasih)',
        cleaned))


def recovery_guidance():
    from belive.complaint_mail import configured
    if configured():
        return 'If you saved your complaint reference and entered a recovery email when you submitted, use “Forgot your Complaint Code?” on the complaint page.'
    return 'Email recovery is currently unavailable. Contact the BeLive team with your original complaint reference, or the approximate submission date and title, so they can help locate it.'


def public_guidance_reply(decision, lessons=None):
    if not isinstance(decision, dict) or decision.get('can_answer') is not True:
        return ''
    topics = decision.get('topics')
    if not isinstance(topics, list) or not 1 <= len(topics) <= 3:
        return ''
    guidance={**PUBLIC_GUIDANCE,**(lessons or {})}
    if not all(isinstance(topic,str) and topic in guidance for topic in topics):
        return ''
    return '\n\n'.join(guidance[topic][1] or recovery_guidance() for topic in dict.fromkeys(topics))


def publish_public_answer(store, db, case):
    if case['status'] != 'AI_PENDING' or exception_reason(case['title']):
        return
    text = ' '.join(case['description'].casefold().replace('’', "'").split())
    questions = [part.strip() for part in re.split(r'[?!.。？！]+', text) if part.strip()]
    if not questions:
        return
    replies = []
    for question in questions:
        reply = PUBLIC_COMPLAINT_ANSWERS.get(question)
        if re.fullmatch(r"(?:i )?(?:forgot|forget|lost|can't find|cannot find) (?:my |the )?complaint (?:id|code|reference(?: number)?)", question):
            reply = recovery_guidance()
        if not reply:
            return
        if reply not in replies:
            replies.append(reply)
    publish_public_guidance(store, db, case, '\n\n'.join(replies), 'SYSTEM')


def publish_public_guidance(store, db, case, reply, sender, turn_id='initial'):
    message = post(store, db, case, sender, reply, 'public-complaint-answer-'+turn_id)
    case.update(status='FOLLOW_UP', severity='LOW',
                next_action='Customer can accept the answer or request staff help',
                automatic_answer={'id':'PUBLIC-COMPLAINT-FAQ','version':1,'message_id':message['id']})
    store.put(db,'case',case)


def policy(store, db):
    return next(iter(store.all(db, 'automation')), {'id':'routine', 'enabled':False, 'version':0})


def active_answers(store, db):
    return [a for a in store.all(db, 'answer') if a.get('active') and a.get('verified')
            and (not a.get('expires_at') or a['expires_at'] > now())]


def command(service, db, name, p):
    store = service.store
    if name == 'automation_settings':
        enabled = p.get('enabled')
        check(type(enabled) is bool, 'Choose whether routine automation is enabled')
        check(not enabled or (service.ai.readiness() and active_answers(store, db)),
              'Configure the model and save at least one approved answer first')
        item = policy(store, db)
        item.update(enabled=enabled, version=item['version']+1, changed_at=now())
        store.put(db, 'automation', item)
        store.event(db, 'routine', 'AUTOMATION_ENABLED' if enabled else 'AUTOMATION_DISABLED', p.get('_actor', 'administrator'))
        return item
    old = next((a for a in store.all(db, 'answer') if a['id'] == p.get('id')), None)
    if p.get('id'):
        check(old is not None and old['version'] == p.get('version'), 'Answer changed; reload its latest version')
    if name == 'answer_deactivate':
        check(old is not None, 'Choose an existing answer')
        item = {**old, 'active':False, 'version':old['version']+1, 'at':now()}
    else:
        check(p.get('confirmed') is True, 'Verify the source and approve this exact answer')
        service.store.get(db, 'condo', p.get('condo_id'))
        check(p.get('category') in CATEGORIES, 'Choose a supported tenant-support category')
        kind=p.get('kind', old.get('kind','EXACT') if old else 'EXACT')
        check(kind in {'EXACT','GUIDANCE'}, 'Choose an exact reply or reusable support guidance')
        check(p.get('language') in LANGUAGES, 'Choose English, Malay or Chinese')
        answer = bounded(p.get('answer'), 8, 2500)
        check(not re.search(r'\b(otp|password|pin code|bank account)\b|密码|银行卡', answer, re.I), 'Do not store secrets or access codes in automatic answers')
        check(not re.search(r'refund (?:has been|is) (?:issued|approved)|we have (?:repaired|refunded)|guarantee|bypass.{0,30}lock', answer, re.I), 'Automatic answers cannot promise financial, repair or access actions')
        expiry = p.get('expires_at') or None
        if expiry:
            date = datetime.fromisoformat(expiry)
            check(date.tzinfo is not None and date > datetime.now(timezone.utc), 'Expiry must be a future time with timezone')
            expiry = date.astimezone(timezone.utc).isoformat()
        item = {'id':old['id'] if old else 'FAQ-'+secrets.token_hex(5).upper(),
                'condo_id':p['condo_id'], 'question':bounded(p.get('question'), 5, 600),
                'answer':answer, 'source':bounded(p.get('source'), 8, 500),
                'category':p['category'], 'language':p['language'], 'kind':kind, 'active':True,
                'verified':True, 'version':old['version']+1 if old else 1,
                'expires_at':expiry, 'at':now(), 'reviewed_by':p.get('_actor', 'administrator')}
    if old:
        store.version(db, 'answer', old)
    store.version(db, 'answer', item)
    store.put(db, 'answer', item)
    store.event(db, item['id'], 'ANSWER_DEACTIVATED' if name == 'answer_deactivate' else 'ANSWER_APPROVED', 'v'+str(item['version'])+'; '+item['source'])
    return item


def eligible(store, db, case):
    return (case.get('automation_requested') and policy(store, db)['enabled']
            and case.get('tenant_id') and case.get('entrypoint') in {'TENANT_PORTAL', 'TENANT_WEBSITE'}
            and not case.get('owner') and not case.get('handoff') and not case.get('automation_paused')
            and case['status'] not in TERMINAL
            and not any(w['case_id'] == case['id'] and w['status'] == 'OPEN' for w in store.all(db, 'workorder')))


def input_turn(store, db, case):
    messages = conversation(store, db, case)
    return next((m for m in reversed(messages) if m['sender'] in {'TENANT', 'REPORTED_ISSUE'}), messages[0])


def tokens(text):
    text = re.sub(r'wi[ -]?fi|internet', 'wifi', text.lower())
    words = set(re.findall(r'[a-z]{3,}', text)) - {'the','how','can','what','does','for','this','that','and','are','with','please'}
    chinese = ''.join(re.findall(r'[\u4e00-\u9fff]', text))
    return words | {chinese[i:i+2] for i in range(len(chinese)-1)}


def add_context(store, db, case, context):
    if not case.get('tenant_id'):
        return context
    tenant = store.get(db, 'tenant', case['tenant_id'])
    turn = input_turn(store, db, case)
    query = tokens(case['title']+' '+turn['text'])
    answers = [a for a in active_answers(store, db) if a['condo_id'] == tenant['condo_id']]
    answers.sort(key=lambda a:len(query & tokens(a['question'])), reverse=True)
    context['verified_records'] += [{'id':a['id'], 'version':a['version'], 'source':a['source'],
        'text':a['answer'], 'question':a['question'], 'knowledge':True} for a in answers[:8]]
    if not eligible(store, db, case):
        return context
    context['approved_answers'] = answers[:8]
    context['automatic'] = {'policy_version':policy(store, db)['version'], 'input_id':turn['id']}
    # The immutable original report stays in the case; evidence for a follow-up quotes its current turn.
    if turn['sender'] == 'TENANT':
        context['case']['description'] = turn['text']
    return context


def handover_receipt(store, db, case):
    if case.get('entrypoint') == 'TENANT_WEBSITE' or (case.get('automation_requested') and case.get('tenant_id')):
        turn = input_turn(store, db, case)
        post(store, db, case, 'SYSTEM', 'Your request needs the support team. It is in the staff queue and remains open. You can add details here.', 'handover-'+turn['id'])


def apply_result(service, db, case, result, context):
    if not context.get('automatic'):
        return
    if case['status'] in {'HUMAN_REVIEW', 'SKIPPED'}:
        if case['status'] == 'SKIPPED':
            service.handoff(db, case, 'No approved routine answer matched the tenant request')
        return
    if result.get('severity')=='MEDIUM':
        service.handoff(db,case,'MODERATE: AI assessment and proposed guidance are ready for staff review. Only SIMPLE replies are automatic.')
        return
    reason = exception_reason(context['case']['title']+' '+context['case']['description'])
    answer = next((a for a in context['approved_answers'] if a['id'] == result.get('approved_answer_id')), None)
    confidence = result.get('match_confidence')
    turns = case.get('automatic_reply_count', 0)
    guided=bool(answer and answer.get('kind')=='GUIDANCE')
    reviewed=not guided or (result.get('guidance_review_passed') is True and answer['id'] in result.get('record_ids',[]))
    safe = (eligible(service.store, db, case) and not reason and answer
            and result.get('relevance') == 'SUPPORT' and result.get('severity') == 'LOW'
            and result.get('uncertainty') is False and result.get('requires_human') is False
            and result.get('category') == answer['category'] and result.get('request_language') == answer['language']
            and type(confidence) in {int, float} and 0.9 <= confidence <= 1 and turns < 3 and reviewed)
    if not safe:
        service.handoff(db, case, reason or 'No sufficiently certain approved answer is available; staff assessment required')
        return
    from belive.service import due
    # Exact replies preserve wording; guidance needs a separate groundedness/safety review.
    key = 'automatic-'+context['automatic']['input_id']
    reply=result['response'] if guided else answer['answer']
    message = post(service.store, db, case, 'AI_SUPPORT', reply, key)
    case.update(draft=reply, status='FOLLOW_UP', followup_due=due(service.settings.followup_minutes),
                followup_count=0, next_action='Tenant can ask a follow-up or accept this informational answer',
                automatic_reply_count=turns+1, automatic_answer={'id':answer['id'], 'version':answer['version'],
                'message_id':message['id'], 'input_id':context['automatic']['input_id']})
    result['response'] = reply
    result['approved_answer_ref'] = {'id':answer['id'], 'version':answer['version'], 'source':answer['source'],'kind':answer.get('kind','EXACT')}
    service.store.event(db, case['id'], 'AUTOMATIC_ANSWER_PUBLISHED', answer['id']+' v'+str(answer['version'])+'; '+message['id'])
