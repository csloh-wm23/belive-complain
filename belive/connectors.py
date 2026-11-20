"""Bounded official reads and an approved notification gateway. Never automate login."""
import hashlib
import hmac
import json
import os
import re
import secrets
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from belive.store import bounded,now

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def request_json(url,token='',payload=None,headers=None,method=None):
    request_headers={'Accept':'application/json',**(headers or {})}
    if token:request_headers['Authorization']='Bearer '+token
    body=None if payload is None else json.dumps(payload).encode()
    if body is not None:request_headers['Content-Type']='application/json'
    with build_opener(NoRedirect).open(Request(url,data=body,headers=request_headers,method=method),timeout=20) as response:
        data=response.read(1_000_001)
        if len(data)>1_000_000:raise ValueError('RESPONSE_TOO_LARGE')
        return json.loads(data) if data else {}

def validate_source(p):
    platform=p.get('platform');resource=p.get('resource','')
    if p.get('authorised') is not True:raise ValueError('Confirm this exact public API resource is authorised for your use')
    if platform=='GOOGLE':
        valid=bool(re.fullmatch(r'accounts/[0-9]+/locations/[0-9]+',resource))
    elif platform=='FACEBOOK':valid=bool(re.fullmatch(r'[0-9_]+/(?:feed|comments)',resource))
    elif platform=='THREADS':valid=bool(re.fullmatch(r'[0-9]+/replies',resource))
    else:valid=False
    if not valid:raise ValueError('Use a selected Google location, Facebook Page feed/post comments, or Threads post replies resource')
    return {'id':p.get('id') or 'SRC-'+secrets.token_hex(5),'platform':platform,'resource':resource,
            'enabled':p.get('enabled',True) is True,'authorised':True,'last_scan':None,'next_scan':now(),'status':'READY','error':''}

def public_link_platform(value):
    from urllib.parse import urlsplit
    if not isinstance(value,str) or len(value)>2000 or re.search(r'\s',value):
        raise ValueError('Enter a public Google review, Facebook or Threads link')
    url=urlsplit(value)
    host=url.netloc.lower()
    if url.scheme!='https':
        raise ValueError('Use an HTTPS platform link')
    if ((host in {'google.com','www.google.com'} and url.path.startswith(('/maps/','/travel/hotels/')))
            or host in {'maps.app.goo.gl','maps.google.com'}
            or (host=='g.page' and url.path)):
        return 'GOOGLE'
    if host in {'facebook.com','www.facebook.com','m.facebook.com','fb.watch'} and url.path not in {'','/'}:
        return 'FACEBOOK'
    if host in {'threads.com','www.threads.com','threads.net','www.threads.net'} and '/post/' in url.path:
        return 'THREADS'
    raise ValueError('Only Google review, Facebook and Threads links are supported')


def google_review_share_link(value):
    message = 'Copy the link from Share on the individual Google review.'
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError(message)
    value = value.strip()
    try:
        platform = public_link_platform(value)
    except ValueError:
        raise ValueError(message) from None
    url = urlsplit(value)
    if platform == 'GOOGLE' and (
        (url.netloc.lower() == 'maps.app.goo.gl' and re.fullmatch(r'/[A-Za-z0-9_-]+/?', url.path))
        or (url.netloc.lower() in {'www.google.com', 'google.com', 'maps.google.com'}
            and (url.path.startswith('/maps/reviews/')
                or re.fullmatch(r'/maps/contrib/\d+/place/[A-Za-z0-9_-]+(?:/.*)?', url.path)))
    ):
        return value
    raise ValueError(message)


