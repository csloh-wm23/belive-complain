"""Passive WhatsApp support: signed intake, isolated conversations, staff advice and delivery."""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit,parse_qs
from urllib.request import Request,build_opener
from belive.store import bounded,digest,now
from belive.connectors import NoRedirect,request_json
from belive.conversations import post
from belive import whatsapp_ai

PREFIX='BELIVE_WHATSAPP_'
MAX_IMAGE=5*1024*1024


def configuration():
    from belive.credentials import get_value,load,CredentialStoreError
    c={k:get_value(PREFIX+k.upper(),'').strip() for k in ('access_token','app_secret','verify_token','phone_number_id','graph_version','webhook_host')}
    # Preserve the newer encrypted credential store's precedence and fail-closed behaviour.
    try:
        if load()['version']:return c
    except CredentialStoreError:return c
    from belive import meta_signup
    runtime=meta_signup.read_json(meta_signup.RUNTIME)
    if runtime:
        saved=meta_signup.read_json(meta_signup.CREDENTIALS)
        saved.update(verify_token=runtime.get('verify_token',''),webhook_host=urlsplit(runtime.get('origin','')).netloc,app_secret=meta_signup.config()['app_secret'])
        for key in c:
            if not c[key]:c[key]=saved.get(key,'')
    return c


def signup_configuration():
    # Numeric identifiers are safe to show to signed-in operators. Never return secrets.
    ids={k:os.getenv(PREFIX+k.upper(),'').strip() for k in ('app_id','config_id','business_id')}
    ids={k:v if re.fullmatch(r'\d{5,30}',v) else '' for k,v in ids.items()}
    return ids|{'recorded':bool(ids['app_id'] and ids['config_id']),
                'meta_configuration_verified':False,'coexistence_required':True}



def ready():
    c=configuration()
    return bool(c['access_token'] and c['app_secret'] and c['verify_token'] and re.fullmatch(r'\d+',c['phone_number_id']) and re.fullmatch(r'v\d+\.\d+',c['graph_version']))


