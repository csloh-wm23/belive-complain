"""Explicitly reviewed Google Business Profile replies through the official API."""
import os
import re
from urllib.error import HTTPError
from belive.connectors import request_json
from belive.credentials import get_value
from belive.store import bounded, digest, now


def resource(case):
    if case.get('platform')!='GOOGLE' or case.get('entrypoint')!='PUBLIC_SOURCE':return None
    match=re.fullmatch(r'(accounts/\d+/locations/\d+)/(?:reviews/)?([A-Za-z0-9_-]+)',case.get('source_id',''))
    return match[1]+'/reviews/'+match[2] if match else None


def readiness(store,db,case):
    name=resource(case)
    if not name:return {'ready':False,'reason':'Direct posting needs this review imported through an authorised Google Business Profile API source; a public Maps link alone is insufficient.'}
    location=name.split('/reviews/')[0]
    allowed=any(s['platform']=='GOOGLE' and s.get('authorised') and s['resource']==location for s in store.all(db,'source'))
    if not allowed:return {'ready':False,'reason':'Configure the company-authorised Google Business Profile location under Public reviews.'}
    if not get_value('BELIVE_GOOGLE_TOKEN',database=store.path) or os.getenv('BELIVE_GOOGLE_REPLY_ENABLED','').lower()!='true':
        return {'ready':False,'reason':'Company Google authorization and direct reply publishing must be configured locally first.'}
    if case.get('google_reply',{}).get('status') in {'SENDING','UNKNOWN'}:
        return {'ready':False,'reason':'The previous posting result is unconfirmed. Check the original Google review before another attempt.'}
    if case['status'] in {'CLOSED','ANSWERED','SKIPPED'}:return {'ready':False,'reason':'Reopen this case before publishing.'}
    return {'ready':True,'reason':'Posts the reviewed text publicly as the company on Google.'}


def publish(service,p,actor,key):
    from belive.service import require
    require(isinstance(key,str) and 8<=len(key)<=150,'A request idempotency key is required')
    text=bounded(p.get('text'),1,3000)
    require(p.get('confirmed') is True,'Review the exact reply and confirm public posting first')
    attempt_id=digest(str(p.get('id'))+':'+key)
    fingerprint=digest(str(p.get('id'))+':'+text+':'+str(p.get('replace_existing') is True))
    with service.lock,service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        attempts=[a for a in service.store.all(db,'google_reply_attempt') if a['id']==attempt_id]
        if attempts:
            require(attempts[0]['fingerprint']==fingerprint,'Idempotency mismatch')
            return attempts[0]['result']
        case=service.store.get(db,'case',p.get('id'))
        require(case['revision']==p.get('revision'),'Case changed; reload before posting')
        ready=readiness(service.store,db,case);require(ready['ready'],ready['reason'])
        if case.get('google_reply',{}).get('status')=='POSTED' and case['google_reply']['text']==text:return case['google_reply']
        name=resource(case);description=case['description']
        result={'status':'SENDING','text':text,'at':now(),'resource':name,'actor':actor}
        case['google_reply']=result;case['revision']+=1
        service.store.put(db,'case',case)
        service.store.put(db,'google_reply_attempt',{'id':attempt_id,'fingerprint':fingerprint,'result':result})
        service.store.event(db,case['id'],'GOOGLE_REPLY_STARTED',actor+': reviewed public reply requested')
    sending=False
    try:
        token=get_value('BELIVE_GOOGLE_TOKEN',database=service.store.path);url='https://mybusiness.googleapis.com/v4/'+name
        review=request_json(url,token)
        require(review.get('name')==name,'Google returned a different review; no reply posted')
        require(bounded(review.get('comment'),1,6000)==description,'The Google review changed; import and review its latest text before posting')
        existing=review.get('reviewReply',{}).get('comment','')
        require(not existing or existing==text or p.get('replace_existing') is True,'This review already has a company reply. Explicitly allow replacing it before posting')
        if existing==text:receipt=review['reviewReply']
        else:
            sending=True
            receipt=request_json(url+'/reply',token,payload={'comment':text},method='PUT')
        require(receipt.get('comment')==text and isinstance(receipt.get('updateTime'),str),'Google posting result could not be confirmed')
        result.update(status='POSTED',google_update_time=receipt['updateTime'],detail='Google confirmed the reply. Check the original review for public display.')
    except Exception as exc:
        rejected=isinstance(exc,HTTPError) and 400<=exc.code<500
        status='UNKNOWN' if sending and not rejected else 'FAILED'
        if isinstance(exc,ValueError) and not sending:detail=str(exc)
        elif rejected:detail=f'Google rejected the request (HTTP {exc.code}). Check company access and authorization.'
        else:detail='Posting could not be confirmed. Check the original review before retrying.' if sending else 'Could not read the Google review. No reply was sent.'
        result.update(status=status,detail=detail)
    with service.lock,service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=service.store.get(db,'case',p['id'])
        current['google_reply']=result;current['revision']+=1
        service.store.put(db,'case',current)
        service.store.put(db,'google_reply_attempt',{'id':attempt_id,'fingerprint':fingerprint,'result':result})
        service.store.event(db,current['id'],'GOOGLE_REPLY_'+result['status'],actor+': '+result['detail'])
    return result
