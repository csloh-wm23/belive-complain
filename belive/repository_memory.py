"""Private authenticated-encrypted reviewed-knowledge export and restore."""
import base64,hashlib,json,os,secrets,sys,threading
from pathlib import Path
from belive.memory_hub import clean,fingerprint
from belive.store import now

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'knowledge'/'team-memory.enc.json'
AAD=b'BeLive approved knowledge backup v1'


def crypto():
    try:from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        sys.path.insert(0,str(ROOT/'output'/'knowledge-runtime'))
        try:from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:raise ValueError('Install the knowledge-backup dependency: python scripts/knowledge_backup.py runtime') from None
    return AESGCM


def key_path(service):return service.store.path.parent/'knowledge-backup.key'


def read_key(service,create=False):
    path=key_path(service)
    if not path.exists():
        if not create:raise ValueError('Import the team recovery-key file to restore the encrypted SOP and learning backup.')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='ascii') as f:f.write(base64.b64encode(secrets.token_bytes(32)).decode()+'\n')
    try:key=base64.b64decode(path.read_text().strip(),validate=True)
    except Exception:raise ValueError('Invalid team recovery-key file') from None
    if len(key)!=32:raise ValueError('Invalid team recovery-key file')
    return key


def pack(data,key):
    plain=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode();nonce=secrets.token_bytes(12)
    return {'schema_version':1,'algorithm':'AES-256-GCM','key_id':hashlib.sha256(key).hexdigest()[:16],
        'content_hash':hashlib.sha256(plain).hexdigest(),'nonce':base64.b64encode(nonce).decode(),
        'ciphertext':base64.b64encode(crypto()(key).encrypt(nonce,plain,AAD)).decode()}


def unpack(envelope,key):
    if envelope.get('schema_version')!=1 or envelope.get('algorithm')!='AES-256-GCM':raise ValueError('Unsupported knowledge backup format')
    try:
        raw=crypto()(key).decrypt(base64.b64decode(envelope['nonce'],validate=True),base64.b64decode(envelope['ciphertext'],validate=True),AAD)
        if len(raw)>40_000_000 or hashlib.sha256(raw).hexdigest()!=envelope['content_hash']:raise ValueError()
        data=json.loads(raw)
        from belive.shared_memory import re_workspace
        if data.get('schema_version')!=1 or not re_workspace(data.get('workspace_id')):raise ValueError()
        keys=set()
        for item in data['records']:
            clean(item['kind'],item['value']);key=item['kind']+':'+item['value']['id']
            if item['key']!=key or key in keys or type(item['revision']) is not int or item['revision']<1:raise ValueError()
            keys.add(key)
        documents={x['value']['sha256'] for x in data['records'] if x['kind']=='document'}
        for sha,body in data['documents'].items():
            decoded=base64.b64decode(body,validate=True)
            if sha not in documents or len(decoded)>20*1024*1024 or hashlib.sha256(decoded).hexdigest()!=sha:raise ValueError()
        return data
    except Exception:raise ValueError('The recovery key does not match, or the knowledge backup is damaged. Existing data was not replaced.') from None


def configure(service):
    from belive import shared_memory as sm
    with service.lock,service.store.connect() as db:
        old=sm.connection(service,db)
        c={'id':'shared','backend':'repository','workspace_id':old['workspace_id'] if old else 'MEM-'+secrets.token_hex(12),'role':'repository','url':''}
        service.store.put(db,'memory_connection',c)
    if getattr(service,'memory_hub',None):service.memory_hub.shutdown();service.memory_hub.server_close();service.memory_hub=None
    return sync(service)


def bind(service,db,item):
    from belive import shared_memory as sm
    sm.materialize(service,db,item)
    source=sm.exports(service,db).get(item['key'])
    binding=service.store.get(db,'memory_binding',item['key'])
    binding['local_stamp']=sm.local_stamp(service,db,item['key'],*source) if source else None
    service.store.put(db,'memory_binding',binding)


def sync(service):
    from belive import shared_memory as sm
    with service.memory_lock,service.lock,service.store.connect() as db:
        local=sm.exports(service,db);bindings={x['id']:x for x in service.store.all(db,'memory_binding')}
        conflict_keys={x['key'] for x in service.store.all(db,'memory_conflict') if x.get('status')=='OPEN'}
        cache={x['key']:x for x in service.store.all(db,'memory_record')}
        for key,(kind,value) in local.items():
            binding=bindings.get(key);old=cache.get(key)
            if key in conflict_keys:continue
            stamp=sm.local_stamp(service,db,key,kind,value)
            if binding and (binding.get('local_stamp')==stamp if 'local_stamp' in binding else binding['hash']==fingerprint(value)):continue
            if old and fingerprint(old['value'])==fingerprint(value):bind(service,db,old);continue
            item={'key':key,'kind':kind,'value':value,'revision':old['revision']+1 if old else 1,'updated_at':now(),'actor':'Local reviewed knowledge'}
            bind(service,db,item)
        service.store.put(db,'memory_state',{'id':'shared','status':'ONLINE','last_sync':now(),'sequence':sum(x['revision'] for x in service.store.all(db,'memory_record')),'error':'','pending':0,'peers':[]})
    return {'status':'ONLINE'}


def request(service,p=None):
    if p is None:
        sync(service)
        with service.store.connect() as db:return {'records':service.store.all(db,'memory_record')}
    with service.memory_lock,service.lock,service.store.connect() as db:
        value=clean(p['kind'],p['value']);key=p['kind']+':'+value['id'];old=next((x for x in service.store.all(db,'memory_record') if x['key']==key),None);revision=old['revision'] if old else 0
        if p.get('expected_revision')!=revision:return {'error':'SHARED_CONFLICT','key':key,'current_revision':revision,'current_value':old['value'] if old else None}
        bind(service,db,{'key':key,'kind':p['kind'],'value':value,'revision':revision+1,'updated_at':now(),'actor':'Reviewed repository knowledge'})
        return {'key':key,'revision':revision+1}


