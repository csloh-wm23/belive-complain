"""Bounded official reads and an approved notification gateway. Never automate login."""
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode,urlsplit,parse_qsl,unquote
from urllib.request import Request,build_opener,HTTPRedirectHandler
from belive.store import bounded,now
from belive.credentials import get_value,credential_scope

THREADS_API = 'https://graph.threads.com/v1.0/'
THREADS_POST_LIMIT = 25
THREADS_REPLY_LIMIT = 25
THREADS_IMPORT_LIMIT = 25
FACEBOOK_POST_LIMIT = 25
FACEBOOK_COMMENT_LIMIT = 25
FACEBOOK_IMPORT_LIMIT = 25
DEFAULT_LOOKBACK_DAYS = 30
FACEBOOK_LOOKBACK_DAYS = DEFAULT_LOOKBACK_DAYS

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
    elif platform=='FACEBOOK':valid=bool(re.fullmatch(r'(?:\d+/feed|\d+(?:_\d+)*/comments)',resource))
    elif platform=='THREADS':valid=bool(re.fullmatch(r'[0-9]+/(?:replies|threads)',resource))
    else:valid=False
    if not valid:raise ValueError('Use a selected Google location, Facebook Page feed/post comments, or Threads post replies resource')
    source={'id':p.get('id') or 'SRC-'+secrets.token_hex(5),'platform':platform,'resource':resource,
            'enabled':p.get('enabled',True) is True,'authorised':True,'last_scan':None,'next_scan':now(),'status':'READY','error':''}
    days=p.get('lookback_days',DEFAULT_LOOKBACK_DAYS)
    if type(days) is not int or not 1<=days<=365:raise ValueError('Lookback must be a whole number from 1 to 365 days')
    source['lookback_days']=days
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

def facebook_permalink_url(value, *, comment=False):
    """Keep safe API-returned object links, never a guessed URL built from an ID."""
    if (not isinstance(value,str) or not value or len(value)>2000
            or re.search(r'[\x00-\x20\x7f\\]',value)
            or re.search(r'[\x00-\x20\x7f\\]',unquote(value))):return None
    try:
        url=urlsplit(value)
        if url.scheme!='https' or url.netloc.lower() not in {'facebook.com','www.facebook.com','m.facebook.com'}:return None
        kept=[];seen=set()
        for key,number in parse_qsl(url.query,keep_blank_values=True):
            if key not in {'id','story_fbid','fbid','v','comment_id','reply_comment_id'}:continue
            if key in seen:return None
            valid=(re.fullmatch(r'(?:\d+|pfbid[A-Za-z0-9]+)',number) if key=='story_fbid'
                   else re.fullmatch(r'\d+(?:_\d+)*',number))
            if not valid:return None
            seen.add(key);kept.append((key,number))
        path=url.path
        post_path=bool(re.fullmatch(r'/[A-Za-z0-9_.-]+/(?:posts|videos)/[A-Za-z0-9_-]+/?',path)
                       or re.fullmatch(r'/(?:\d+(?:_\d+)*|pfbid[A-Za-z0-9]+)/?',path))
        php_path=path in {'/permalink.php','/story.php'} and {'id','story_fbid'}<=seen
        photo_path=path in {'/photo.php','/photo/','/photo'} and 'fbid' in seen
        watch_path=path in {'/watch','/watch/'} and 'v' in seen
        if not (post_path or php_path or photo_path or watch_path):return None
        if comment and not ({'comment_id','reply_comment_id'}&seen):return None
        return url._replace(netloc=url.netloc.lower(),query=urlencode(kept),fragment='').geturl()
    except ValueError:return None


def _facebook_data(response):
    if not isinstance(response,dict) or response.get('error') or not isinstance(response.get('data'),list):
        raise ValueError('Invalid Facebook API collection response')
    return response['data']


def _collection_window(source):
    days=source.get('lookback_days',DEFAULT_LOOKBACK_DAYS)
    if type(days) is not int or not 1<=days<=365:raise ValueError('Invalid source lookback')
    current=datetime.now(timezone.utc)
    return current-timedelta(days=days),current


def _source_datetime(value):
    if not isinstance(value,str) or len(value)>80:return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError,OverflowError):return None


def _recent(value,window):
    parsed=_source_datetime(value)
    return parsed is not None and window[0]<=parsed<=window[1]


