"""Short-lived, photo-scoped official lookup evidence; never reusable company policy."""
import re
from datetime import datetime,timezone
from urllib.parse import urlsplit
from belive.store import digest,now

def history(service,case_id):
    from belive.whatsapp_ai import domains
    with service.store.connect() as db:records=service.store.all(db,'wa_research')
    result=[]
    for r in records:
        if r.get('case_id')!=case_id:continue
        try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(r['retrieved_at'])).total_seconds()
        except (KeyError,ValueError,TypeError):continue
        if not 0<=age<=3600:continue
        if r.get('kind') not in {'COMPANY','TECHNICAL'} or r.get('purpose') not in {'GUIDANCE','IDENTIFICATION'} or not isinstance(r.get('sources'),list):continue
        try:allowed=domains(r['kind'])
        except ValueError:continue
        if r.get('domains')!=allowed:continue
        if any(not isinstance(s,dict) or not isinstance(s.get('url'),str) or urlsplit(s['url']).scheme!='https' or not any((urlsplit(s['url']).hostname or '')==d or (urlsplit(s['url']).hostname or '').endswith('.'+d) for d in allowed) for s in r['sources']):continue
        result.append(r)
    return result[:4]

def prime(context,record):
    context.update(research_attempted=True,research_summary=record['summary'],research_sources=record['sources'],
                   research_purpose=record['purpose'],identification_only=record['purpose']=='IDENTIFICATION',
                   research_retrieved_at=record['retrieved_at'],research_query=record['query'],research_kind=record['kind'])

def lookup(service,context,case_id,photo_id,query,kind,purpose):
    from belive import whatsapp_ai
    key=lambda q:re.sub(r'\s+',' ',q.strip()).casefold()
    cached=next((r for r in context.get('research_history',[]) if r['photo_message_id']==photo_id and r['kind']==kind and r['purpose']==purpose and key(r['query'])==key(query)),None)
    if cached:
        prime(context,cached);context['research_performed_this_turn']=True;return True
    found=whatsapp_ai.research(service,query,kind,purpose=purpose) if purpose=='IDENTIFICATION' else whatsapp_ai.research(service,query,kind)
    record={'id':'WAR-'+digest((case_id,photo_id,kind,purpose,key(query)))[:24],'case_id':case_id,'photo_message_id':photo_id,
            'kind':kind,'purpose':purpose,'query':query,'summary':found['summary'],'sources':found['sources'],'retrieved_at':now(),'domains':whatsapp_ai.domains(kind)}
    if photo_id:
        with service.store.connect() as db:service.store.put(db,'wa_research',record)
    prime(context,record);context['research_performed_this_turn']=True;return False
