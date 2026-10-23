"""Consistent SQLite backups and recovery into a separate, paused workspace."""
import json
import hashlib
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from belive.store import Store,now,digest
from belive.workspace import validate_database_path,save_selection

def checksum(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):h.update(block)
    return h.hexdigest()

def copy_database(source,target):
    target=Path(target);target.touch(exist_ok=False)
    try:
        with closing(sqlite3.connect(Path(source).as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed')
        validate_database_path(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise

def operation(service,action,p,key):
    if not isinstance(key,str) or not 8<=len(key)<=150:raise ValueError('A request idempotency key is required')
    fingerprint=digest(json.dumps([action,p],sort_keys=True))
    with service.lock:
        with service.store.connect() as db:
            old=db.execute('SELECT result FROM requests WHERE key=?',(key,)).fetchone()
            if old:
                saved=json.loads(old[0])
                if saved['fingerprint']!=fingerprint:raise ValueError('Idempotency mismatch')
                return saved['result']
        active=service.store.path.resolve()
        folder=active.parent/('backups' if action=='backup' else 'recovered');folder.mkdir(exist_ok=True)
        destination=folder/(action+'-'+secrets.token_hex(10)+'.db')
        if action=='backup':
            copy_database(active,destination)
            result={'id':'BACKUP-'+secrets.token_hex(8),'path':str(destination),'sha256':checksum(destination),'bytes':destination.stat().st_size,'at':now(),'source':str(active)}
        elif action=='restore':
            if service.workspace_config is None:raise ValueError('Recovery requires database selection support')
            if p.get('confirmed') is not True:raise ValueError('Confirm recovery into a separate paused workspace')
            with service.store.connect() as db:backup=service.store.get(db,'backup',p.get('id'))
            source=Path(backup['path']).resolve()
            if source.parent!=active.parent/'backups' or checksum(source)!=backup['sha256']:raise ValueError('Backup integrity could not be confirmed')
            copy_database(source,destination)
            recovered=Store(destination)
            with recovered.connect() as db:
                # A recovered snapshot must never replay old messages, schedules or access keys.
                db.execute("DELETE FROM objects WHERE kind IN ('auth_session','portal','login_attempt')")
                for item in recovered.all(db,'source'):
                    item['enabled']=False;recovered.put(db,'source',item)
                for item in recovered.all(db,'outbox'):
                    if item['status']!='DELIVERED' and item['status']!='REJECTED':
                        item.update(status='RECOVERY_HOLD',outcome='Recovered snapshot: reconcile prior delivery before preparing a new notification.')
                        recovered.put(db,'outbox',item)
                for case in recovered.all(db,'case'):
                    case.update(ack_due=None,followup_due=None,action_due=None)
                    if case['status'] not in {'CLOSED','SKIPPED'}:
                        case.update(status='HUMAN_REVIEW',handoff=True,review_reason='Recovered backup: staff review required before resuming',revision=case['revision']+1)
                    recovered.put(db,'case',case)
                for record in recovered.all(db,'record'):
                    recovered.version(db,'record',record)
                    record.update(active=False,version=record.get('version',1)+1,change_reason='Recovered guidance requires source revalidation',at=now())
                    recovered.version(db,'record',record);recovered.put(db,'record',record)
                for condo in recovered.all(db,'condo'):
                    recovered.version(db,'condo',condo);condo.update(review_required=True,version=condo.get('version',1)+1)
                    recovered.version(db,'condo',condo);recovered.put(db,'condo',condo)
                for case_id in {f['case_id'] for f in recovered.all(db,'feedback')}:
                    recovered.put(db,'feedback',{'id':'STYLE-RECOVERY-'+secrets.token_hex(8),'case_id':case_id,'verdict':'REJECTED','text':'','share':False,'at':now()})
                recovered.event(db,'workspace','RECOVERED_COPY','Sources paused, notifications held, guidance requires revalidation, sessions and tenant access keys revoked')
            save_selection(service.workspace_config,destination)
            result={'path':str(destination),'restart_required':True,'original_unchanged':True}
        else:raise ValueError('Unknown backup action')
        with service.store.connect() as db:
            if action=='backup':service.store.put(db,'backup',result)
            service.store.event(db,'workspace',action.upper()+'_CREATED',str(destination))
            db.execute('INSERT INTO requests VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':result})))
        return result
