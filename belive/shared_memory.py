"""Two-way, revision-checked sharing of approved company knowledge only."""
import json
import secrets
import threading
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener
from belive.connectors import NoRedirect
from belive.memory_hub import Hub,serve,FIELDS,fingerprint,clean
from belive.store import now


def connection(service,db):
    c=next(iter(service.store.all(db,'memory_connection')),None)
    if c and c.get('backend')=='repository':c['_service']=service
    return c


def enabled(service,db):return bool(connection(service,db))


def status(service,db):
    c=connection(service,db);state=next(iter(service.store.all(db,'memory_state')),{'status':'NOT_CONNECTED'})
    records=service.store.all(db,'memory_record')
    return {'configured':bool(c),'status':state['status'],'last_sync':state.get('last_sync'),'error':state.get('error',''),
        'backend':c.get('backend','local') if c else None,'repository':c.get('repository') if c else None,
        'repository_backup':next(iter(service.store.all(db,'repository_backup')),{'status':'NOT_SAVED'}),
        'workspace_id':c.get('workspace_id') if c else None,'url':c.get('url') if c else '',
        'role':c.get('role') if c else None,'counts':{k:sum(r['kind']==k for r in records) for k in FIELDS},
        'conflicts':[{k:x[k] for k in ('id','key','kind','local_value','remote_value','remote_revision','at')} for x in service.store.all(db,'memory_conflict') if x.get('status')=='OPEN'],
        'records':[{k:x[k] for k in ('key','kind','value','revision','updated_at','actor')} for x in records],
        'pending':state.get('pending',0),'sequence':state.get('sequence',0),'peers':state.get('peers',[])}


def fresh(service,db):
    if not enabled(service,db):return True
    if connection(service,db).get('backend')=='repository':return True
    state=next(iter(service.store.all(db,'memory_state')),{})
    if state.get('status')!='ONLINE' or not state.get('last_sync'):return False
    return (datetime.now(timezone.utc)-datetime.fromisoformat(state['last_sync'])).total_seconds()<90


def records(service,db,kind):
    if not fresh(service,db):return []
    return [x['value'] for x in service.store.all(db,'memory_record') if x['kind']==kind]


def knowledge(service,db):return records(service,db,'sop') if enabled(service,db) else service.store.all(db,'wa_knowledge')


def documents(service,db):return records(service,db,'document') if enabled(service,db) else service.store.all(db,'sop_document')


def experiences(service,db):
    return [{**x,'id':'SHARED-'+x['id'],'case_id':None,'provenance':'Shared approved experience'+(' · SAMPLE / TEST' if x.get('sample_data') else '')} for x in records(service,db,'experience') if x.get('enabled')]


def tips(service,db):
    return [{**x,'id':'SHARED-'+x['id'],'case_id':None,'status':'APPROVED','approved':True,'revision':1} for x in records(service,db,'tip') if x.get('enabled')]


def validate_url(value):
    p=urlsplit(value)
    if p.username or p.password or p.query or p.fragment or p.path not in {'','/'}:raise ValueError('Use the private memory service base URL')
    if not p.hostname or (p.scheme!='https' and not(p.scheme=='http' and p.hostname in {'127.0.0.1','localhost'})):raise ValueError('Use HTTPS; plain HTTP is allowed only on this computer')
    if p.scheme=='https' and not p.hostname.lower().endswith('.ts.net'):raise ValueError('Use the private Tailscale HTTPS address, not a public website')
    return value.rstrip('/')