def _facebook_item(item,parent_id,parent_url,page_id):
    if not isinstance(item,dict):return None
    source_id=item.get('id')
    if not isinstance(source_id,str) or not re.fullmatch(r'\d+(?:_\d+)*',source_id):
        raise ValueError('Invalid Facebook comment identifier')
    author=item.get('from') or {}
    if isinstance(author,dict) and author.get('id')==page_id:return None
    text=item.get('message','')
    if not isinstance(text,str) or not text.strip():return None
    result={'id':source_id,'text':text,'parent_source_id':parent_id,'public_source_kind':'FACEBOOK_COMMENT'}
    link=facebook_permalink_url(item.get('permalink_url'),comment=True)
    if link:result['public_url']=link
    if parent_url:result['parent_public_url']=parent_url
    if isinstance(item.get('created_time'),str):result['source_created_at']=item['created_time'][:80]
    return result


def _facebook_comments(base,parent_id,parent_url,page_id,token,window):
    response=request_json(base+parent_id+'/comments?'+urlencode({
        'fields':'id,message,from,created_time,permalink_url','limit':FACEBOOK_COMMENT_LIMIT,
        'filter':'toplevel','order':'reverse_chronological'}),token)
    rows=[]
    for item in _facebook_data(response)[:FACEBOOK_COMMENT_LIMIT]:
        if not isinstance(item,dict) or not _recent(item.get('created_time'),window):continue
        row=_facebook_item(item,parent_id,parent_url,page_id)
        if row:rows.append(row)
    return rows


def _facebook_source(source,token,version,window):
    resource=source['resource'];base='https://graph.facebook.com/'+version+'/'
    if resource.endswith('/feed'):
        page_id=resource.split('/')[0]
        cutoff,current=window
        response=request_json(base+page_id+'/posts?'+urlencode({
            'fields':'id,from,permalink_url,created_time','limit':FACEBOOK_POST_LIMIT,
            'since':int(cutoff.timestamp())}),token)
        rows=[]
        for post in _facebook_data(response)[:FACEBOOK_POST_LIMIT]:
            if not isinstance(post,dict):continue
            post_id=post.get('id','');author=post.get('from') or {}
            if not isinstance(post_id,str) or not re.fullmatch(r'\d+(?:_\d+)*',post_id):raise ValueError('Invalid Facebook post identifier')
            # /Page/posts is Page-owned; a supplied conflicting author is still rejected.
            if isinstance(author,dict) and author.get('id') not in {None,page_id}:continue
            if not _recent(post.get('created_time'),window):continue
            rows.extend(_facebook_comments(base,post_id,facebook_permalink_url(post.get('permalink_url')),page_id,token,window))
        return rows
    parent_id=resource.rsplit('/',1)[0]
    parent=request_json(base+parent_id+'?'+urlencode({'fields':'id,from,permalink_url'}),token)
    if not isinstance(parent,dict) or parent.get('error') or parent.get('id')!=parent_id:
        raise ValueError('Facebook returned a different parent post')
    author=parent.get('from') or {};page_id=author.get('id') if isinstance(author,dict) else None
    if not isinstance(page_id,str) or not re.fullmatch(r'\d+',page_id):raise ValueError('Facebook parent Page could not be identified')
    return _facebook_comments(base,parent_id,facebook_permalink_url(parent.get('permalink_url')),page_id,token,window)


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
    window=_collection_window(source)
    if platform=='GOOGLE':
        result=request_json('https://mybusiness.googleapis.com/v4/'+resource+'/reviews?'+urlencode({'pageSize':25,'orderBy':'updateTime desc'}),token)
        rows=[]
        for item in result.get('reviews',[])[:25]:
            updated=_source_datetime(item.get('updateTime'));created=_source_datetime(item.get('createTime'))
            effective=updated or created
            if not item.get('comment') or effective is None or not window[0]<=effective<=window[1]:continue
            row={'id':resource+'/'+item['reviewId'],'text':item['comment']}
            if created:row['source_created_at']=item['createTime']
            if updated:row['source_updated_at']=item['updateTime']
            rows.append(row)
        return rows
    if platform=='FACEBOOK':
        version=get_value('BELIVE_FACEBOOK_VERSION','')
        if not re.fullmatch(r'v\d+\.\d+',version):raise RuntimeError('FACEBOOK_VERSION_REQUIRED')
        return _facebook_source(source,token,version,window)
    if resource.endswith('/threads'):
        result=request_json(THREADS_API+resource+'?'+urlencode({'fields':'id,text,permalink,timestamp','limit':THREADS_POST_LIMIT}),token)
        rows=[]
        for post in _threads_data(result)[:THREADS_POST_LIMIT]:
            post_id=post.get('id')
            if not isinstance(post_id,str) or not re.fullmatch(r'[0-9]+',post_id):
                raise ValueError('Invalid Threads post identifier')
            if not _recent(post.get('timestamp'),window):continue
            replies=request_json(THREADS_API+post_id+'/replies?'+urlencode({'fields':'id,text,permalink,timestamp,is_reply_owned_by_me','limit':THREADS_REPLY_LIMIT}),token)
            rows.extend(_threads_item(item,post_id) for item in _threads_data(replies)[:THREADS_REPLY_LIMIT]
                        if item.get('text') and item.get('is_reply_owned_by_me') is not True
                        and _recent(item.get('timestamp'),window))
        return rows
    result=request_json(THREADS_API+resource+'?'+urlencode({'fields':'id,text,permalink,timestamp,is_reply_owned_by_me','limit':THREADS_REPLY_LIMIT}),token)
    # Older single-post sources retain their IDs and duplicate behaviour.
    return [_threads_item(item)
            for item in _threads_data(result)[:THREADS_REPLY_LIMIT]
            if item.get('text') and item.get('is_reply_owned_by_me') is not True
            and _recent(item.get('timestamp'),window)]

