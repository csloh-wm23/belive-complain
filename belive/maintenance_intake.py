"""Location-aware maintenance intake and priority; notification receipts remain separate."""
from belive.store import now

LEVELS={'LOW':1,'MEDIUM':2,'HIGH':3,'CRITICAL':4}
LABELS={'LOW':'Information','MEDIUM':'Routine maintenance','HIGH':'Urgent','CRITICAL':'Emergency'}

def update(service,db,item,case,context):
    proposed=(context.get('assessment') or {}).get('severity') or case.get('severity','MEDIUM')
    candidates=[x for x in (proposed,item.get('severity'),'MEDIUM') if x in LEVELS]
    severity=max(candidates,key=LEVELS.get)
    location=context.get('maintenance_location') or {}
    item.update(severity=severity,priority=LEVELS[severity],priority_label=LABELS[severity])
    if location.get('property') or location.get('unit'):
        known=item.get('maintenance_location') or {}
        item['maintenance_location']={k:location.get(k) or known.get(k,'') for k in ('property','unit')}
        item['location_complete']=bool(location.get('complete') and location.get('property') and location.get('unit'))
    item['intake_state']='READY_FOR_MAINTENANCE' if item.get('location_complete') else 'NEEDS_LOCATION'
    place=item.get('maintenance_location') or {}
    text=f"Priority {item['priority']}/4 · {severity} · {LABELS[severity]}\nProperty: {place.get('property') or 'Not yet supplied'}\nRoom / affected area: {place.get('unit') or 'Not yet supplied'}\n{item['intake_state']}\n{item['question']}"
    old=next((x for x in service.store.all(db,'outbox') if x['id']==item.get('notification_id')),None)
    status='PENDING_APPROVAL' if item.get('location_complete') or severity in {'HIGH','CRITICAL'} else 'NEEDS_DETAILS'
    if old and old.get('kind')=='STAFF_WORK_ORDER' and old.get('text')==text and old.get('target')==item['assigned_team'] and old['status'] not in {'REJECTED','CANCELLED'}:
        return
    if old and old['status'] in {'PENDING_APPROVAL','NEEDS_DETAILS'}:
        old.update(status='CANCELLED',error='Superseded by current maintenance intake');service.store.put(db,'outbox',old)
    notice=service.enqueue(db,case['id'],'STAFF_WORK_ORDER',text,item['assigned_team'])
    notice.update(status=status,support_request_id=item['id'],severity=severity,priority=item['priority'],intake_state=item['intake_state'],location=place,
                  supersedes_notice_id=old['id'] if old else None)
    service.store.put(db,'outbox',notice);item['notification_id']=notice['id']
    service.store.event(db,case['id'],'MAINTENANCE_INTAKE_UPDATED',severity+'; '+item['intake_state']+'; '+status+'; external dispatch not confirmed')