def request(c,p=None):
    if c.get('backend')=='repository':
        from belive.repository_memory import request as repository_request
        return repository_request(c['_service'],p)
    url=validate_url(c['url'])+'/v1/knowledge';body=None if p is None else json.dumps(p).encode()
    req=Request(url,data=body,headers={'Authorization':'Bearer '+c['token'],'Content-Type':'application/json'})
    try:
        with build_opener(NoRedirect).open(req,timeout=8) as response:
            raw=response.read(12_000_001)
            if len(raw)>12_000_000:raise ValueError('Shared knowledge response too large')
            result=json.loads(raw)
    except HTTPError as exc:
        with exc:
            if exc.code==409:return json.loads(exc.read(200001))
        raise ValueError('Shared memory access was rejected; check the pairing configuration') from None
    if p is None and result.get('workspace_id')!=c['workspace_id']:raise ValueError('Wrong shared knowledge workspace; nothing was merged')
    if p is None and result.get('schema_version')!=1:raise ValueError('Update both BeLive installations to the same shared-memory version')
    return result


def sync_documents(service,c,snapshot):
    import hashlib
    available=set(snapshot.get('available_documents',[]));directory=service.store.path.parent/'company_documents'
    for item in snapshot['records']:
        if item['kind']!='document':continue
        sha=item['value']['sha256'];path=directory/(sha+'.pdf');body=path.read_bytes() if path.is_file() else None
        if body and hashlib.sha256(body).hexdigest()!=sha:raise ValueError('Local source checksum mismatch')
        if body and sha in available:continue
        if not body and sha not in available:continue
        req=Request(validate_url(c['url'])+'/v1/document/'+sha,data=body,headers={'Authorization':'Bearer '+c['token'],'Content-Type':'application/pdf'})
        with build_opener(NoRedirect).open(req,timeout=15) as response:data=response.read(20*1024*1024+1)
        if body is None:
            if len(data)>20*1024*1024 or not data.startswith(b'%PDF-') or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Shared source checksum mismatch')
            directory.mkdir(exist_ok=True);path.write_bytes(data)


def exports(service,db):
    result={}
    for kind,store_kind in [('sop','wa_knowledge'),('document','sop_document')]:
        for x in service.store.all(db,store_kind):
            value={k:v for k,v in x.items() if k in FIELDS[kind]}
            result[kind+':'+x['id']]=(kind,clean(kind,value))
    # Only deliberately approved general reuse text, never source conversations or case details.
    cases={x['id']:x for x in service.store.all(db,'case')};latest={}
    for x in reversed(service.store.all(db,'feedback')):latest[x['case_id']]=x
    for x in service.store.all(db,'feedback'):
        key='experience:'+x['id'];c=cases.get(x['case_id'],{})
        active=bool(latest.get(x['case_id'],{}).get('id')==x['id'] and x.get('public_question') and x.get('verdict')=='CORRECTED' and c.get('status')=='CLOSED' and c.get('closure_reason')!='CUSTOMER_INACTIVE')
        bound=any(b['id']==key for b in service.store.all(db,'memory_binding'))
        if not active and not bound:continue
        from belive.relevance import sample_case
        value={'id':x['id'],'question':x.get('public_question',''),'answer':x.get('text','') if active else '',
            'category':c.get('category','OTHER'),'sample_data':sample_case(c),'enabled':active,'provenance':'Staff-approved general complaint experience'}
        result[key]=('experience',value)
    for x in service.store.all(db,'reply_learning'):
        if x.get('scope_condo') is not None:continue
        key='tip:'+x['id'];active=bool(x.get('approved') and x['status']=='APPROVED')
        bound=any(b['id']==key for b in service.store.all(db,'memory_binding'))
        if not active and not bound:continue
        from belive.relevance import domains
        topics=sorted(domains(x['question']))
        labels={'wifi':'Wi-Fi connectivity','air_conditioning':'Air conditioning','refrigerator':'Refrigerator','water_pressure':'Water pressure','parcel':'Parcel delivery','washer':'Washing machine','cleaning':'Cleaning','access':'Access and keys','billing':'Billing','rules':'House rules','tracking':'Complaint tracking'}
        question=', '.join(labels[t] for t in topics)+' support communication' if topics else 'General support communication'
        value={'id':x['id'],'question':question,'tip':x['tip'] if active else '', 'category':x['category'],
            'sample_data':x.get('sample_data',False),'scope_condo':None,'enabled':active,'approved':active,'status':'APPROVED' if active else 'REJECTED'}
        result[key]=('tip',value)
    return result