def scan_interval(store,db):
    settings=store.all(db,'source_schedule')
    return settings[0]['minutes'] if settings else 15


def _source_metadata(service,db,case,item):
    evidence={k:item[k] for k in ('public_url','source_created_at','source_updated_at','parent_source_id',
                                'parent_public_url','public_source_kind') if item.get(k)}
    if evidence and any(case.get(k)!=v for k,v in evidence.items()):
        case.update(evidence);case['revision']+=1
        service.store.put(db,'case',case)
        service.store.event(db,case['id'],'API_SOURCE_LINKED','Original API source link and timestamp retained')


def scan(service,source_id):
    from belive.service import due
    with service.store.connect() as db:source=service.store.get(db,'source',source_id)
    if not source['enabled']:raise ValueError('Resume checks for the selected source before scanning')
    try:
        with credential_scope(service.store.path):rows=read_source(source)
        from belive.store import digest,redact
        account_mode=source['platform']=='THREADS' and source['resource'].endswith('/threads')
        facebook_feed=source['platform']=='FACEBOOK' and source['resource'].endswith('/feed')
        deferred_count=0
        with service.lock,service.store.connect() as db:
            cases=service.store.all(db,'case');before_ids={c['id'] for c in cases}
            if source['platform'] in {'FACEBOOK','THREADS'}:
                own_ids={c.get('public_reply',{}).get('receipt_id') for c in cases
                         if (c.get('public_reply',{}).get('platform') or c.get('platform'))==source['platform']
                         and c.get('public_reply',{}).get('status')=='POSTED'}
                own_ids|={a.get('result',{}).get('receipt_id') for a in service.store.all(db,'public_reply_attempt')
                          if a.get('result',{}).get('platform')==source['platform']
                          and a.get('result',{}).get('status')=='POSTED'}
                rows=[item for item in rows if item['id'] not in own_ids]
            by_version={version:case for case in cases for version in case.get('source_versions',[])}
            for item in rows:
                text=item.get('text','')
                if not isinstance(text,str) or not 10<=len(text.strip())<=6000:continue
                known=db.execute('SELECT id FROM sources WHERE platform=? AND source_id=? AND hash=?',
                                 (source['platform'],item['id'],digest(redact(text.strip())))).fetchone()
                if known and known[0] in by_version:
                    _source_metadata(service,db,by_version[known[0]],item)
            seen_count=len(rows)
            if account_mode or facebook_feed:
                # Process unseen immutable versions first; existing replies must not fill the import cap.
                unique={}
                for item in rows:
                    text=item.get('text','')
                    if not isinstance(text,str) or not 10<=len(text.strip())<=6000:continue
                    fingerprint=digest(redact(text.strip()))
                    if not db.execute('SELECT 1 FROM sources WHERE platform=? AND source_id=? AND hash=?',
                                      (source['platform'],item['id'],fingerprint)).fetchone():
                        unique[(item['id'],fingerprint)]=item
                pending=sorted(unique.values(),key=lambda item:(item.get('source_created_at',''),item['id']))
                limit=FACEBOOK_IMPORT_LIMIT if facebook_feed else THREADS_IMPORT_LIMIT
                rows=pending[:limit]
                deferred_count=max(0,len(pending)-len(rows))
        results=[]
        for item in rows:
            p={'title':'Public tenant feedback','description':item['text'],'platform':source['platform'],'source_id':item['id']}
            if len(p['description'].strip())<10:continue
            # Content hash distinguishes immutable edits while duplicate polls reuse results.
            c=service.command('intake',p,'scan-'+digest(json.dumps(p,sort_keys=True)))
            if any(item.get(k) for k in ('public_url','source_created_at','source_updated_at','parent_source_id','parent_public_url','public_source_kind')):
                with service.lock,service.store.connect() as db:
                    current_case=service.store.get(db,'case',c['id'])
                    _source_metadata(service,db,current_case,item)
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
