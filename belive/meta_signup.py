"""Bounded, operator-authorised Meta Embedded Signup. No dashboard is public."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from belive.connectors import request_json
from belive.store import digest

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'data'/'whatsapp-https.json'
CREDENTIALS=ROOT/'data'/'whatsapp-credentials.json'

def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def private_write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8');temp.replace(path)

def config():
    values={}
    env=ROOT/'.env'
    if env.is_file():
        for line in env.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"').strip("'")
    return {key:os.getenv('BELIVE_WHATSAPP_'+key.upper(),'').strip() or values.get('BELIVE_WHATSAPP_'+key.upper(),'')
            for key in ('app_id','config_id','app_secret','graph_version')}

def origin():
    value=read_json(RUNTIME).get('origin','');url=urlsplit(value)
    if url.scheme!='https' or not url.hostname or url.netloc!=url.hostname or url.path or url.query or url.fragment:
        raise ValueError('HTTPS authorisation address is not ready')
    return value

def status():
    c=config()
    try:base=origin()
    except ValueError:base=''
    return {'origin':base,'signup_url':base+'/connect/whatsapp' if base else '',
            'webhook_url':base+'/webhooks/whatsapp' if base else '',
            'app_id':c['app_id'],'config_id':c['config_id'],
            'app_secret_present':bool(c['app_secret']),
            'graph_version':c['graph_version'],'temporary':True}

def new_link(service):
    base=origin();ticket=secrets.token_urlsafe(32)
    with service.store.connect() as db:
        # Starting another setup invalidates earlier unfinished grants.
        for row in service.store.all(db,'meta_signup'):
            if row.get('status')!='COMPLETE':
                row.update(status='EXPIRED',business_token='');service.store.put(db,'meta_signup',row)
        service.store.put(db,'meta_signup',{'id':digest(ticket),'status':'ISSUED','expires':time.time()+1800})
    return {'url':base+'/connect/whatsapp#'+ticket,'expires_in':1800}

def consume_ticket(service,ticket):
    if not isinstance(ticket,str) or not 30<=len(ticket)<=100:raise ValueError('Open a fresh connection link from the local BeLive dashboard')
    cookie=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=service.store.get(db,'meta_signup',digest(ticket))
        if row['status']!='ISSUED' or row['expires']<time.time():raise ValueError('Connection link expired or already used; create a new link in BeLive')
        row.update(status='OPEN',session_hash=digest(cookie),csrf=csrf);service.store.put(db,'meta_signup',row)
    return cookie,csrf

def session(service,cookie,csrf=None):
    with service.store.connect() as db:rows=service.store.all(db,'meta_signup')
    row=next((r for r in rows if r.get('session_hash')==digest(cookie)),None)
    if not cookie or not row or row['expires']<time.time() or row['status']=='EXPIRED':raise ValueError('Connection session expired; return to local BeLive')
    if csrf is not None and not hmac.compare_digest(row['csrf'],str(csrf)):raise ValueError('Invalid connection session')
    return row

def graph(path,token='',payload=None,params=None):
    c=config();version=c['graph_version']
    if not re.fullmatch(r'v\d+\.\d+',version):raise ValueError('Set the Meta Graph API version locally')
    return request_json('https://graph.facebook.com/'+version+'/'+path+('?' + urlencode(params) if params else ''),token,payload)

def exchange(service,row,code):
    c=config()
    if not c['app_secret']:raise ValueError('App Secret is missing in the local .env; do not paste it here')
    if not isinstance(code,str) or not 10<=len(code)<=12000:raise ValueError('Meta did not return a valid authorisation code')
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE');current=service.store.get(db,'meta_signup',row['id'])
        if current['status']!='OPEN':raise ValueError('Authorisation code was already submitted')
        current.update(status='EXCHANGING');service.store.put(db,'meta_signup',current)
    try:
        result=graph('oauth/access_token',params={'client_id':c['app_id'],'client_secret':c['app_secret'],'code':code})
        token=result.get('access_token')
        if not isinstance(token,str) or not token:raise ValueError('Meta did not issue an access token')
        details=graph('debug_token',token=c['app_id']+'|'+c['app_secret'],params={'input_token':token}).get('data',{})
        if not details.get('is_valid') or str(details.get('app_id'))!=c['app_id']:raise ValueError('Meta token does not belong to this app')
        required={'whatsapp_business_management','whatsapp_business_messaging'}
        if not required.issubset(details.get('scopes',[])):raise ValueError('Meta did not grant both WhatsApp permissions')
        with service.store.connect() as db:
            current=service.store.get(db,'meta_signup',row['id']);current.update(status='TOKEN_READY',business_token=token);service.store.put(db,'meta_signup',current)
        return {'code_exchanged':True}
    except Exception:
        with service.store.connect() as db:
            current=service.store.get(db,'meta_signup',row['id']);current.update(status='FAILED',business_token='');service.store.put(db,'meta_signup',current)
        raise

def complete(service,row,waba_id,phone_id=''):
    from belive.whatsapp_channel import settings,phone
    if not re.fullmatch(r'\d{5,30}',str(waba_id)):raise ValueError('Meta has not returned the WhatsApp account ID yet')
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=service.store.get(db,'meta_signup',row['id'])
        if row['status']!='TOKEN_READY':raise ValueError('Wait for Meta authorisation to finish')
        row.update(status='VERIFYING');service.store.put(db,'meta_signup',row);approved=settings(service,db)['public_number']
    token=row['business_token']
    try:
        numbers=graph(waba_id+'/phone_numbers',token,params={'fields':'id,display_phone_number,is_on_biz_app,platform_type'}).get('data',[])
        match=next((x for x in numbers if phone(x.get('display_phone_number',''))==approved and (not phone_id or x['id']==phone_id)),None)
        if not approved or not match:raise ValueError('Selected number does not match the company support number')
        if match.get('is_on_biz_app') is not True or match.get('platform_type')!='CLOUD_API':raise ValueError('Keep the phone Business app: complete existing-Business-app onboarding, not ordinary number registration')
        phone_id=match['id'];c=config();runtime=read_json(RUNTIME)
        # Never register/unregister a phone or replace the app-wide webhook.
        subscriptions=graph(waba_id+'/subscribed_apps',token).get('data',[])
        if not any(str(x.get('whatsapp_business_api_data',{}).get('id'))==c['app_id'] for x in subscriptions):
            subscribed=graph(waba_id+'/subscribed_apps',token,payload={})
            if not subscribed.get('success'):raise ValueError('Meta could not subscribe the WhatsApp account')
        callback={'override_callback_uri':origin()+'/webhooks/whatsapp','verify_token':runtime['verify_token']}
        # Persist after ownership verification, before Meta's synchronous callback check.
        previous=read_json(CREDENTIALS)
        private_write(CREDENTIALS,{'access_token':token,'phone_number_id':phone_id,'graph_version':c['graph_version'],'waba_id':waba_id})
        try:
            result=graph(phone_id,token,payload={'webhook_configuration':callback})
            if not result.get('success'):raise ValueError('Meta webhook setup failed')
        except Exception:
            private_write(CREDENTIALS,previous);raise
        with service.store.connect() as db:
            row.update(status='COMPLETE',business_token='',phone_number_id=phone_id,waba_id=waba_id);service.store.put(db,'meta_signup',row)
        return {'authorised':True,'phone_number_id':phone_id,'delivery_verified':False,'next':'Send a new customer message to the company number to verify Hermes delivery.'}
    except Exception:
        with service.store.connect() as db:
            row.update(status='TOKEN_READY');service.store.put(db,'meta_signup',row)
        raise