def local_stamp(service,db,key,kind,value):
    if kind in {'experience','tip'}:
        name='feedback' if kind=='experience' else 'reply_learning'
        source=next((x for x in service.store.all(db,name) if x['id']==value['id']),None)
        return fingerprint({'source':source,'value':value}) if source else None
    return fingerprint(value)


def materialize(service,db,item):
    kind=item['kind'];value=item['value'];key=item['key']
    service.store.put(db,'memory_record',{'id':key,**item})
    if kind in {'sop','document'}:
        store_kind='wa_knowledge' if kind=='sop' else 'sop_document'
        old=next((x for x in service.store.all(db,store_kind) if x['id']==value['id']),{})
        merged={**old,**value,'_memory_key':key}
        if kind=='sop':merged.setdefault('property_ref','');merged.setdefault('reviewed_by','Shared company knowledge');merged.setdefault('at',now())
        service.store.put(db,store_kind,merged)
    # Only update the baseline of the knowledge that this machine owns or materialises.
    service.store.put(db,'memory_binding',{'id':key,'revision':item['revision'],'hash':fingerprint(value)})


def sync(service):
    if not hasattr(service,'memory_lock'):service.memory_lock=threading.RLock()
    with service.memory_lock:
        with service.lock,service.store.connect() as db:
            c=connection(service,db)
            if not c:return {'status':'NOT_CONNECTED'}
            if c.get('backend')=='repository':
                from belive.repository_memory import sync as repository_sync
                return repository_sync(service)
            local=exports(service,db);bindings={x['id']:x for x in service.store.all(db,'memory_binding')}
            stamps={k:local_stamp(service,db,k,kind,value) for k,(kind,value) in local.items()}
            conflicts={x['key']:x for x in service.store.all(db,'memory_conflict') if x.get('status')=='OPEN'}
        try:
            # Verify the workspace before publishing even a single company rule.
            snapshot=request(c)
            for key,(kind,value) in local.items():
                binding=bindings.get(key)
                if binding and (binding.get('local_stamp')==stamps[key] if 'local_stamp' in binding else binding['hash']==fingerprint(value)):continue
                if key in conflicts:continue
                answer=request(c,{'kind':kind,'value':value,'expected_revision':binding['revision'] if binding else 0})
                if answer.get('error')=='SHARED_CONFLICT':
                    with service.lock,service.store.connect() as db:
                        service.store.put(db,'memory_conflict',{'id':key,'key':key,'kind':kind,'local_value':value,'remote_value':answer['current_value'],'remote_revision':answer['current_revision'],'status':'OPEN','at':now()})
                        service.store.event(db,key,'SHARED_MEMORY_CONFLICT','Local proposal preserved; common published version retained')
            snapshot=request(c)
            sync_documents(service,c,snapshot)
            with service.lock,service.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for late in snapshot.get('_conflicts',[]):
                    service.store.put(db,'memory_conflict',{'id':late['key'],**late,'status':'OPEN','at':now()})
                # Prevent a simultaneous local edit from being overwritten by a network snapshot.
                current=exports(service,db);pending=0;updated_keys=set()
                for item in snapshot['records']:
                    clean(item['kind'],item['value'])
                    if item['key']!=item['kind']+':'+item['value']['id']:raise ValueError('Invalid shared record')
                    key=item['key']
                    conflict=next((x for x in service.store.all(db,'memory_conflict') if x['key']==key and x.get('status')=='OPEN'),None)
                    if conflict:
                        conflict.update(remote_value=item['value'],remote_revision=item['revision']);service.store.put(db,'memory_conflict',conflict)
                    if key in current and (key not in local or local_stamp(service,db,key,*current[key])!=stamps.get(key)):
                        pending+=1;continue
                    materialize(service,db,item)
                    updated_keys.add(key)
                after=exports(service,db)
                for item in snapshot['records']:
                    key=item['key'];binding=next((x for x in service.store.all(db,'memory_binding') if x['id']==key),None)
                    if key not in updated_keys:continue
                    if not binding or binding['revision']!=item['revision']:continue
                    binding['local_stamp']=local_stamp(service,db,key,*after[key]) if key in after else None
                    service.store.put(db,'memory_binding',binding)
                state={'id':'shared','status':'PENDING' if pending else 'ONLINE','last_sync':now(),'sequence':snapshot['sequence'],'pending':pending,'error':'','peers':snapshot.get('peers',[])}
                service.store.put(db,'memory_state',state)
            return {'status':state['status'],'sequence':snapshot['sequence'],'records':len(snapshot['records'])}
        except Exception:
            with service.lock,service.store.connect() as db:
                old=next(iter(service.store.all(db,'memory_state')),{'id':'shared'})
                old.update(status='OFFLINE',error='Cannot reach the shared knowledge service. Shared rules are paused rather than using stale knowledge.')
                service.store.put(db,'memory_state',old)
            return {'status':'OFFLINE'}