def challenge(query):
    c=configuration();params=parse_qs(query)
    if not c['verify_token'] or params.get('hub.mode')!=['subscribe'] or not hmac.compare_digest(params.get('hub.verify_token',[''])[0],c['verify_token']):raise ValueError('Webhook verification failed')
    value=params.get('hub.challenge',[''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',value):raise ValueError('Invalid challenge')
    return value


def verify(raw,signature):
    secret=configuration()['app_secret']
    return bool(secret and hmac.compare_digest('sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest(),str(signature or '')))


def _save_image(service,data,mime):
    valid=(mime=='image/png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/jpeg' and data.startswith(b'\xff\xd8\xff')) or (mime=='image/webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP')
    if not valid or not 0<len(data)<=MAX_IMAGE:raise ValueError('Use a JPEG, PNG or WebP image no larger than 5 MB')
    directory=service.store.path.parent/'whatsapp_media';directory.mkdir(exist_ok=True)
    filename=digest(data)+{'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}[mime]
    (directory/filename).write_bytes(data)
    return {'file':filename,'mime':mime,'bytes':len(data)}


def media_path(service,message):
    media=message.get('media') or {}
    if not isinstance(media,dict):raise ValueError('Image not available')
    filename=media.get('file','')
    if not re.fullmatch(r'[a-f0-9]{64}\.(?:png|jpg|webp)',filename):raise ValueError('Image not available')
    return service.store.path.parent/'whatsapp_media'/filename


def download_image(service,media_id):
    if not re.fullmatch(r'[0-9]+',media_id):raise ValueError('Invalid media ID')
    c=configuration()
    meta=request_json('https://graph.facebook.com/'+c['graph_version']+'/'+media_id+'?phone_number_id='+c['phone_number_id'],c['access_token'])
    url=meta.get('url','');parsed=urlsplit(url);host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or parsed.password or not any(host==d or host.endswith('.'+d) for d in ('facebook.com','fbsbx.com','fbcdn.net')):raise ValueError('Untrusted media download host')
    if meta.get('mime_type') not in {'image/jpeg','image/png','image/webp'}:raise ValueError('Unsupported photo format')
    with build_opener(NoRedirect).open(Request(url,headers={'Authorization':'Bearer '+c['access_token']}),timeout=20) as response:
        data=response.read(MAX_IMAGE+1)
    return _save_image(service,data,meta['mime_type'])


def customer_reference(phone_number='',user_id=''):
    # BSUIDs remain stable when a user hides their phone number. Do not infer
    # identity from a display name, username or another contact in the payload.
    for candidate in (user_id,phone_number):
        if isinstance(candidate,str) and re.fullmatch(r'[A-Z]{2}\.[A-Za-z0-9]{1,128}',candidate):return candidate
    if isinstance(phone_number,str):
        number=phone_number.removeprefix('+')
        if re.fullmatch(r'[0-9]{6,20}',number):return number
    raise ValueError('Invalid customer reference')


def recipient_fields(reference):
    reference=customer_reference(reference)
    return {'recipient':reference} if '.' in reference else {'to':reference}


def _ingest(service,db,sender,message_id,text,kind,timestamp,*,simulated=False,image=None,media_id=None,reply_to_external_id=None):
    if not re.fullmatch(r'[A-Za-z0-9_.:=/+\-]{1,512}',message_id):raise ValueError('Invalid message identifier')
    namespace='SIM' if simulated else configuration()['phone_number_id']
    key='WAM-'+digest(namespace+':'+message_id)[:24]
    old=next((x for x in service.store.all(db,'wa_message') if x['id']==key),None)
    if old:return {'thread_id':old['thread_id'],'duplicate':True}
    if simulated:
        if not isinstance(sender,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',sender):raise ValueError('Invalid customer reference')
    else:sender=customer_reference(sender)
    tid=('SIMWA-' if simulated else 'WA-')+digest(namespace+':'+sender)[:20]
    thread=next((x for x in service.store.all(db,'wa_thread') if x['id']==tid),None)
    if not thread:
        thread={'id':tid,'recipient':sender,'simulated':simulated,'label':('SIMULATED · '+sender) if simulated else 'WhatsApp · '+sender[-4:],
                'revision':0,'state':'OPEN','at':now(),'property_ref':''}
    case=service.store.get(db,'case',thread['case_id']) if thread.get('case_id') else None
    if not case or case['status'] in {'CLOSED','ANSWERED','SKIPPED'}:
        case=service.create(db,{'title':('[TEST] ' if simulated else '')+'WhatsApp support','description':('WhatsApp: '+text)[:6000] if text else 'Customer shared a photo or unsupported message.',
                              'platform':'INTERNAL','entrypoint':'WHATSAPP','source_id':'WA:'+key})
        case.update(whatsapp_thread_id=tid,sample_data=simulated);service.store.put(db,'case',case)
        thread['case_id']=case['id']
    if image:media=_save_image(service,image[0],image[1])
    else:media=None
    received=float(timestamp)
    if not math.isfinite(received) or received<=0:raise ValueError('Invalid message timestamp')
    received=min(received,datetime.now(timezone.utc).timestamp())
    thread.update(last_customer_at=max(thread.get('last_customer_at',0),received),last_message_at=now(),revision=thread['revision']+1)
    message={'id':key,'thread_id':tid,'case_id':case['id'],'external_id':message_id,'direction':'CUSTOMER','text':text,
             'kind':kind,'at':now(),'media_id':media_id,'media':media}
    quoted=next((m for m in service.store.all(db,'wa_message') if m['thread_id']==tid and m['case_id']==case['id'] and m.get('external_id')==reply_to_external_id),None) if reply_to_external_id else None
    if quoted:message['reply_to_message_id']=quoted['id']
    if reply_to_external_id and not quoted:message['unresolved_quote']=True
    service.store.put(db,'wa_message',message);service.store.put(db,'wa_thread',thread)
    turn={'id':'WAT-'+digest(key)[:24],'thread_id':tid,'message_id':key,'case_id':case['id'],'status':'PENDING','at':now()}
    service.store.put(db,'wa_turn',turn)
    # A new customer message reopens the service window. Re-generate deferred
    # staff guidance, never retry an UNKNOWN send or reuse an old draft.
    for request in service.store.all(db,'wa_staff'):
        if request['thread_id']==tid and request['case_id']==case['id'] and any(o.get('request_id')==request['id'] and o.get('request_revision')==request.get('revision',0) and o['status']=='NEEDS_TEMPLATE' for o in service.store.all(db,'wa_outgoing')):
            _queue_guidance(service,db,request)
    post(service.store,db,case,'TENANT',text[:3000] or 'Customer shared a photo.','wa-in-'+key)
    from belive.reply_learning import discover
    discover(service,db,case['id'])
    service.store.event(db,case['id'],'WHATSAPP_RECEIVED','Simulated message' if simulated else 'Signed WhatsApp customer message received')
    return {'thread_id':tid,'duplicate':False,'case_id':case['id']}


def webhook(service,raw,signature):
    if not verify(raw,signature):raise PermissionError('Invalid webhook signature')
    payload=json.loads(raw)
    if payload.get('object')!='whatsapp_business_account':raise ValueError('Unsupported webhook object')
    c=configuration();threads=set()
    with service.lock,service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for entry in payload.get('entry',[]):
            for change in entry.get('changes',[]):
                value=change.get('value',{})
                if value.get('metadata',{}).get('phone_number_id')!=c['phone_number_id']:continue
                from belive.whatsapp_channel import proof
                metadata=value.get('metadata',{})
                if change.get('field')=='smb_message_echoes':
                    for echo in value.get('message_echoes',[]):_echo(service,db,echo)
                    continue
                if change.get('field') not in {None,'messages'}:continue
                for status in value.get('statuses',[]):
                    for out in service.store.all(db,'wa_outgoing'):
                        if out.get('external_id')==status.get('id'):
                            rank={'ACCEPTED':1,'SENT':2,'DELIVERED':3,'READ':4,'FAILED':5}
                            new=status.get('status','').upper()
                            if new in rank and rank[new]>=rank.get(out['status'],0):
                                out['status']=new
                                if new in {'DELIVERED','READ'}:out.setdefault('delivered_at',now())
                                service.store.put(db,'wa_outgoing',out)
                                if new in {'DELIVERED','READ'}:proof(service,db,metadata,last_reply_delivered=now())
                for msg in value.get('messages',[]):
                    kind=msg.get('type','unsupported')
                    text=msg.get('text',{}).get('body','') if kind=='text' else msg.get('image',{}).get('caption','')
                    sender=customer_reference(msg.get('from',''),msg.get('from_user_id',''))
                    result=_ingest(service,db,sender,msg.get('id',''),bounded(text,0,6000),kind,msg.get('timestamp',0),media_id=msg.get('image',{}).get('id') if kind=='image' else None,reply_to_external_id=msg.get('context',{}).get('id'))
                    proof(service,db,metadata,last_customer_message=now())
                    if not result['duplicate']:threads.add(result['thread_id'])
    return sorted(threads)


def _echo(service,db,message):
    """Mirror a mobile-app message as context; never treat it as a customer request."""
    external_id=message.get('id','')
    try:recipient=customer_reference(message.get('to',''),message.get('to_user_id',''))
    except ValueError:return
    if not re.fullmatch(r'[A-Za-z0-9_.:=/+\-]{1,512}',external_id):return
    if any(x.get('external_id')==external_id for x in service.store.all(db,'wa_message')):return
    tid='WA-'+digest(configuration()['phone_number_id']+':'+recipient)[:20]
    thread=next((x for x in service.store.all(db,'wa_thread') if x['id']==tid),None)
    if not thread:return  # Old mobile-only chats never create unsolicited AI complaints/replies.
    kind=message.get('type','unsupported')
    text=message.get('text',{}).get('body','') if kind=='text' else 'Staff sent a '+kind+' message from the mobile app.'
    text=bounded(text,0,6000)
    service.store.put(db,'wa_message',{'id':'WAM-'+digest('mobile:'+external_id)[:24],'thread_id':tid,'case_id':thread['case_id'],'external_id':external_id,'direction':'STAFF_MOBILE','text':text,'kind':kind,'at':now()})
    # Supersede drafts made before a real human mobile reply; the next customer message resumes AI.
    thread['revision']+=1;service.store.put(db,'wa_thread',thread)
    for turn in service.store.all(db,'wa_turn'):
        if turn['thread_id']==tid and turn['status']=='PENDING':turn['status']='SUPERSEDED';service.store.put(db,'wa_turn',turn)
    post(service.store,db,service.store.get(db,'case',thread['case_id']),'SUPPORT',text[:3000] or 'Staff mobile reply.','wa-mobile-'+external_id)


def _queue_guidance(service,db,request):
    if request.get('status')!='ANSWERED' or request.get('progress')!='GUIDANCE_READY' or not request.get('guidance_message_id'):return
    if not request.get('origin_message_id'):return
    original=service.store.get(db,'wa_message',request['origin_message_id'])
    if original['thread_id']!=request['thread_id'] or original['case_id']!=request['case_id'] or original['direction']!='CUSTOMER' or not original.get('external_id'):return
    turns=service.store.all(db,'wa_turn')
    if any(t.get('request_id')==request['id'] and t.get('request_revision')==request.get('revision',0) and t['status'] in {'PENDING','PROCESSING'} for t in turns):return
    if any(o.get('request_id')==request['id'] and o['status'] in {'UNKNOWN','SENDING'} for o in service.store.all(db,'wa_outgoing')):return
    service.store.put(db,'wa_turn',{'id':'WAT-'+secrets.token_hex(12),'thread_id':request['thread_id'],'case_id':request['case_id'],
        'message_id':request['guidance_message_id'],'status':'PENDING','at':now(),'request_id':request['id'],'request_revision':request.get('revision',0)})


def _staff_request(service,db,thread,question,maintenance=False,*,origin_message_id=None,request_id=None,context=None):
    context=context or {}
    if not origin_message_id:
        origin_message_id=next((m['id'] for m in service.store.all(db,'wa_message') if m['thread_id']==thread['id'] and m['case_id']==thread['case_id'] and m['direction']=='CUSTOMER'),None)
    existing=next((x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id'] and x['case_id']==thread['case_id'] and (x['id']==request_id if request_id else x.get('origin_message_id')==origin_message_id)),None)
    open_requests=[x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id'] and x['case_id']==thread['case_id'] and x['status']=='OPEN']
    photo_id=(context.get('current_photo') or {}).get('message_id')
    photo_requests=[x for x in open_requests if photo_id and x.get('photo_context_message_id')==photo_id]
    if not existing and not request_id and len(photo_requests)==1:existing=photo_requests[0]
    origin_text=service.store.get(db,'wa_message',origin_message_id)['text'] if origin_message_id else ''
    if not existing and len(open_requests)==1 and re.fullmatch(r'\s*(?:any (?:update|news)|any updates|still waiting|有消息吗|有进展吗|ada update|ada perkembangan)[?？.!\s]*',origin_text,re.I):existing=open_requests[0]
    case=service.store.get(db,'case',thread['case_id'])
    was_maintenance=bool(existing and existing.get('maintenance'))
    was_waiting=bool(existing and existing.get('status')=='OPEN')
    from belive.routing import destination,settings as routing_settings
    maintenance_destination=destination(service.store,db,'MAINTENANCE')
    category='MAINTENANCE' if maintenance or was_maintenance else case['category']
    assigned=destination(service.store,db,category)
    item=existing or {'id':'WAS-'+secrets.token_hex(6),'thread_id':thread['id'],'case_id':case['id'],'status':'OPEN','at':now()}
    if photo_id:item['photo_context_message_id']=photo_id
    item['handoff_summary']={'problem':(context.get('assessment') or {}).get('summary') or (case.get('analysis') or {}).get('summary',''),
        'original_customer_message':origin_text[:1500],
        'latest_customer_update':context.get('current_message',{}).get('text','')[:1500] if context.get('current_message',{}).get('role')=='CUSTOMER' else '',
        'decision_needed':question or 'Provide a verified next step.'}
    item.update(question=question or 'Please review this customer support request and provide verified guidance.',maintenance=maintenance or item.get('maintenance',False),
                origin_message_id=item.get('origin_message_id') or origin_message_id,status='OPEN',progress='WAITING_GUIDANCE',revision=item.get('revision',0)+1,
                evidence_checked={'sop_titles':[s.get('title','') for s in context.get('sop',[])],
                                  'research_attempted':context.get('research_attempted',False),'research_sources':context.get('research_sources',[]),
                                  'research_purpose':context.get('research_purpose'),'research_summary':context.get('research_summary','')[:3000],
                                  'unavailable_details':context.get('unavailable_details',[]),'photo_message_id':(context.get('current_photo') or {}).get('message_id')},
                category=category,assigned_team=assigned,routing_confirmed=bool(routing_settings(service.store,db)['departments'].get(category)))
    service.store.put(db,'wa_staff',item)
    thread['state']='WAITING_STAFF'
    if not existing or not was_waiting:
        new_workorder=maintenance and not was_maintenance
        notification=service.handoff(db,case,'WhatsApp customer needs team guidance: '+item['question'],target=assigned,notify=not item['maintenance'])
        if notification:item['notification_id']=notification['id']
        case['revision']+=1;service.store.put(db,'case',case)
    elif maintenance and not was_maintenance:
        case['staff_destination']=assigned;case['revision']+=1;service.store.put(db,'case',case)
    if item['maintenance']:
        from belive.maintenance_intake import update
        update(service,db,item,case,context)
    service.store.put(db,'wa_staff',item)


def sop(service,db,thread):
    from belive.company_sop import eligible
    from belive.shared_memory import knowledge
    return [x for x in knowledge(service,db) if eligible(service,db,x) and (not x.get('property_ref') or x['property_ref']==thread.get('property_ref'))]



def _local_learning_versions(tips,lessons):
    from belive.memory_hub import fingerprint
    tip_fields=('id','question','tip','category','scope_condo','revision','approved','status')
    lesson_fields=('id','question','answer','category','sample_data')
    return ({'tip:'+x['id']:fingerprint({k:x.get(k) for k in tip_fields}) for x in tips}
            | {'experience:'+x['id']:fingerprint({k:x.get(k) for k in lesson_fields}) for x in lessons})


def _local_learning_stale(service,db,versions):
    if not versions:return False
    from belive import shared_memory
    from belive.experience_learning import experiences
    # Native WhatsApp memory projects these same tips; never keep a draft after their approval changes.
    if shared_memory.enabled(service,db):return True
    tips=[x for x in service.store.all(db,'reply_learning') if x.get('approved') and x['status']=='APPROVED' and x.get('scope_condo') is None]
    current=_local_learning_versions(tips,experiences(service,db))
    return any(current.get(key)!=version for key,version in versions.items())


def process_thread(service,tid):
    from belive.hermes_native import conversation_scope
    from belive.credentials import credential_scope
    from belive.whatsapp_presence import Presence
    with conversation_scope(tid),credential_scope(service.store.path),Presence(service,tid):return _process_thread(service,tid)

def _phase(service,turn,phase):
    with service.store.connect() as db:
        current=service.store.get(db,'wa_turn',turn['id'])
        if current['status']=='PROCESSING':
            current.update(phase=phase,phase_at=now());service.store.put(db,'wa_turn',current)


def _process_thread(service,tid):
    from belive import shared_memory
    from belive.service import risk
    with service.store.connect() as db:sharing=shared_memory.enabled(service,db)
    for _ in range(8):
        native_started_at=now()
        with service.lock,service.store.connect() as db:
            pending=[x for x in reversed(service.store.all(db,'wa_turn')) if x['thread_id']==tid and x['status']=='PENDING']
            if not pending:return
            # New customer questions take priority; staff solutions stay queued separately.
            customer_turns=[x for x in pending if not x.get('request_id')]
            turn=customer_turns[-1] if customer_turns else pending[0]
            for stale in (customer_turns[:-1] if customer_turns else []):
                stale['status']='SUPERSEDED';service.store.put(db,'wa_turn',stale)
            thread=service.store.get(db,'wa_thread',tid);revision=thread['revision']
            previous_case=service.store.get(db,'case',thread['case_id']);case_revision=previous_case['revision']
            turn.update(status='PROCESSING',started_at=now(),phase='CHECKING_CONTEXT',phase_at=now());service.store.put(db,'wa_turn',turn)
            messages=[x for x in reversed(service.store.all(db,'wa_message')) if x['thread_id']==tid and x['case_id']==thread['case_id']][-20:]
            requests=[x for x in service.store.all(db,'wa_staff') if x['thread_id']==tid and x['case_id']==thread['case_id']]
            target=next((x for x in requests if x['id']==turn.get('request_id')),None)
            if target and (target.get('revision',0)!=turn.get('request_revision') or target.get('status')!='ANSWERED'):
                turn['status']='SUPERSEDED';service.store.put(db,'wa_turn',turn);continue
            instructions=[]
            focused=next((x for x in messages if x['id']==turn['message_id']),messages[-1] if messages else {})
            original=service.store.get(db,'wa_message',target['origin_message_id']) if target and target.get('origin_message_id') else None
            focused_quote=service.store.get(db,'wa_message',focused['reply_to_message_id']) if focused.get('reply_to_message_id') else None
            request_origins={}
            for request in requests:
                if request.get('origin_message_id'):
                    source=service.store.get(db,'wa_message',request['origin_message_id'])
                    if source['thread_id']==tid and source['case_id']==thread['case_id'] and source['direction']=='CUSTOMER' and source.get('external_id'):request_origins[request['id']]=source['text']
            # A sourced AI continuation can mark an issue ANSWERED/WAITING_CUSTOMER
            # without any staff-authored guidance. Never promote it to staff evidence.
            instructions=[x for x in reversed(requests) if x['id'] in request_origins and x['status']=='ANSWERED' and isinstance(x.get('guidance'),str) and x['guidance'].strip() and (not target or x['id']==target['id'])][-3:]
            question=original['text'] if original else focused.get('text','') if focused.get('direction')=='CUSTOMER' else next((x['text'] for x in reversed(messages) if x['direction']=='CUSTOMER'),'')
        urgent=bool(focused.get('direction')=='CUSTOMER' and risk(focused['text']))
        social_only=not urgent and whatsapp_ai.greeting_only(messages,previous_case,thread,instructions)
        # The deterministic emergency acknowledgement must not wait for unrelated memory/network work.
        memory_ready=urgent or social_only or not sharing or shared_memory.sync(service).get('status')=='ONLINE'
        with service.lock,service.store.connect() as db:
            from belive.reply_learning import matching
            from belive.experience_learning import experiences
            from belive.relevance import match_score
            knowledge=[] if urgent else sop(service,db,thread)
            tips=[] if urgent or social_only else matching(service,db,question)
            lessons=[] if urgent or social_only else sorted([x for x in experiences(service,db) if match_score(question,x['question'])>0],key=lambda x:match_score(question,x['question']),reverse=True)[:3]
            shared_snapshot={x['key']:x['revision'] for x in service.store.all(db,'memory_record')} if sharing and not urgent and not social_only else {}
            local_learning_versions=_local_learning_versions(tips,lessons) if not sharing and not urgent and not social_only else {}
            from belive.routing import settings as routing_settings
            team_routes=routing_settings(service.store,db)['departments']
            from belive.customer_directory import facts as customer_facts
            customer_record=customer_facts(service,db,thread) if not urgent and not social_only else None
        from belive.company_sop import retrieve,evidence
        _phase(service,turn,'CHECKING_RULES')
        from belive import whatsapp_triage
        selected,lookup_uncertain=([],False) if urgent or social_only else retrieve(service,knowledge,[original] if original else messages)
        steps=['Greeting-only eligibility checked; no unresolved support issue'] if social_only else ['Relevant company SOP retrieved'] if selected else []
        context={'conversation':[{'role':x['direction'],'text':x['text'],'photo':x.get('vision'),'message_id':x['id'],'reply_to_message_id':x.get('reply_to_message_id'),'photo_context_message_id':x.get('photo_context_message_id')} for x in messages],
            'sop':evidence(selected),'sop_lookup_uncertain':lookup_uncertain,
            'approved_experiences':[{k:x[k] for k in ('id','question','answer','sample_data')} for x in lessons],
            'latest_sender':'STAFF_INTERNAL' if target else focused.get('direction',''),
            'current_message':{'message_id':focused.get('id'),'role':focused.get('direction',''),'text':focused.get('text',''),'quoted_text':focused_quote.get('text') if focused_quote else None,'quoted_request_id':focused_quote.get('request_id') if focused_quote else None},
            'target_request':{'id':target['id'],'question':target['question'],'original_message':original['text']} if target and original else None,
            'support_requests':[{'id':x['id'],'question':x['question'],'status':x['status'],'origin_message_id':x.get('origin_message_id'),'photo_context_message_id':x.get('photo_context_message_id'),'original_message':request_origins[x['id']],'maintenance_location':x.get('maintenance_location',{}),'severity':x.get('severity')} for x in requests if x['id'] in request_origins],
            'legacy_staff_requests_waiting_for_binding':sum(x['id'] not in request_origins for x in requests),
            'explicit_staff_requested':bool(focused.get('direction')=='CUSTOMER' and whatsapp_ai.explicit_staff_request(focused['text'])),
            'staff_guidance':[{'id':x['id'],'question':x['question'],'verified_solution':x['guidance']} for x in instructions],
            'staff_work_updates':[{'id':r['id'],'state':r['maintenance_progress']['state'],'note':r['maintenance_progress'].get('note',''),'updated_at':r['maintenance_progress']['updated_at'],'internal_only':True} for r in requests if r['id'] in request_origins and r['status']!='CLOSED' and r.get('maintenance_progress')],
            'waiting_for_staff':thread['state']=='WAITING_STAFF','provided_property':thread.get('property_ref'),
            'ongoing_support':bool(requests),
            'team_routes':team_routes,'team_notification_mode':'internal_queue_pending_approval',
            'research_sources':[],'research_attempted':False,'research_performed_this_turn':False,'reviewed_writing_tips':[{'id':x['id'],'tip':x['tip']} for x in tips],
            'social_only':social_only,'customer_record':customer_record}
        from belive import wa_research
        context['research_history']=[] if urgent or social_only else wa_research.history(service,thread['case_id'])
        used_shared={('sop:'+x['id']) for x in selected}|{('document:'+x['document_id']) for x in selected if x.get('document_id')}
        used_shared|={('tip:'+x['id'].removeprefix('SHARED-')) for x in tips}|{('experience:'+x['id'].removeprefix('SHARED-')) for x in lessons}
        shared_revisions={k:shared_snapshot[k] for k in used_shared if k in shared_snapshot}
        assessment=whatsapp_triage.emergency(question) if urgent else whatsapp_triage.greeting(question) if social_only else None
        staff_draft=None;delivery_kind='ACKNOWLEDGEMENT';decision_trace=[];photo_anchor=''
        try:
            if not memory_ready and not urgent:raise ValueError('Shared knowledge unavailable; do not use a potentially revoked local rule')
            for message in ([] if urgent else [original or focused]):
                if message['direction']!='CUSTOMER' or message['kind']!='image' or message.get('vision'):continue
                media=message.get('media') or download_image(service,message['media_id'])
                # Make the downloaded preview available while native vision runs.
                if not message.get('media'):
                    with service.lock,service.store.connect() as db:
                        saved=service.store.get(db,'wa_message',message['id']);saved['media']=media;service.store.put(db,'wa_message',saved)
                copy={**message,'media':media};data_url='data:'+media['mime']+';base64,'+base64.b64encode(media_path(service,copy).read_bytes()).decode()
                _phase(service,turn,'READING_PHOTO')
                vision=whatsapp_ai.read_photo(service,data_url);steps.append('Photo read')
                with service.lock,service.store.connect() as db:
                    saved=service.store.get(db,'wa_message',message['id']);saved.update(media=media,vision=vision);service.store.put(db,'wa_message',saved)
                context['conversation'].append({'role':'PHOTO_OBSERVATION','text':vision,'message_id':message['id']})
                context['current_photo']={'message_id':message['id'],'observations':vision}
            if (original or focused).get('vision'):
                context['current_photo']={'message_id':(original or focused)['id'],'observations':(original or focused)['vision']}
            photos=[x.get('vision') for x in [original or focused] if x.get('vision')]
            photos += [x['text'] for x in context['conversation'] if x['role']=='PHOTO_OBSERVATION']
            # A typed code from an unrelated earlier photo/issue does not confirm
            # the code in this new image. Bind confirmation to this image caption.
            customer_text=(original or focused).get('text','').lower()
            typed_code=bool(re.search(r'\b(?:[a-z]{1,3}\d{1,3}[a-z]?|\d{1,3}[a-z]{1,3})\b|(?:code|display|shows|reads|代码|显示)\s*(?:is|says|:|是)?\s*[a-z0-9-]{2,12}',customer_text,re.I))
            # A typed correction takes priority over a potentially mistaken OCR candidate.
            context['photo_confirmation_required']=bool(photos) and not typed_code
            if messages and messages[-1]['kind'] not in {'text','image','staff'}:raise ValueError('Only text and photos are supported')
            if not urgent and context['latest_sender']=='CUSTOMER' and photos and any(risk(str(x.get('observations',''))) for x in photos):
                urgent=True;assessment=whatsapp_triage.emergency(question)
            if assessment is None:
                _phase(service,turn,'ASSESSING_QUESTION')
                if context['latest_sender']=='STAFF_INTERNAL':
                    with service.store.connect() as db:assessment=service.store.get(db,'case',thread['case_id']).get('analysis')
                if not assessment:assessment=whatsapp_triage.assess(service,context)
            if assessment['severity']=='CRITICAL' and context['latest_sender']=='CUSTOMER':urgent=True
            context['assessment']=assessment
            context['unavailable_details']=assessment.get('unavailable_details',[])
            steps.append('Complaint category and level assessed')
            if not urgent and context['latest_sender']=='CUSTOMER':
                from belive import photo_context
                photo_anchor=photo_context.apply(context,assessment,focused)
                if photo_anchor:decision_trace.append({'stage':'photo_context','scope':context.get('photo_context_scope','EXPLICIT_DEVICE_LINK'),'photo_message_id':photo_anchor,'confirmed_error_code':context.get('confirmed_error_code','')})
            context['research_history']=[r for r in context['research_history'] if photo_anchor and r['photo_message_id']==photo_anchor]
            if context['research_history']:
                wa_research.prime(context,context['research_history'][0]);steps.append('Recent official lookup available for this photo')
            def perform_research(query,kind,purpose):
                _phase(service,turn,'CHECKING_OFFICIAL_SOURCES')
                reused=wa_research.lookup(service,context,thread['case_id'],photo_anchor,query,kind,purpose)
                steps.append('Recent official lookup reused for this photo' if reused else 'Official device-identification sources searched' if purpose=='IDENTIFICATION' else 'Company website checked' if kind=='COMPANY' else 'Technical sources searched')
            # The native assessor can request missing public evidence before reply drafting.
            # A remembered handover must not silently suppress that tool execution.
            private_policy=lookup_uncertain or any(x.get('policy')=='CONFLICT_REVIEW' for x in context['sop'])
            research_purpose=assessment.get('research_purpose','GUIDANCE')
            if not urgent and not context['explicit_staff_requested'] and (not context['photo_confirmation_required'] or research_purpose=='IDENTIFICATION') and not private_policy and assessment['severity'] in {'LOW','MEDIUM'} and assessment.get('research') in {'COMPANY','TECHNICAL'}:
                perform_research(assessment['search_query'],assessment['research'],research_purpose)
                decision_trace.append({'stage':'assessment_research','research':assessment['research'],'purpose':research_purpose,'search_query':assessment['search_query']})
            if urgent:
                draft={'reply':'Please move away from the hazard and do not touch or repair the equipment. If anyone is in immediate danger, contact local emergency services now. I am alerting our team urgently; you can keep messaging here.', 'needs_staff':True,'staff_question':'Urgent safety report: review immediately and arrange the appropriate response.','needs_maintenance':True,'research':'NONE','search_query':'','sources_used':[]}
            else:
                _phase(service,turn,'PREPARING_REPLY');draft=whatsapp_ai.reply(service,context)
            decision_trace.append({'stage':'initial',**{k:draft.get(k) for k in ('handling','decision_reason','needs_staff','needs_maintenance','research','search_query')}})
            if social_only and (draft['needs_staff'] or draft['needs_maintenance'] or draft['research']!='NONE' or draft['sources_used'] or draft['search_query'] or draft['staff_question']):
                raise ValueError('Greeting response proposed unsupported actions')
            steps.append('Conversation assessed')
            def complete_research(draft):
                if draft.get('research','NONE')=='NONE' or not draft.get('search_query'):return draft
                if context['research_performed_this_turn']:raise ValueError('Repeated research request after evidence was supplied')
                purpose=draft.get('research_purpose','GUIDANCE')
                if context['photo_confirmation_required'] and purpose!='IDENTIFICATION':
                    draft.update(reply='Could you type the exact code shown on the display and the appliance brand/model? Similar-looking codes can mean different things, so I want to check the right guidance.',handling='CLARIFY',decision_reason='Confirm typed display details before code-specific research.',research='NONE',needs_staff=False,needs_maintenance=False,staff_question='',sources_used=[])
                    steps.append('Asked customer to confirm photo details')
                else:
                    perform_research(draft['search_query'],draft['research'],purpose)
                    draft=whatsapp_ai.reply(service,context)
                    decision_trace.append({'stage':'after_research',**{k:draft.get(k) for k in ('handling','decision_reason','needs_staff','needs_maintenance','research','search_query')}})
                return draft
            draft=complete_research(draft)
            whatsapp_ai.enforce_staff_request(draft,context)
            assessment,draft,delivery_kind,staff_draft=whatsapp_triage.apply_policy(assessment,draft,context,urgent)
            review_context={**context,'acknowledgement_only':staff_draft is not None,'private_staff_draft':staff_draft,'clarification_only':delivery_kind=='CLARIFICATION'}
            _phase(service,turn,'REVIEWING_REPLY')
            if not urgent and not whatsapp_ai.review(service,review_context,draft['reply'],draft):
                feedback=review_context.pop('_review_feedback',{})
                decision_trace.append({'stage':'review_rejected','safe':feedback.get('safe'),'grounded':feedback.get('grounded'),'handoff_justified':feedback.get('handoff_justified'),'next_step_useful':feedback.get('next_step_useful'),'improvement_reason':str(feedback.get('improvement_reason',''))[:500],'unsupported_claims':[str(x)[:400] for x in feedback.get('unsupported_claims',[])[:5]]})
                revised_context={**context,'revision_feedback':feedback,'previous_draft':draft['reply'],
                                 'acknowledgement_only':staff_draft is not None}
                draft=whatsapp_ai.reply(service,revised_context);whatsapp_ai.enforce_staff_request(draft,context)
                decision_trace.append({'stage':'after_review',**{k:draft.get(k) for k in ('handling','decision_reason','needs_staff','needs_maintenance','research','search_query')}})
                draft=complete_research(draft)
                assessment,draft,delivery_kind,staff_draft=whatsapp_triage.apply_policy(assessment,draft,context,urgent)
                review_context={**context,'acknowledgement_only':staff_draft is not None,'private_staff_draft':staff_draft,'clarification_only':delivery_kind=='CLARIFICATION'}
                if not whatsapp_ai.review(service,review_context,draft['reply'],draft):
                    feedback=review_context.get('_review_feedback',{})
                    decision_trace.append({'stage':'review_rejected','safe':feedback.get('safe'),'grounded':feedback.get('grounded'),'handoff_justified':feedback.get('handoff_justified'),'next_step_useful':feedback.get('next_step_useful'),'improvement_reason':str(feedback.get('improvement_reason',''))[:500],'unsupported_claims':[str(x)[:400] for x in feedback.get('unsupported_claims',[])[:5]]})
                    raise ValueError('Reply did not pass safety/evidence review')
                steps.append('Reply revised after evidence review')
            steps.append('Reply reviewed')
        except Exception as exc:
            code=str(exc)
            decision_trace.append({'stage':'fallback','error_type':type(exc).__name__,'code':code if re.fullmatch(r'[A-Z][A-Z0-9_]{2,80}',code) else 'REPLY_REVIEW_FAILED' if code=='Reply did not pass safety/evidence review' else 'PROCESSING_FAILED'})
            assessment=assessment or whatsapp_triage.failed(question)
            assessment.update(uncertainty=True,requires_human=True)
            if assessment['severity']=='LOW':assessment['severity']='MEDIUM'
            assessment=whatsapp_triage.preserve_priority(assessment,previous_case,thread['state']=='WAITING_STAFF')
            assessment['level_reason']+=' The reply or evidence review could not complete; staff review is required.'
            draft={'reply':'I got your message. I cannot confirm a safe solution yet, so I am asking our team for guidance. You can keep sending details here; I will help you through the next steps.',
                   'needs_staff':True,'staff_question':'Review the customer message/photo and provide a verified safe response.','needs_maintenance':False,'sources_used':[],'handling':'TEAM','decision_reason':'The reply or evidence verification could not complete.'}
            steps.append('Staff fallback: AI, research or photo check could not complete')
        if urgent:
            selected=[];tips=[];shared_revisions={};local_learning_versions={}
        with service.lock,service.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');current=service.store.get(db,'wa_thread',tid);saved_turn=service.store.get(db,'wa_turn',turn['id'])
            live_shared={x['key']:x['revision'] for x in service.store.all(db,'memory_record')}
            record_changed=customer_record is not None and customer_facts(service,db,current)!=customer_record
            live_requests={r['id']:r for r in service.store.all(db,'wa_staff')}
            staff_context_changed=any(r['id'] not in live_requests or live_requests[r['id']].get('revision',0)!=r.get('revision',0) for r in requests)
            if staff_context_changed or record_changed or current['revision']!=revision or service.store.get(db,'case',current['case_id'])['revision']!=case_revision or (not urgent and not social_only and sop(service,db,current)!=knowledge) or any(live_shared.get(k)!=v for k,v in shared_revisions.items()) or (not urgent and _local_learning_stale(service,db,local_learning_versions)):
                saved_turn['status']='SUPERSEDED';service.store.put(db,'wa_turn',saved_turn)
                if not any(x['thread_id']==tid and x['status']=='PENDING' and x.get('request_id')==turn.get('request_id') for x in service.store.all(db,'wa_turn')):
                    retry={**turn,'id':'WAT-'+secrets.token_hex(12),'status':'PENDING','at':now()};service.store.put(db,'wa_turn',retry)
                continue
            case=service.store.get(db,'case',current['case_id'])
            assessment.update(response=staff_draft or draft['reply'],plan=draft['staff_question'] or 'Continue the support conversation.')
            case_assessment=whatsapp_triage.preserve_priority(dict(assessment),previous_case,bool(requests))
            case.update(analysis=case_assessment,category=case_assessment['category'],severity=case_assessment['severity'],draft=staff_draft or draft['reply'],updated_at=now())
            from belive.routing import destination
            case['staff_destination']=destination(service.store,db,case['category'])
            case['revision']+=1;service.store.put(db,'case',case)
            service.store.event(db,case['id'],'WHATSAPP_ASSESSED',assessment['report_type']+'; '+assessment['category']+'; '+assessment['complaint_level']+'; '+case['staff_destination'])
            related=target['id'] if target else draft.get('related_request_id','')
            related_request=next((x for x in requests if x['id']==related),None)
            if related and related_request is None:raise ValueError('Support issue is outside this conversation')
            if related_request and related not in request_origins:
                # Legacy tasks without a verified original message cannot be resumed
                # or marked answered. A reviewed current reply remains independent.
                related='';related_request=None
                service.store.event(db,case['id'],'WHATSAPP_LEGACY_ISSUE_UNBOUND','Current reply kept separate; old staff task needs an original customer message selected.')
            if draft['needs_staff']:_staff_request(service,db,current,draft['staff_question'],draft['needs_maintenance'],origin_message_id=focused.get('id') if focused.get('direction')=='CUSTOMER' else None,request_id=related or None,context={**context,'maintenance_location':{'property':draft.get('maintenance_property',''),'unit':draft.get('maintenance_unit',''),'complete':draft.get('maintenance_location_complete',False)}})
            else:current['state']='WAITING_STAFF' if any(x['thread_id']==tid and x['status']=='OPEN' for x in service.store.all(db,'wa_staff')) else 'OPEN'
            if related:related_request=service.store.get(db,'wa_staff',related)
            if photo_anchor and focused.get('direction')=='CUSTOMER':
                bound=service.store.get(db,'wa_message',focused['id']);bound['photo_context_message_id']=photo_anchor;service.store.put(db,'wa_message',bound)
                if related_request:related_request['photo_context_message_id']=photo_anchor;service.store.put(db,'wa_staff',related_request)
            case=service.store.get(db,'case',current['case_id'])
            out={'id':'WAO-'+digest(turn['id'])[:24],'thread_id':tid,'case_id':current['case_id'],'thread_revision':revision,'case_revision':case['revision'],
                 'text':draft['reply'],'status':'QUEUED','at':now(),'sources':draft.get('sources_used',[]),'research_sources':context['research_sources'],'steps':steps,'tip_ids':[x['id'] for x in tips],
                 'company_evidence':evidence([x for x in selected if x['id'] in draft.get('sources_used',[])]),
                 'assessment':assessment,'staff_destination':case['staff_destination'],'delivery_kind':delivery_kind,'staff_draft':staff_draft,
                 'knowledge_versions':{x['id']:x['version'] for x in selected}}
            out['processing_path']='GREETING_REVIEWED' if social_only else 'FULL_SUPPORT'
            out['customer_record_facts']=customer_record
            out['responds_to_message_id']=focused['id'] if focused.get('direction')=='CUSTOMER' else None
            out['handling']=draft.get('handling');out['decision_reason']=draft.get('decision_reason','');out['decision_trace']=decision_trace
            out['photo_context_message_id']=photo_anchor or None;out['research_purpose']=context.get('research_purpose');out['identification_only']=context.get('identification_only',False)
            out['request_id']=related or None
            out['continues_request']=bool(related and not draft['needs_staff'])
            out['reply_to_message_id']=related_request.get('origin_message_id') if related_request else focused.get('id') if focused.get('direction')=='CUSTOMER' else None
            out['request_revision']=related_request.get('revision',0) if related_request else None
            out['shared_revisions']=shared_revisions;out['local_learning_versions']=local_learning_versions
            scope_hash=hashlib.sha256(tid.encode()).hexdigest()[:24]
            executions=[x for x in service.store.all(db,'native_execution') if x.get('scope_hash')==scope_hash and x['at']>=native_started_at]
            out['native_execution_ids']=[x['id'] for x in executions]
            out['native_reply_verified']=any(x.get('role')=='WhatsApp Customer Support Agent' and x.get('engine')=='hermes-native' and x.get('mode')=='generate' and x.get('api_calls',0)>0 for x in executions)
            out['native_tools']=sorted({name for x in executions for name in x.get('executed_tools',[])})
            service.store.put(db,'wa_outgoing',out);service.store.put(db,'wa_thread',current)
            saved_turn.update(status='COMPLETE',phase='COMPLETE',phase_at=now(),steps=steps);service.store.put(db,'wa_turn',saved_turn)
        deliver(service,out['id'])


def _case_blocks_reply(case,out):
    from belive.workflow import complaint_level
    known={'SIMPLE','VERIFIED_STAFF_GUIDANCE','ACKNOWLEDGEMENT','URGENT_ACKNOWLEDGEMENT','CLARIFICATION','REVIEWED_GUIDANCE','REVIEWED_TEAM_GUIDANCE'}
    required_handling={'CLARIFICATION':'CLARIFY','REVIEWED_GUIDANCE':'ANSWER','REVIEWED_TEAM_GUIDANCE':'TEAM'}
    next_step_invalid=(out.get('delivery_kind') in required_handling and (out.get('assessment',{}).get('severity') not in {'LOW','MEDIUM'} or out.get('handling')!=required_handling[out['delivery_kind']]))
    return (case['status'] in {'CLOSED','ANSWERED','SKIPPED','VERIFIED'}
            or out.get('case_revision')!=case['revision'] or out.get('delivery_kind') not in known
            or next_step_invalid
            or (out.get('delivery_kind')=='SIMPLE' and complaint_level(case)!='SIMPLE'))


def deliver(service,out_id):
    from belive import shared_memory
    with service.lock,service.store.connect() as db:
        pending=service.store.get(db,'wa_outgoing',out_id)
        if pending['status']!='QUEUED':return pending
        case=service.store.get(db,'case',pending['case_id'])
        if _case_blocks_reply(case,pending):
            pending.update(status='SUPERSEDED',error='The case changed or no longer permits this reply; staff must review the current case before another send.')
            service.store.put(db,'wa_outgoing',pending)
            if pending.get('request_id') and case['status'] not in {'CLOSED','ANSWERED','SKIPPED','VERIFIED'}:
                _queue_guidance(service,db,service.store.get(db,'wa_staff',pending['request_id']))
            return pending
        requires_common=pending.get('delivery_kind')!='URGENT_ACKNOWLEDGEMENT' and bool(pending.get('knowledge_versions') or pending.get('shared_revisions')) and shared_memory.enabled(service,db)
    if requires_common and shared_memory.sync(service).get('status')!='ONLINE':
        with service.lock,service.store.connect() as db:
            pending=service.store.get(db,'wa_outgoing',out_id)
            if pending['status']=='QUEUED':pending['error']='Shared knowledge is offline; waiting for a current revision before sending';service.store.put(db,'wa_outgoing',pending)
        return pending
    with service.lock,service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE');out=service.store.get(db,'wa_outgoing',out_id)
        if out['status']!='QUEUED':return out
        thread=service.store.get(db,'wa_thread',out['thread_id'])
        case=service.store.get(db,'case',out['case_id'])
        request=service.store.get(db,'wa_staff',out['request_id']) if out.get('request_id') else None
        request_changed=request and (request['thread_id']!=thread['id'] or request['case_id']!=case['id'] or request.get('revision',0)!=out.get('request_revision'))
        quoted=service.store.get(db,'wa_message',out['reply_to_message_id']) if out.get('reply_to_message_id') else None
        quote_invalid=bool(out.get('request_id') and not quoted) or bool(quoted and (quoted['thread_id']!=thread['id'] or quoted['case_id']!=case['id'] or quoted['direction']!='CUSTOMER' or not quoted.get('external_id')))
        from belive.workflow import complaint_level
        terminal=case['status'] in {'CLOSED','ANSWERED','SKIPPED','VERIFIED'}
        case_changed=out.get('case_revision')!=case['revision']
        policy_changed=_case_blocks_reply(case,out)
        urgent_ack=out.get('delivery_kind')=='URGENT_ACKNOWLEDGEMENT'
        from belive.company_sop import eligible
        current_knowledge={x['id']:x for x in service.store.all(db,'wa_knowledge')}
        stale=not urgent_ack and any(k not in current_knowledge or not eligible(service,db,current_knowledge[k]) or current_knowledge[k]['version']!=v for k,v in out.get('knowledge_versions',{}).items())
        shared_now={x['key']:x['revision'] for x in service.store.all(db,'memory_record')}
        stale=stale or (not urgent_ack and any(shared_now.get(k)!=v for k,v in out.get('shared_revisions',{}).items()))
        stale=stale or (not urgent_ack and _local_learning_stale(service,db,out.get('local_learning_versions',{})))
        if not urgent_ack and out.get('customer_record_facts'):
            from belive.customer_directory import facts
            stale=stale or facts(service,db,thread)!=out['customer_record_facts']
        if terminal or case_changed or policy_changed or request_changed or quote_invalid:
            out.update(status='SUPERSEDED',error='The case changed or no longer permits this reply; staff must review the current case before another send.')
        elif out['thread_revision']!=thread['revision'] or stale:out['status']='SUPERSEDED'
        elif datetime.now(timezone.utc).timestamp()-thread.get('last_customer_at',0)>86400:out.update(status='NEEDS_TEMPLATE',error='Customer service window expired; wait for the customer or use an approved WhatsApp template.')
        elif thread['simulated']:out['status']='SIMULATED'
        elif not ready():out.update(status='NOT_CONFIGURED',error='WhatsApp company connection is not configured.')
        else:out['status']='SENDING'
        service.store.put(db,'wa_outgoing',out)
        if out['status']=='SUPERSEDED' and request and not terminal and not request_changed and not quote_invalid:_queue_guidance(service,db,request)
        if stale and not (terminal or case_changed or policy_changed) and out['thread_revision']==thread['revision'] and not any(x['thread_id']==thread['id'] and x['status']=='PENDING' for x in service.store.all(db,'wa_turn')):
            service.store.put(db,'wa_turn',{'id':'WAT-'+secrets.token_hex(12),'thread_id':thread['id'],'case_id':thread['case_id'],'message_id':out['id'],'status':'PENDING','at':now()})
    if out['status']=='SENDING':
        c=configuration()
        try:
            result=request_json('https://graph.facebook.com/'+c['graph_version']+'/'+c['phone_number_id']+'/messages',c['access_token'],payload={
                'messaging_product':'whatsapp','recipient_type':'individual',**recipient_fields(thread['recipient']),'type':'text','text':{'body':out['text']},
                **({'context':{'message_id':quoted['external_id']}} if quoted else {})})
            external=result.get('messages',[{}])[0].get('id')
            if not isinstance(external,str) or not external:raise ValueError('No message receipt')
            out.update(status='ACCEPTED',external_id=external)
        except HTTPError as exc:out.update(status='FAILED' if 400<=exc.code<500 else 'UNKNOWN',error='WhatsApp rejected the send or delivery could not be confirmed. Check before retrying.')
        except Exception:out.update(status='UNKNOWN',error='Send outcome unconfirmed. Do not retry automatically; check WhatsApp first.')
    with service.lock,service.store.connect() as db:
        service.store.put(db,'wa_outgoing',out)
        if out['status'] in {'ACCEPTED','SIMULATED'}:
            message={'id':'WAM-'+digest(out['id'])[:24],'thread_id':thread['id'],'case_id':out['case_id'],'direction':'AI','text':out['text'],'kind':'text','at':now(),'delivery':out['status'],'delivery_kind':out.get('delivery_kind'),'external_id':out.get('external_id'),'reply_to_message_id':out.get('reply_to_message_id'),'request_id':out.get('request_id'),'photo_context_message_id':out.get('photo_context_message_id')}
            service.store.put(db,'wa_message',message)
            if out.get('continues_request'):
                request=service.store.get(db,'wa_staff',out['request_id'])
                request.update(status='ANSWERED',progress='WAITING_CUSTOMER',last_outgoing_id=out['id'],last_relayed_at=now())
                service.store.put(db,'wa_staff',request)
            if out['status']=='ACCEPTED':
                from belive.whatsapp_channel import proof
                proof(service,db,{'phone_number_id':configuration()['phone_number_id']},last_reply_accepted=now())
            case=service.store.get(db,'case',out['case_id'])
            if out.get('delivery_kind') in {'SIMPLE','VERIFIED_STAFF_GUIDANCE','CLARIFICATION','REVIEWED_GUIDANCE','REVIEWED_TEAM_GUIDANCE'}:case['draft']=out['text'];service.store.put(db,'case',case)
            published=post(service.store,db,case,'AI_SUPPORT',out['text'],'wa-out-'+out['id'])
            if not any(x['thread_id']==thread['id'] and x['status']=='OPEN' for x in service.store.all(db,'wa_staff')):
                case.update(status='FOLLOW_UP',handoff=False,next_action='Await customer reply in WhatsApp',ack_due=None,followup_due=None,updated_at=now())
                case['revision']+=1;service.store.put(db,'case',case)
            from belive.reply_learning import usage
            candidates=shared_memory.tips(service,db) if shared_memory.enabled(service,db) else service.store.all(db,'reply_learning')
            tips=[x for x in candidates if x['id'] in out.get('tip_ids',[]) and x.get('approved')]
            usage(service,db,case,published['id'],tips)
        service.store.event(db,out['case_id'],'WHATSAPP_'+out['status'],'Simulated customer reply' if thread['simulated'] else 'WhatsApp reply delivery state recorded')
    return out


def command(service,db,name,p):
    from belive.service import require
    if name=='wa_simulate':
        image=None
        if p.get('image'):
            match=re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)',p['image'])
            require(match is not None,'Use a supported photo')
            image=(base64.b64decode(match[2],validate=True),match[1])
        text=bounded(p.get('text',''),0,6000);require(text or image,'Enter a message or attach a photo')
        return _ingest(service,db,p.get('customer','test_customer'),p.get('message_id') or 'sim-'+secrets.token_hex(12),text,'image' if image else 'text',datetime.now(timezone.utc).timestamp(),simulated=True,image=image)
    if name=='wa_knowledge':
        old=service.store.get(db,'wa_knowledge',p['id']) if p.get('id') else None
        if old:require(p.get('version')==old['version'],'SOP changed; reload before saving')
        require(p.get('confirmed') is True,'Review this as company-approved SOP before enabling it')
        if old and old.get('document_id'):
            require(all(p.get(k,old[k])==old[k] for k in ('title','text','source','property_ref')),'Re-import reviewed document sections to change their wording or scope')
        item={**(old or {}),'id':old['id'] if old else 'SOP-'+secrets.token_hex(8),'title':bounded(p.get('title'),3,160),'text':bounded(p.get('text'),8,18000),
              'property_ref':bounded(p.get('property_ref',''),0,80),'source':bounded(p.get('source'),3,400),'verified':True,'active':p.get('active',True) is True,
              'version':old['version']+1 if old else 1,'reviewed_by':p.get('_actor','staff'),'at':now()}
        service.store.version(db,'wa_knowledge',item);service.store.put(db,'wa_knowledge',item);return item
    thread=service.store.get(db,'wa_thread',p.get('thread_id'))
    if name not in {'wa_staff_reply','wa_staff_complete'} or not p.get('request_id'):require(p.get('revision')==thread['revision'],'Conversation changed; refresh before acting')
    if name=='wa_property':thread['property_ref']=bounded(p.get('property_ref',''),0,80)
    elif name=='wa_staff_complete':
        require(p.get('confirmed') is True,'Confirm the outcome before finishing this issue')
        item=service.store.get(db,'wa_staff',p.get('request_id'))
        require(item['thread_id']==thread['id'] and item['case_id']==thread['case_id'],'Choose an issue from this conversation')
        require(p.get('request_revision')==item.get('revision',0),'This issue changed; review the latest details')
        require(item['status']!='CLOSED','This issue is already finished')
        require(p.get('outcome') in {'RESOLVED','TEST_COMPLETED'},'Choose a verified resolution or completed test')
        note=bounded(p.get('note'),8,2000)
        outputs=[o for o in service.store.all(db,'wa_outgoing') if o.get('request_id')==item['id'] or (o.get('case_id')==item['case_id'] and o.get('reply_to_message_id')==item.get('origin_message_id'))]
        notices=[n for n in service.store.all(db,'outbox') if n['id']==item.get('notification_id') or n.get('support_request_id')==item['id']]
        require(not any(o['status'] in {'SENDING','UNKNOWN'} for o in outputs) and not any(n['status'] in {'SENDING','UNKNOWN'} for n in notices),'Check the unconfirmed delivery before finishing this issue')
        item.update(status='CLOSED',progress='CLOSED',closure_reason=p['outcome'],closure_note=note,closed_at=now(),closed_by=p.get('_actor','staff'),resolution_confirmed=p['outcome']=='RESOLVED',revision=item.get('revision',0)+1)
        service.store.put(db,'wa_staff',item)
        for out in outputs:
            if out['status']=='QUEUED':out.update(status='SUPERSEDED',error='This issue was finished before the queued reply was sent');service.store.put(db,'wa_outgoing',out)
        for turn in service.store.all(db,'wa_turn'):
            if turn.get('request_id')==item['id'] and turn['status']=='PENDING':turn['status']='SUPERSEDED';service.store.put(db,'wa_turn',turn)
        for notice in notices:
            if notice['status'] in {'PENDING_APPROVAL','NEEDS_DETAILS','APPROVED'}:
                notice.update(status='CANCELLED',error='Issue finished before notice dispatch: '+p['outcome']);service.store.put(db,'outbox',notice)
        thread['state']='WAITING_STAFF' if any(r['thread_id']==thread['id'] and r['status']=='OPEN' for r in service.store.all(db,'wa_staff')) else 'OPEN'
        # Finishing one topic does not close the chat, other issues, or create a lesson.
        service.store.event(db,item['case_id'],'WHATSAPP_ISSUE_FINISHED',p['outcome']+': '+note)
    elif name=='wa_staff_reply':
        require(p.get('confirmed') is True,'Verify the staff solution and any commitments before asking AI to relay them')
        guidance=bounded(p.get('guidance'),8,3000)
        requests=[x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id'] and x['case_id']==thread['case_id'] and x['status']=='OPEN']
        case=service.store.get(db,'case',thread['case_id'])
        require(case['status'] not in {'CLOSED','ANSWERED','SKIPPED','VERIFIED'},'This case is closed; use the current customer conversation')
        if p.get('request_id'):
            item=service.store.get(db,'wa_staff',p['request_id'])
            require(item['thread_id']==thread['id'] and item['case_id']==thread['case_id'],'Choose an issue from this conversation')
            require(p.get('request_revision')==item.get('revision',0),'This issue changed; review the latest staff request before saving')
            require(item['status']!='CLOSED','This issue is finished; a new customer report can reopen it')
        else:
            require(len(requests)<=1,'Several issues need help; select the exact issue in Staff help')
            item=requests[0] if requests else {'id':'WAS-'+secrets.token_hex(6),'thread_id':thread['id'],'case_id':thread['case_id'],'at':now(),'question':'Staff supplied follow-up guidance.'}
        origin_id=item.get('origin_message_id') or p.get('origin_message_id')
        require(not any(o.get('request_id')==item['id'] and o['status'] in {'SENDING','UNKNOWN'} for o in service.store.all(db,'wa_outgoing')),'A previous send is still unconfirmed. Check WhatsApp delivery before supplying another reply for this issue')
        if not origin_id and not p.get('request_id'):
            origin_id=next((m['id'] for m in service.store.all(db,'wa_message') if m['thread_id']==thread['id'] and m['case_id']==thread['case_id'] and m['direction']=='CUSTOMER'),None)
        require(origin_id is not None,'Choose the original customer message for this issue')
        origin=service.store.get(db,'wa_message',origin_id)
        require(origin['thread_id']==thread['id'] and origin['case_id']==thread['case_id'] and origin['direction']=='CUSTOMER','The original message must belong to this customer and case')
        item.update(status='ANSWERED',progress='GUIDANCE_READY',origin_message_id=origin_id,guidance=guidance,verified_by=p.get('_actor','staff'),revision=item.get('revision',0)+1,guidance_at=now());service.store.put(db,'wa_staff',item)
        message={'id':'WAM-'+secrets.token_hex(10),'thread_id':thread['id'],'case_id':thread['case_id'],'direction':'STAFF_INTERNAL','text':guidance,'kind':'staff','at':now(),'request_id':item['id']}
        service.store.put(db,'wa_message',message)
        item['guidance_message_id']=message['id'];service.store.put(db,'wa_staff',item)
        service.store.put(db,'wa_turn',{'id':'WAT-'+digest(message['id'])[:24],'thread_id':thread['id'],'message_id':message['id'],'case_id':thread['case_id'],'status':'PENDING','at':now(),'request_id':item['id'],'request_revision':item['revision']})
        thread['state']='WAITING_STAFF' if any(x['id']!=item['id'] for x in requests) else 'OPEN'
        case=service.store.get(db,'case',thread['case_id']);case.update(status='IN_PROGRESS',owner=p.get('_actor','staff'),ack_due=None);case['revision']+=1;service.store.put(db,'case',case)
    else:raise ValueError('Unsupported WhatsApp action')
    thread['revision']+=1;service.store.put(db,'wa_thread',thread)
    service.store.event(db,thread['case_id'],name.upper(),'Verified staff guidance queued for AI relay' if name=='wa_staff_reply' else 'Property scope updated')
    return {'thread_id':thread['id'],'revision':thread['revision']}


def snapshot(service,db):
    from belive import shared_memory
    threads=service.store.all(db,'wa_thread')[:60];messages=service.store.all(db,'wa_message');outputs=service.store.all(db,'wa_outgoing')
    result=[]
    for thread in threads:
        copy={k:v for k,v in thread.items() if k!='recipient'}
        from belive.customer_directory import selected
        copy['selected_customer_record']=selected(service,db,thread)
        copy['messages']=[{k:v for k,v in x.items() if k not in {'media_id','media'}}|{'has_photo':bool(x.get('media') or x.get('media_id')),'photo_ready':bool(x.get('media'))} for x in reversed(messages) if x['thread_id']==thread['id']][-40:]
        copy['outgoing']=[x for x in outputs if x['thread_id']==thread['id']][:8]
        copy['staff_requests']=[x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id']]
        notices={n['id']:n for n in service.store.all(db,'outbox')}
        copy['staff_requests']=[{**r,'notification':{k:notices.get(r.get('notification_id'),{}).get(k) for k in ('kind','target','status')}} for r in copy['staff_requests']]
        origin_ids={r.get('origin_message_id') for r in copy['staff_requests'] if r['case_id']==thread['case_id']}
        copy['request_originals']=[{k:m.get(k) for k in ('id','text','kind','at','case_id','direction')} for m in messages if m['thread_id']==thread['id'] and m['id'] in origin_ids]
        from belive.support_progress import snapshot as progress_snapshot
        from belive.maintenance_queue import view as maintenance_view
        copy['support_progress']=progress_snapshot(thread,messages,service.store.all(db,'wa_turn'),outputs,copy['staff_requests'])
        copy['staff_requests']=[{**r,'internal_work':maintenance_view(r)} if r.get('maintenance') else r for r in copy['staff_requests']]
        result.append(copy)
    c=configuration()
    from belive.whatsapp_channel import public,observed
    from belive.launch_status import current
    from belive.customer_directory import snapshot as directory_snapshot
    from belive.support_progress import delivery_health
    launcher=current(observed(service,db))
    health=delivery_health(threads,messages,outputs,service.store.all(db,'wa_turn'),launcher.get('started_at'),c['phone_number_id'])
    launcher['live_delivery_this_start']=bool(launcher['ready'] and observed(service,db)['company_number_matches'] and health['correlated_delivery_this_start'])
    return {'configured':ready(),'webhook_path':'/webhooks/whatsapp','connection_fields':{k:bool(c[k]) for k in ('access_token','app_secret','verify_token','phone_number_id','graph_version','webhook_host')},
            'tenant_report':public(service,db),'connection_status':observed(service,db),'launcher':launcher,'delivery_health':health,'signup_configuration':signup_configuration(),
            'threads':result,'customer_directory':directory_snapshot(service,db),'knowledge':shared_memory.knowledge(service,db),'documents':[{k:v for k,v in x.items() if k!='specification'} for x in shared_memory.documents(service,db)],
            'pending_turns':sum(x['status']=='PENDING' for x in service.store.all(db,'wa_turn'))}