def payload(service):
    from belive import shared_memory as sm
    with service.store.connect() as db:
        c=sm.connection(service,db);records=[{k:x[k] for k in ('key','kind','value','revision','updated_at','actor')} for x in service.store.all(db,'memory_record')]
        if any(x.get('status')=='OPEN' for x in service.store.all(db,'memory_conflict')):raise ValueError('Review knowledge conflicts before exporting a private backup')
    documents={}
    for item in records:
        if item['kind']!='document':continue
        sha=item['value']['sha256'];path=service.store.path.parent/'company_documents'/(sha+'.pdf')
        if not path.is_file():raise ValueError('A referenced source PDF is missing; backup was not marked complete')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Company source checksum mismatch')
        documents[sha]=base64.b64encode(raw).decode()
    return {'schema_version':1,'workspace_id':c['workspace_id'],'records':sorted(records,key=lambda x:x['key']),'documents':documents}


def export(service,path=None):
    path=Path(path or ARCHIVE)
    # Never replace an incoming package with unrelated local data before restoring it.
    if path.is_file():startup(service,path)
    configure(service);key=read_key(service,create=not path.is_file());data=payload(service)
    if path.is_file():
        old=json.loads(path.read_text(encoding='utf-8'))
        if unpack(old,key)==data:return {'changed':False,'records':len(data['records']),'documents':len(data['documents'])}
    envelope=pack(data,key);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(envelope,indent=2)+'\n',encoding='utf-8');temporary.replace(path)
    with service.store.connect() as db:
        for item in data['records']:service.store.put(db,'repository_base',{'id':item['key'],'hash':fingerprint(item['value'])})
        service.store.put(db,'repository_backup',{'id':'repository','status':'READY','content_hash':envelope['content_hash'],'at':now(),'records':len(data['records']),'documents':len(data['documents'])})
    return {'changed':True,'records':len(data['records']),'documents':len(data['documents'])}


def restore(service,path=None,key=None):
    from belive import shared_memory as sm
    path=Path(path or ARCHIVE);data=unpack(json.loads(path.read_text(encoding='utf-8')),key or read_key(service))
    with service.memory_lock:
        # Materialise current edits before comparing with the incoming repository revision.
        with service.store.connect() as db:
            old=sm.connection(service,db)
            if old and old['workspace_id']!=data['workspace_id']:raise ValueError('The backup belongs to another workspace. Existing knowledge was preserved.')
            service.store.put(db,'memory_connection',{'id':'shared','backend':'repository','workspace_id':data['workspace_id'],'role':'repository','url':''})
        sync(service)
        with service.lock,service.store.connect() as db:
            existing={x['key']:x for x in service.store.all(db,'memory_record')};bases={x['id']:x['hash'] for x in service.store.all(db,'repository_base')}
            for item in data['records']:
                key=item['key'];previous=existing.get(key);different=previous and fingerprint(previous['value'])!=fingerprint(item['value'])
                if different and bases.get(key)!=fingerprint(previous['value']):
                    service.store.put(db,'memory_conflict',{'id':key,'key':key,'kind':item['kind'],'local_value':previous['value'],'remote_value':item['value'],'remote_revision':item['revision'],'status':'OPEN','at':now()})
                bind(service,db,item)
                service.store.put(db,'repository_base',{'id':key,'hash':fingerprint(item['value'])})
            directory=service.store.path.parent/'company_documents';directory.mkdir(exist_ok=True)
            for sha,body in data['documents'].items():
                target=directory/(sha+'.pdf');raw=base64.b64decode(body)
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=sha:raise ValueError('An existing company document is damaged; restore preserved it for review')
                if not target.exists():target.write_bytes(raw)
            envelope=json.loads(path.read_text(encoding='utf-8'))
            service.store.put(db,'repository_backup',{'id':'repository','status':'RESTORED','content_hash':envelope['content_hash'],'at':now(),'records':len(data['records']),'documents':len(data['documents'])})
        sync(service)
    return {'records':len(data['records']),'documents':len(data['documents'])}


def startup(service,path=None):
    path=Path(path or ARCHIVE)
    if not path.is_file():return
    try:
        envelope=json.loads(path.read_text(encoding='utf-8'))
        with service.store.connect() as db:old=next(iter(service.store.all(db,'repository_backup')),None)
        if old and old.get('content_hash')==envelope['content_hash']:return
        restore(service,path)
    except Exception as exc:
        with service.store.connect() as db:service.store.put(db,'repository_backup',{'id':'repository','status':'RESTORE_REQUIRED','message':str(exc)[:300]})


def import_key(service,value):
    if not ARCHIVE.is_file():raise ValueError('Copy the private encrypted backup to knowledge/team-memory.enc.json before importing its matching recovery key. Existing knowledge was preserved.')
    try:key=base64.b64decode(value.strip(),validate=True)
    except Exception:raise ValueError('Choose the original team recovery-key file') from None
    if len(key)!=32:raise ValueError('Choose the original team recovery-key file')
    # Verify before changing either the local key or knowledge.
    unpack(json.loads(ARCHIVE.read_text(encoding='utf-8')),key)
    result=restore(service,key=key);key_path(service).write_text(base64.b64encode(key).decode()+'\n',encoding='ascii');return result