def configure(service,p):
    url=validate_url(str(p.get('url','')));token=p.get('token','');wid=p.get('workspace_id','')
    if not isinstance(token,str) or len(token)<32 or not re_workspace(wid):raise ValueError('Use the complete private pairing configuration')
    candidate={'id':'shared','url':url,'token':token,'workspace_id':wid,'role':p.get('role','peer')}
    request(candidate)
    with service.lock,service.store.connect() as db:
        old=connection(service,db)
        if old and old['workspace_id']!=wid:raise ValueError('This computer is paired to another workspace; review its pending knowledge before switching')
        service.store.put(db,'memory_connection',candidate)
    return sync(service)


def re_workspace(value):
    import re
    return isinstance(value,str) and bool(re.fullmatch(r'MEM-[a-f0-9]{24}',value))


def hub_config_path(service):return service.store.path.parent/'shared_memory'/'hub-config.json'


def start_host(service):
    with service.store.connect() as db:
        c=connection(service,db)
        if c and c.get('backend')=='repository':return
    if getattr(service,'memory_hub',None):return
    path=hub_config_path(service)
    if not path.is_file():return
    c=json.loads(path.read_text(encoding='utf-8'))
    hub=Hub(path.with_name('knowledge.db'),c['workspace_id'],{c['host_token']:'Host',c['peer_token']:'Peer'})
    service.memory_hub=serve(hub,c['port'])


def setup_host(service):
    with service.memory_lock:return _setup_host(service)


def _setup_host(service):
    with service.store.connect() as db:
        old=connection(service,db)
        if old and old.get('role')!='host':raise ValueError('This computer is already paired as a peer; use the existing common workspace')
    path=hub_config_path(service)
    if not path.is_file():
        path.parent.mkdir(parents=True,exist_ok=True)
        c={'workspace_id':'MEM-'+secrets.token_hex(12),'host_token':secrets.token_urlsafe(36),'peer_token':secrets.token_urlsafe(36),'port':8878}
        path.write_text(json.dumps(c),encoding='utf-8')
    c=json.loads(path.read_text(encoding='utf-8'));start_host(service)
    return configure(service,{'url':'http://127.0.0.1:'+str(c['port']),'token':c['host_token'],'workspace_id':c['workspace_id'],'role':'host'})


def pairing(service,url):
    url=validate_url(url)
    if not url.startswith('https://'):raise ValueError('The peer must use the private HTTPS address')
    c=json.loads(hub_config_path(service).read_text(encoding='utf-8'))
    return {'url':url,'token':c['peer_token'],'workspace_id':c['workspace_id'],'role':'peer'}


