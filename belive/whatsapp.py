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
    return {k:os.getenv(PREFIX+k.upper(),'').strip() for k in ('access_token','app_secret','verify_token','phone_number_id','graph_version','webhook_host')}


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
    filename=message.get('media',{}).get('file','')
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


def _ingest(service,db,sender,message_id,text,kind,timestamp,*,simulated=False,image=None,media_id=None):
    if not re.fullmatch(r'[A-Za-z0-9_.:=/+\-]{1,512}',message_id):raise ValueError('Invalid message identifier')
    namespace='SIM' if simulated else configuration()['phone_number_id']
    key='WAM-'+digest(namespace+':'+message_id)[:24]
    old=next((x for x in service.store.all(db,'wa_message') if x['id']==key),None)
    if old:return {'thread_id':old['thread_id'],'duplicate':True}
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}' if simulated else r'\d{6,20}',sender):raise ValueError('Invalid customer reference')
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
    service.store.put(db,'wa_message',message);service.store.put(db,'wa_thread',thread)
    turn={'id':'WAT-'+digest(key)[:24],'thread_id':tid,'message_id':key,'case_id':case['id'],'status':'PENDING','at':now()}
    service.store.put(db,'wa_turn',turn)
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
                                out['status']=new;service.store.put(db,'wa_outgoing',out)
                                if new in {'DELIVERED','READ'}:proof(service,db,metadata,last_reply_delivered=now())
                for msg in value.get('messages',[]):
                    kind=msg.get('type','unsupported')
                    text=msg.get('text',{}).get('body','') if kind=='text' else msg.get('image',{}).get('caption','')
                    result=_ingest(service,db,msg.get('from',''),msg.get('id',''),bounded(text,0,6000),kind,msg.get('timestamp',0),media_id=msg.get('image',{}).get('id') if kind=='image' else None)
                    proof(service,db,metadata,last_customer_message=now())
                    if not result['duplicate']:threads.add(result['thread_id'])
    return sorted(threads)


def _echo(service,db,message):
    """Mirror a mobile-app message as context; never treat it as a customer request."""
    external_id=message.get('id','');recipient=str(message.get('to','')).lstrip('+')
    if not re.fullmatch(r'[A-Za-z0-9_.:=/+\-]{1,512}',external_id) or not re.fullmatch(r'\d{6,20}',recipient):return
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


