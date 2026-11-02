"""Explicit, fictional-only demo access. Never a shortcut into normal tenant records."""
import json
from pathlib import Path
from belive.store import digest,now

PROPERTY='DEMO-SUPPORT-LAB'
TENANT='DEMO-AUTOMATION-TEST'

def info(service,db):
    config=next(iter(service.store.all(db,'demo')), {})
    tenants={x['id']:x for x in service.store.all(db,'tenant')}
    properties={x['id']:x for x in service.store.all(db,'condo')}
    tenant=tenants.get(TENANT,{});prop=properties.get(PROPERTY,{})
    enabled=bool(config.get('enabled') and tenant.get('demo_only') is True
                 and prop.get('demo_only') is True and tenant.get('condo_id')==PROPERTY and not prop.get('review_required'))
    return {'available':enabled,'label':'Fictional demo tenant' if enabled else ''}

def prepare(service,db,p):
    if p.get('confirmed') is not True:raise ValueError('Confirm that demo records are fictional')
    props={x['id']:x for x in service.store.all(db,'condo')}
    tenants={x['id']:x for x in service.store.all(db,'tenant')}
    if PROPERTY in props:
        prop=props[PROPERTY]
        if not (prop.get('demo_only') or prop['name'].startswith('DEMO ONLY')):
            raise ValueError('The reserved demo property reference is already in use')
    else:
        prop=service._command(db,'condo',dict(id=PROPERTY,name='DEMO ONLY - Support automation lab',
            rules='Fictional local support demonstration. No real company rules, account facts, schedules or completed work are supplied.',confirmed=True))
    if TENANT in tenants:
        tenant=tenants[TENANT]
        if tenant['condo_id']!=PROPERTY or not (tenant.get('demo_only') or tenant.get('evidence','').startswith('Fictional')):
            raise ValueError('The reserved demo tenant reference is already in use')
    else:
        tenant=service._command(db,'tenant',dict(id=TENANT,condo_id=PROPERTY,unit_ref='DEMO-ROOM',
            verified_by='Fictional demo setup',evidence='Fictional tenant used only for the local prototype demonstration.',confirmed=True))
    prop['demo_only']=True;tenant['demo_only']=True
    service.store.put(db,'condo',prop);service.store.put(db,'tenant',tenant)
    entries=json.loads((Path(__file__).resolve().parents[1]/'demo/support_knowledge.json').read_text(encoding='utf-8'))
    old=service.store.all(db,'answer');added=0
    for entry in entries:
        if any(a['condo_id']==PROPERTY and a['question']==entry['question'] and a['language']==entry['language'] for a in old):continue
        service._command(db,'answer',{**entry,'condo_id':PROPERTY,'confirmed':True,'_actor':p.get('_actor','Demo setup')});added+=1
    service.store.put(db,'demo',{'id':'tenant-demo','enabled':True,'at':now()})
    service.store.event(db,TENANT,'DEMO_PREPARED','Fictional tenant only; no normal tenant access granted')
    return {'prepared':True,'knowledge_added':added,'available':True}

def session(service):
    with service.lock,service.store.connect() as db:
        if not info(service,db)['available']:raise ValueError('The fictional tenant demo is not enabled')
        token=getattr(service,'_demo_token',None)
        if token:
            old=next((x for x in service.store.all(db,'portal') if x['id']==digest(token)),None)
            if old and old['expires']>now():return {'token':token,'demo_only':True}
        access=service._command(db,'portal_issue',{'tenant_id':TENANT,'_demo_session':True})
        service._demo_token=access['token']
        return {'token':access['token'],'demo_only':True}
