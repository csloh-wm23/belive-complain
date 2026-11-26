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
from belive.credentials import get_value,credential_scope

THREADS_API = 'https://graph.threads.com/v1.0/'
THREADS_POST_LIMIT = 25
THREADS_REPLY_LIMIT = 25
THREADS_IMPORT_LIMIT = 25

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
    elif platform=='THREADS':valid=bool(re.fullmatch(r'[0-9]+/(?:replies|threads)',resource))
    else:valid=False
    if not valid:raise ValueError('Use a selected Google location, Facebook Page feed/post comments, or Threads post replies resource')
    source={'id':p.get('id') or 'SRC-'+secrets.token_hex(5),'platform':platform,'resource':resource,
            'enabled':p.get('enabled',True) is True,'authorised':True,'last_scan':None,'next_scan':now(),'status':'READY','error':''}
    if platform=='THREADS' and resource.endswith('/threads') and p.get('account_name'):
        if not isinstance(p['account_name'],str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,60}',p['account_name']):
            raise ValueError('Invalid Threads account name')
        source['account_name']=p['account_name']
    return source


def resolve_threads_account(payload):
    """Bind the friendly setup option to the authenticated account, before saving it."""
    if payload.get('authorised') is not True:
        raise ValueError('Confirm this connected Threads account is authorised for collection')
    token=get_value('BELIVE_THREADS_TOKEN','')
    if not token:
        raise ValueError('Save your Threads access token in Connection settings first')
    try:
        profile=request_json(THREADS_API+'me?'+urlencode({'fields':'id,username'}),token)
        account_id=profile.get('id');username=profile.get('username')
        if not isinstance(account_id,str) or not re.fullmatch(r'[0-9]+',account_id):
            raise ValueError()
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,60}',username):
            raise ValueError()
    except Exception:
        raise ValueError('Threads account could not be read. Check the saved token and its permissions.') from None
    return {**payload,'resource':account_id+'/threads','account_name':username}


def _threads_item(item,parent_id=None):
    source_id=item.get('id')
    if not isinstance(source_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}',source_id):
        raise ValueError('Invalid Threads reply identifier')
    result={'id':source_id,'text':item.get('text','')}
    if parent_id:result['parent_source_id']=parent_id
    if isinstance(item.get('timestamp'),str):result['source_created_at']=item['timestamp'][:80]
    link=item.get('permalink','')
    if isinstance(link,str) and len(link)<=2000:
        parsed=urlsplit(link)
        if (parsed.scheme=='https' and parsed.netloc.lower() in {'threads.com','www.threads.com','threads.net','www.threads.net'}
                and re.fullmatch(r'/(?:@[^/]+/post|t)/[A-Za-z0-9_-]+/?',parsed.path)):
            result['public_url']=parsed._replace(query='',fragment='').geturl()
    return result


def _threads_data(response):
    if not isinstance(response,dict) or response.get('error') or not isinstance(response.get('data'),list):
        raise ValueError('Invalid Threads API collection response')
    return response['data']

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
    token=get_value('BELIVE_'+platform+'_TOKEN','')
    if not token:raise RuntimeError('CONNECTOR_NOT_CONFIGURED')
    if platform=='GOOGLE':
        result=request_json('https://mybusiness.googleapis.com/v4/'+resource+'/reviews?'+urlencode({'pageSize':25,'orderBy':'updateTime desc'}),token)
        return [{'id':resource+'/'+item['reviewId'],'text':item.get('comment','')} for item in result.get('reviews',[])[:25] if item.get('comment')]
    if platform=='FACEBOOK':
        version=get_value('BELIVE_FACEBOOK_VERSION','')
        if not re.fullmatch(r'v\d+\.\d+',version):raise RuntimeError('FACEBOOK_VERSION_REQUIRED')
        result=request_json('https://graph.facebook.com/'+version+'/'+resource+'?'+urlencode({'fields':'id,message,created_time','limit':25}),token)
        return [{'id':item['id'],'text':item.get('message','')} for item in result.get('data',[])[:25] if item.get('message')]
    if resource.endswith('/threads'):
        result=request_json(THREADS_API+resource+'?'+urlencode({'fields':'id,text,permalink,timestamp','limit':THREADS_POST_LIMIT}),token)
        rows=[]
        for post in _threads_data(result)[:THREADS_POST_LIMIT]:
            post_id=post.get('id')
            if not isinstance(post_id,str) or not re.fullmatch(r'[0-9]+',post_id):
                raise ValueError('Invalid Threads post identifier')
            replies=request_json(THREADS_API+post_id+'/replies?'+urlencode({'fields':'id,text,permalink,timestamp','limit':THREADS_REPLY_LIMIT}),token)
            rows.extend(_threads_item(item,post_id) for item in _threads_data(replies)[:THREADS_REPLY_LIMIT] if item.get('text'))
        return rows
    result=request_json(THREADS_API+resource+'?'+urlencode({'fields':'id,text,permalink,timestamp','limit':THREADS_REPLY_LIMIT}),token)
    # Older single-post sources retain their IDs and duplicate behaviour.
    return [_threads_item(item)
            for item in _threads_data(result)[:THREADS_REPLY_LIMIT] if item.get('text')]