def read_source(source):
    platform,resource=source['platform'],source['resource']
    token=os.getenv('BELIVE_'+platform+'_TOKEN','')
    if not token:raise RuntimeError('CONNECTOR_NOT_CONFIGURED')
    if platform=='GOOGLE':
        result=request_json('https://mybusiness.googleapis.com/v4/'+resource+'/reviews?'+urlencode({'pageSize':25,'orderBy':'updateTime desc'}),token)
        return [{'id':resource+'/'+item['reviewId'],'text':item.get('comment','')} for item in result.get('reviews',[])[:25] if item.get('comment')]
    if platform=='FACEBOOK':
        version=os.getenv('BELIVE_FACEBOOK_VERSION','')
        if not re.fullmatch(r'v\d+\.\d+',version):raise RuntimeError('FACEBOOK_VERSION_REQUIRED')
        result=request_json('https://graph.facebook.com/'+version+'/'+resource+'?'+urlencode({'fields':'id,message,created_time','limit':25}),token)
        return [{'id':item['id'],'text':item.get('message','')} for item in result.get('data',[])[:25] if item.get('message')]
    result=request_json('https://graph.threads.net/v1.0/'+resource+'?'+urlencode({'fields':'id,text,timestamp','limit':25}),token)
    return [{'id':item['id'],'text':item.get('text','')} for item in result.get('data',[])[:25] if item.get('text')]

def scan_interval(store,db):
    settings=store.all(db,'source_schedule')
    return settings[0]['minutes'] if settings else 15


def scan(service,source_id):
    from belive.service import due
    with service.store.connect() as db:source=service.store.get(db,'source',source_id)
    if not source['enabled']:raise ValueError('Resume checks for the selected source before scanning')
    try:
        rows=read_source(source)
        results=[]
        for item in rows:
            p={'title':'Public tenant feedback','description':item['text'],'platform':source['platform'],'source_id':item['id']}
            if len(p['description'].strip())<10:continue
            # Content hash distinguishes immutable edits while duplicate polls reuse results.
            from belive.store import digest
            c=service.command('intake',p,'scan-'+digest(json.dumps(p,sort_keys=True)))
            results.append(c['id'])
        source.update(status='COMPLETED',error='',last_scan=now(),last_count=len(set(results)))
    except Exception as exc:
        source.update(status='FAILED',error=str(exc) if str(exc) in {'CONNECTOR_NOT_CONFIGURED','FACEBOOK_VERSION_REQUIRED'} else 'CONNECTOR_READ_FAILED',last_scan=now(),last_count=0)
        results=[]
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=service.store.get(db,'source',source_id)
        if current['platform']==source['platform'] and current['resource']==source['resource']:
            for field in ('status','error','last_scan','last_count'):
                current[field]=source[field]
            current['next_scan']=due(scan_interval(service.store,db))
            service.store.put(db,'source',current)
            service.store.event(db,source_id,'SOURCE_SCAN_'+source['status'],source.get('error') or str(len(set(results)))+' source results recorded')
    return list(dict.fromkeys(results))

def deliver(service,message_id):
    from belive.service import support_notification
    with service.lock,service.store.connect() as db:
        item=service.store.get(db,'outbox',message_id)
        if not support_notification(item):raise ValueError('Notification is outside tenant complaint support')
        if item['status']!='APPROVED':raise ValueError('Delivery requires an approved message that has not been attempted')
        url=os.getenv('BELIVE_NOTIFICATION_URL','');secret=os.getenv('BELIVE_NOTIFICATION_SECRET','')
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or not secret:
            raise ValueError('Configure an HTTPS notification gateway and signing secret first')
        item['status']='SENDING';service.store.put(db,'outbox',item)
        service.store.event(db,item['entity'],'DELIVERY_ATTEMPT',item['id'])
    payload={k:item[k] for k in ('id','entity','kind','text','target')}
    raw=json.dumps(payload).encode();signature=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
    try:
        response=request_json(url,payload=payload,headers={'Idempotency-Key':item['id'],'X-BeLive-Signature':signature})
        if response.get('idempotency_key')!=item['id'] or response.get('status')!='delivered' or not isinstance(response.get('receipt_id'),str):
            raise ValueError('UNCERTAIN_RECEIPT')
        item.update(status='DELIVERED',outcome=bounded(response['receipt_id'],1,200))
    except Exception:
        item.update(status='UNKNOWN',outcome='Delivery could not be confirmed. Check the gateway; do not retry automatically.')
    with service.lock,service.store.connect() as db:
        service.store.put(db,'outbox',item);service.store.event(db,item['entity'],'DELIVERY_'+item['status'],item['id'])
    return item