def _staff_request(service,db,thread,question,maintenance=False):
    existing=next((x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id'] and x['status']=='OPEN'),None)
    case=service.store.get(db,'case',thread['case_id'])
    was_maintenance=bool(existing and existing.get('maintenance'))
    item=existing or {'id':'WAS-'+secrets.token_hex(6),'thread_id':thread['id'],'case_id':case['id'],'status':'OPEN','at':now()}
    item.update(question=question or 'Please review this customer support request and provide verified guidance.',maintenance=maintenance or item.get('maintenance',False))
    service.store.put(db,'wa_staff',item)
    thread['state']='WAITING_STAFF'
    if not existing:
        if not case.get('handoff'):service.handoff(db,case,'WhatsApp customer needs staff guidance: '+item['question'])
        case['revision']+=1;service.store.put(db,'case',case)
        if maintenance:service.enqueue(db,case['id'],'STAFF_WORK_ORDER',item['question'],'Maintenance')
    elif maintenance and not was_maintenance:service.enqueue(db,case['id'],'STAFF_WORK_ORDER',item['question'],'Maintenance')


def sop(service,db,thread):
    from belive.company_sop import eligible
    from belive.shared_memory import knowledge
    return [x for x in knowledge(service,db) if eligible(service,db,x) and (not x.get('property_ref') or x['property_ref']==thread.get('property_ref'))]


def process_thread(service,tid):
    from belive.hermes_native import conversation_scope
    with conversation_scope(tid):return _process_thread(service,tid)


def _process_thread(service,tid):
    from belive import shared_memory
    with service.store.connect() as db:sharing=shared_memory.enabled(service,db)
    memory_ready=not sharing or shared_memory.sync(service).get('status')=='ONLINE'
    for _ in range(8):
        native_started_at=now()
        with service.lock,service.store.connect() as db:
            pending=[x for x in reversed(service.store.all(db,'wa_turn')) if x['thread_id']==tid and x['status']=='PENDING']
            if not pending:return
            # One response to the latest context, not one repeated response per queued fragment.
            turn=pending[-1]
            for stale in pending[:-1]:
                stale['status']='SUPERSEDED';service.store.put(db,'wa_turn',stale)
            thread=service.store.get(db,'wa_thread',tid);revision=thread['revision'];knowledge=sop(service,db,thread)
            turn['status']='PROCESSING';service.store.put(db,'wa_turn',turn)
            messages=[x for x in reversed(service.store.all(db,'wa_message')) if x['thread_id']==tid and x['case_id']==thread['case_id']][-20:]
            instructions=[x for x in reversed(service.store.all(db,'wa_staff')) if x['thread_id']==tid and x['case_id']==thread['case_id'] and x['status']=='ANSWERED'][-3:]
            from belive.reply_learning import matching
            question=next((x['text'] for x in reversed(messages) if x['direction']=='CUSTOMER'),'')
            tips=matching(service,db,question)
            from belive.experience_learning import experiences
            from belive.relevance import match_score
            lessons=sorted([x for x in experiences(service,db) if match_score(question,x['question'])>0],key=lambda x:match_score(question,x['question']),reverse=True)[:3]
            shared_snapshot={x['key']:x['revision'] for x in service.store.all(db,'memory_record')} if sharing else {}
        from belive.company_sop import retrieve,evidence
        selected,lookup_uncertain=retrieve(service,knowledge,messages)
        steps=['Relevant company SOP retrieved'] if selected else []
        context={'conversation':[{'role':x['direction'],'text':x['text'],'photo':x.get('vision')} for x in messages],
            'sop':evidence(selected),'sop_lookup_uncertain':lookup_uncertain,
            'approved_experiences':[{k:x[k] for k in ('id','question','answer','sample_data')} for x in lessons],
            'latest_sender':messages[-1]['direction'] if messages else '',
            'explicit_staff_requested':bool(messages and messages[-1]['direction']=='CUSTOMER' and whatsapp_ai.explicit_staff_request(messages[-1]['text'])),
            'staff_guidance':[{'id':x['id'],'verified_solution':x['guidance']} for x in instructions],
            'waiting_for_staff':thread['state']=='WAITING_STAFF','provided_property':thread.get('property_ref'),
            'research_sources':[],'research_attempted':False,'reviewed_writing_tips':[{'id':x['id'],'tip':x['tip']} for x in tips]}
        used_shared={('sop:'+x['id']) for x in selected}|{('document:'+x['document_id']) for x in selected if x.get('document_id')}
        used_shared|={('tip:'+x['id'].removeprefix('SHARED-')) for x in tips}|{('experience:'+x['id'].removeprefix('SHARED-')) for x in lessons}
        shared_revisions={k:shared_snapshot[k] for k in used_shared if k in shared_snapshot}
        try:
            if not memory_ready:raise ValueError('Shared knowledge unavailable; do not use a potentially revoked local rule')
            for message in messages[-3:]:
                if message['direction']!='CUSTOMER' or message['kind']!='image' or message.get('vision'):continue
                media=message.get('media') or download_image(service,message['media_id'])
                copy={**message,'media':media};data_url='data:'+media['mime']+';base64,'+base64.b64encode(media_path(service,copy).read_bytes()).decode()
                vision=whatsapp_ai.read_photo(service,data_url);steps.append('Photo read')
                with service.lock,service.store.connect() as db:
                    saved=service.store.get(db,'wa_message',message['id']);saved.update(media=media,vision=vision);service.store.put(db,'wa_message',saved)
                context['conversation'].append({'role':'PHOTO_OBSERVATION','text':vision})
            photos=[x.get('vision') for x in messages if x.get('vision')]
            photos += [x['text'] for x in context['conversation'] if x['role']=='PHOTO_OBSERVATION']
            customer_text=' '.join(x['text'] for x in messages if x['direction']=='CUSTOMER').lower()
            typed_code=bool(re.search(r'\b(?:[a-z]{1,3}\d{1,3}[a-z]?|\d{1,3}[a-z]{1,3})\b|(?:code|display|shows|reads|代码|显示)\s*(?:is|says|:|是)?\s*[a-z0-9-]{2,12}',customer_text,re.I))
            # A typed correction takes priority over a potentially mistaken OCR candidate.
            context['photo_confirmation_required']=bool(photos) and not typed_code
            if messages and messages[-1]['kind'] not in {'text','image','staff'}:raise ValueError('Only text and photos are supported')
            from belive.service import risk
            urgent=bool(messages and messages[-1]['direction']=='CUSTOMER' and risk(messages[-1]['text']))
            if urgent:
                draft={'reply':'Please move away from the hazard and do not touch or repair the equipment. If anyone is in immediate danger, contact local emergency services now. I am alerting our team urgently; you can keep messaging here.', 'needs_staff':True,'staff_question':'Urgent safety report: review immediately and arrange the appropriate response.','needs_maintenance':True,'research':'NONE','search_query':'','sources_used':[]}
            else:draft=whatsapp_ai.reply(service,context)
            steps.append('Conversation assessed')
            if draft['research']!='NONE' and draft['search_query']:
                if context['photo_confirmation_required']:
                    draft.update(reply='Could you type the exact code shown on the display and the appliance brand/model? Similar-looking codes can mean different things, so I want to check the right guidance.',research='NONE',needs_staff=False,needs_maintenance=False,staff_question='',sources_used=[])
                    steps.append('Asked customer to confirm photo details')
                else:
                    research=whatsapp_ai.research(service,draft['search_query'],draft['research'])
                    context.update(research_attempted=True,research_summary=research['summary'],research_sources=research['sources'])
                    steps.append('Company website checked' if draft['research']=='COMPANY' else 'Technical sources searched')
                    draft=whatsapp_ai.reply(service,context)
            whatsapp_ai.enforce_staff_request(draft,context)
            if not urgent and not whatsapp_ai.review(service,context,draft['reply'],draft):
                feedback=context.pop('_review_feedback',{})
                revised_context={**context,'revision_feedback':feedback,'previous_draft':draft['reply'],'research_attempted':True}
                draft=whatsapp_ai.reply(service,revised_context);whatsapp_ai.enforce_staff_request(draft,context)
                if not whatsapp_ai.review(service,context,draft['reply'],draft):raise ValueError('Reply did not pass safety/evidence review')
                steps.append('Reply revised after evidence review')
            steps.append('Reply reviewed')
        except Exception:
            draft={'reply':'I got your message. I cannot confirm a safe solution yet, so I am asking our team for guidance. You can keep sending details here; I will help you through the next steps.',
                   'needs_staff':True,'staff_question':'Review the customer message/photo and provide a verified safe response.','needs_maintenance':False,'sources_used':[]}
            steps.append('Staff fallback: AI, research or photo check could not complete')
        with service.lock,service.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');current=service.store.get(db,'wa_thread',tid);saved_turn=service.store.get(db,'wa_turn',turn['id'])
            live_shared={x['key']:x['revision'] for x in service.store.all(db,'memory_record')}
            if current['revision']!=revision or sop(service,db,current)!=knowledge or any(live_shared.get(k)!=v for k,v in shared_revisions.items()):
                saved_turn['status']='SUPERSEDED';service.store.put(db,'wa_turn',saved_turn)
                if not any(x['thread_id']==tid and x['status']=='PENDING' for x in service.store.all(db,'wa_turn')):
                    retry={**turn,'id':'WAT-'+secrets.token_hex(12),'status':'PENDING','at':now()};service.store.put(db,'wa_turn',retry)
                continue
            if draft['needs_staff']:_staff_request(service,db,current,draft['staff_question'],draft['needs_maintenance'])
            else:current['state']='WAITING_STAFF' if any(x['thread_id']==tid and x['status']=='OPEN' for x in service.store.all(db,'wa_staff')) else 'OPEN'
            out={'id':'WAO-'+digest(turn['id'])[:24],'thread_id':tid,'case_id':current['case_id'],'thread_revision':revision,
                 'text':draft['reply'],'status':'QUEUED','at':now(),'sources':draft.get('sources_used',[]),'research_sources':context['research_sources'],'steps':steps,'tip_ids':[x['id'] for x in tips],
                 'company_evidence':evidence([x for x in selected if x['id'] in draft.get('sources_used',[])]),
                 'knowledge_versions':{x['id']:x['version'] for x in selected}}
            out['shared_revisions']=shared_revisions
            scope_hash=hashlib.sha256(tid.encode()).hexdigest()[:24]
            executions=[x for x in service.store.all(db,'native_execution') if x.get('scope_hash')==scope_hash and x['at']>=native_started_at]
            out['native_execution_ids']=[x['id'] for x in executions]
            out['native_reply_verified']=any(x.get('role')=='WhatsApp Customer Support Agent' and x.get('engine')=='hermes-native' for x in executions)
            out['native_tools']=sorted({name for x in executions for name in x.get('executed_tools',[])})
            service.store.put(db,'wa_outgoing',out);service.store.put(db,'wa_thread',current)
            saved_turn.update(status='COMPLETE',steps=steps);service.store.put(db,'wa_turn',saved_turn)
        deliver(service,out['id'])


def deliver(service,out_id):
    from belive import shared_memory
    with service.store.connect() as db:
        pending=service.store.get(db,'wa_outgoing',out_id)
        requires_common=bool(pending.get('knowledge_versions') or pending.get('shared_revisions')) and shared_memory.enabled(service,db)
    if requires_common and shared_memory.sync(service).get('status')!='ONLINE':
        with service.lock,service.store.connect() as db:
            pending=service.store.get(db,'wa_outgoing',out_id)
            if pending['status']=='QUEUED':pending['error']='Shared knowledge is offline; waiting for a current revision before sending';service.store.put(db,'wa_outgoing',pending)
        return pending
    with service.lock,service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE');out=service.store.get(db,'wa_outgoing',out_id)
        if out['status']!='QUEUED':return out
        thread=service.store.get(db,'wa_thread',out['thread_id'])
        from belive.company_sop import eligible
        current_knowledge={x['id']:x for x in service.store.all(db,'wa_knowledge')}
        stale=any(k not in current_knowledge or not eligible(service,db,current_knowledge[k]) or current_knowledge[k]['version']!=v for k,v in out.get('knowledge_versions',{}).items())
        shared_now={x['key']:x['revision'] for x in service.store.all(db,'memory_record')}
        stale=stale or any(shared_now.get(k)!=v for k,v in out.get('shared_revisions',{}).items())
        if out['thread_revision']!=thread['revision'] or stale:out['status']='SUPERSEDED'
        elif datetime.now(timezone.utc).timestamp()-thread.get('last_customer_at',0)>86400:out.update(status='NEEDS_TEMPLATE',error='Customer service window expired; wait for the customer or use an approved WhatsApp template.')
        elif thread['simulated']:out['status']='SIMULATED'
        elif not ready():out.update(status='NOT_CONFIGURED',error='WhatsApp company connection is not configured.')
        else:out['status']='SENDING'
        service.store.put(db,'wa_outgoing',out)
        if stale and out['thread_revision']==thread['revision'] and not any(x['thread_id']==thread['id'] and x['status']=='PENDING' for x in service.store.all(db,'wa_turn')):
            service.store.put(db,'wa_turn',{'id':'WAT-'+secrets.token_hex(12),'thread_id':thread['id'],'case_id':thread['case_id'],'message_id':out['id'],'status':'PENDING','at':now()})
    if out['status']=='SENDING':
        c=configuration()
        try:
            result=request_json('https://graph.facebook.com/'+c['graph_version']+'/'+c['phone_number_id']+'/messages',c['access_token'],payload={
                'messaging_product':'whatsapp','recipient_type':'individual','to':thread['recipient'],'type':'text','text':{'body':out['text']}})
            external=result.get('messages',[{}])[0].get('id')
            if not isinstance(external,str) or not external:raise ValueError('No message receipt')
            out.update(status='ACCEPTED',external_id=external)
        except HTTPError as exc:out.update(status='FAILED' if 400<=exc.code<500 else 'UNKNOWN',error='WhatsApp rejected the send or delivery could not be confirmed. Check before retrying.')
        except Exception:out.update(status='UNKNOWN',error='Send outcome unconfirmed. Do not retry automatically; check WhatsApp first.')
    with service.lock,service.store.connect() as db:
        service.store.put(db,'wa_outgoing',out)
        if out['status'] in {'ACCEPTED','SIMULATED'}:
            message={'id':'WAM-'+digest(out['id'])[:24],'thread_id':thread['id'],'case_id':out['case_id'],'direction':'AI','text':out['text'],'kind':'text','at':now(),'delivery':out['status'],'external_id':out.get('external_id')}
            service.store.put(db,'wa_message',message)
            if out['status']=='ACCEPTED':
                from belive.whatsapp_channel import proof
                proof(service,db,{'phone_number_id':configuration()['phone_number_id']},last_reply_accepted=now())
            case=service.store.get(db,'case',out['case_id']);published=post(service.store,db,case,'AI_SUPPORT',out['text'],'wa-out-'+out['id'])
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
    thread=service.store.get(db,'wa_thread',p.get('thread_id'));require(p.get('revision')==thread['revision'],'Conversation changed; refresh before acting')
    if name=='wa_property':thread['property_ref']=bounded(p.get('property_ref',''),0,80)
    elif name=='wa_staff_reply':
        require(p.get('confirmed') is True,'Verify the staff solution and any commitments before asking AI to relay them')
        guidance=bounded(p.get('guidance'),8,3000)
        requests=[x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id'] and x['status']=='OPEN']
        item=requests[0] if requests else {'id':'WAS-'+secrets.token_hex(6),'thread_id':thread['id'],'case_id':thread['case_id'],'at':now(),'question':'Staff supplied follow-up guidance.'}
        item.update(status='ANSWERED',guidance=guidance,verified_by=p.get('_actor','staff'));service.store.put(db,'wa_staff',item)
        message={'id':'WAM-'+secrets.token_hex(10),'thread_id':thread['id'],'case_id':thread['case_id'],'direction':'STAFF_INTERNAL','text':guidance,'kind':'staff','at':now()}
        service.store.put(db,'wa_message',message)
        service.store.put(db,'wa_turn',{'id':'WAT-'+digest(message['id'])[:24],'thread_id':thread['id'],'message_id':message['id'],'case_id':thread['case_id'],'status':'PENDING','at':now()})
        thread['state']='OPEN'
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
        copy['messages']=[{k:v for k,v in x.items() if k not in {'media_id','media'}}|{'has_photo':bool(x.get('media') or x.get('media_id'))} for x in reversed(messages) if x['thread_id']==thread['id']][-40:]
        copy['outgoing']=[x for x in outputs if x['thread_id']==thread['id']][:8]
        copy['staff_requests']=[x for x in service.store.all(db,'wa_staff') if x['thread_id']==thread['id']]
        result.append(copy)
    c=configuration()
    from belive.whatsapp_channel import public,observed
    return {'configured':ready(),'webhook_path':'/webhooks/whatsapp','connection_fields':{k:bool(c[k]) for k in ('access_token','app_secret','verify_token','phone_number_id','graph_version','webhook_host')},
            'tenant_report':public(service,db),'connection_status':observed(service,db),
            'threads':result,'knowledge':shared_memory.knowledge(service,db),'documents':[{k:v for k,v in x.items() if k!='specification'} for x in shared_memory.documents(service,db)],
            'pending_turns':sum(x['status']=='PENDING' for x in service.store.all(db,'wa_turn'))}