def resolve(service,p):
    with service.lock,service.store.connect() as db:
        item=service.store.get(db,'memory_conflict',p.get('id'));c=connection(service,db)
        if item['status']!='OPEN':raise ValueError('This conflict is already resolved')
    if p.get('choice')=='local':
        if p.get('confirmed') is not True:raise ValueError('Review this local proposal before publishing it over the common version')
        if item['remote_revision']!=p.get('remote_revision'):raise ValueError('The common version changed since you reviewed it; compare the updated conflict first')
        result=request(c,{'kind':item['kind'],'value':item['local_value'],'expected_revision':item['remote_revision']})
        if result.get('error'):raise ValueError('Common knowledge changed again; sync and review the latest version')
    elif p.get('choice')!='remote':raise ValueError('Choose the common version or the reviewed local proposal')
    with service.lock,service.store.connect() as db:
        item.update(status='RESOLVED',resolution=p['choice']);service.store.put(db,'memory_conflict',item)
    return sync(service)


def change(service,p):
    if p.get('confirmed') is not True:raise ValueError('Review this change before publishing it to both computers')
    with service.store.connect() as db:
        item=service.store.get(db,'memory_record',p.get('key'));c=connection(service,db)
    if item['revision']!=p.get('revision'):raise ValueError('Common knowledge changed; sync and review the latest version')
    value=dict(item['value'])
    if type(p.get('enabled')) is not bool:raise ValueError('Specify whether this shared lesson is enabled')
    if item['kind'] not in {'tip','experience'}:raise ValueError('Manage SOP and documents in the SOP panel')
    value['enabled']=p['enabled']
    if item['kind']=='tip':value.update(approved=p['enabled'],status='APPROVED' if p['enabled'] else 'REJECTED')
    answer=request(c,{'kind':item['kind'],'value':value,'expected_revision':item['revision']})
    if answer.get('error'):raise ValueError('Common knowledge changed; sync before editing')
    return sync(service)


def tailscale_binary():
    import shutil,os
    binary=shutil.which('tailscale')
    candidate=Path(os.getenv('ProgramFiles','C:/Program Files'))/'Tailscale'/'tailscale.exe'
    return binary or (str(candidate) if candidate.is_file() else None)


def network_status():
    import subprocess
    binary=tailscale_binary()
    if not binary:return {'installed':False,'logged_in':False,'message':'Install Tailscale on both computers, then sign in with each person own authorised account.'}
    try:
        result=subprocess.run([binary,'status','--json'],capture_output=True,text=True,timeout=8)
        info=json.loads(result.stdout);running=info.get('BackendState')=='Running';dns=info.get('Self',{}).get('DNSName','').rstrip('.')
        return {'installed':True,'logged_in':running,'url':'https://'+dns if running and dns else '',
            'message':'Private network connected. Authorise the friend on this private network before sharing the pairing file.' if running else 'Tailscale is installed. Open it from the Windows tray and sign in, then check again.'}
    except Exception:return {'installed':True,'logged_in':False,'message':'Open Tailscale, finish signing in, then check the private connection again.'}


def enable_private_service(service):
    import subprocess
    state=network_status()
    if not state.get('logged_in'):return state
    start_host(service)
    if not getattr(service,'memory_hub',None):raise ValueError('Create the memory host first')
    config=json.loads(hub_config_path(service).read_text(encoding='utf-8'))
    result=subprocess.run([tailscale_binary(),'serve','--bg','--https=443','http://127.0.0.1:'+str(config['port'])],capture_output=True,text=True,timeout=15)
    if result.returncode:state['message']='Finish enabling HTTPS for Serve in Tailscale, then retry. This service must remain private to your authorised network.'
    else:state['message']='Private HTTPS memory service enabled. Give the pairing file only to the authorised friend; this computer and BeLive must stay running.'
    return state