def scan_interval(store,db):
    settings=store.all(db,'source_schedule')
    return settings[0]['minutes'] if settings else 15


def scan(service,source_id):
    from belive.service import due
    with service.store.connect() as db:source=service.store.get(db,'source',source_id)
    if not source['enabled']:raise ValueError('Resume checks for the selected source before scanning')
    try:
        with credential_scope(service.store.path):rows=read_source(source)
        from belive.store import digest,redact
        account_mode=source['platform']=='THREADS' and source['resource'].endswith('/threads')
        seen_count=len(rows);deferred_count=0
        with service.store.connect() as db:
            before_ids={c['id'] for c in service.store.all(db,'case')}
            if account_mode:
                # Process unseen immutable versions first; existing replies must not fill the import cap.
                unique={}
                for item in rows:
                    text=item.get('text','')
                    if not isinstance(text,str) or not 10<=len(text.strip())<=6000:continue
                    fingerprint=digest(redact(text.strip()))
                    if not db.execute('SELECT 1 FROM sources WHERE platform=? AND source_id=? AND hash=?',
                                      ('THREADS',item['id'],fingerprint)).fetchone():
                        unique[(item['id'],fingerprint)]=item
                pending=sorted(unique.values(),key=lambda item:(item.get('source_created_at',''),item['id']))
                rows=pending[:THREADS_IMPORT_LIMIT]
                deferred_count=max(0,len(pending)-len(rows))
        results=[]
        for item in rows:
            p={'title':'Public tenant feedback','description':item['text'],'platform':source['platform'],'source_id':item['id']}
            if len(p['description'].strip())<10:continue
            # Content hash distinguishes immutable edits while duplicate polls reuse results.
            c=service.command('intake',p,'scan-'+digest(json.dumps(p,sort_keys=True)))
            evidence={k:item[k] for k in ('public_url','source_created_at','parent_source_id') if item.get(k)}
            if evidence:
                with service.lock,service.store.connect() as db:
                    current_case=service.store.get(db,'case',c['id'])
                    if any(current_case.get(k)!=v for k,v in evidence.items()):
                        current_case.update(evidence)
                        current_case['revision']+=1
                        service.store.put(db,'case',current_case)
                        service.store.event(db,c['id'],'API_SOURCE_LINKED','Original API source link and timestamp retained')
            results.append(c['id'])
        source.update(status='COMPLETED',error='',last_scan=now(),last_count=len(set(results)),
                      last_seen_count=seen_count,last_new_count=len(set(results)-before_ids),last_deferred_count=deferred_count)
    except Exception as exc:
        source.update(status='FAILED',error=str(exc) if str(exc) in {'CONNECTOR_NOT_CONFIGURED','FACEBOOK_VERSION_REQUIRED'} else 'CONNECTOR_READ_FAILED',last_scan=now(),last_count=0,
                      last_seen_count=0,last_new_count=0,last_deferred_count=0)
        results=[]
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=service.store.get(db,'source',source_id)
        if current['platform']==source['platform'] and current['resource']==source['resource']:
            for field in ('status','error','last_scan','last_count','last_seen_count','last_new_count','last_deferred_count'):
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
        url=get_value('BELIVE_NOTIFICATION_URL','',service.store.path);secret=get_value('BELIVE_NOTIFICATION_SECRET','',service.store.path)
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
