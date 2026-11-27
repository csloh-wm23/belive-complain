"""Internal work ownership; no action here dispatches or messages an external team."""
from datetime import datetime,timedelta,timezone
from belive.store import now,bounded

STATES={'QUEUED','ACCEPTED','IN_PROGRESS','BLOCKED','WORK_DONE'}
HOURS={'LOW':24,'MEDIUM':24,'HIGH':2,'CRITICAL':0.25}

def view(item):
    progress=item.get('maintenance_progress') or {'state':'QUEUED','updated_at':item['at'],'owner':''}
    try:
        deadline=datetime.fromisoformat(progress['updated_at'])+timedelta(hours=HOURS.get(item.get('severity'),24))
        overdue=item['status']!='CLOSED' and progress['state']!='WORK_DONE' and datetime.now(timezone.utc)>deadline
    except (KeyError,ValueError,TypeError):deadline=None;overdue=False
    return {**progress,'reminder_at':deadline.isoformat() if deadline else None,'overdue':overdue,'internal_only':True,
            'customer_confirmation_pending':progress['state']=='WORK_DONE' and item['status']!='CLOSED'}

def command(service,db,p):
    item=service.store.get(db,'wa_staff',p.get('request_id'))
    if not item.get('maintenance') or item['status']=='CLOSED':raise ValueError('Choose an active maintenance issue')
    thread=service.store.get(db,'wa_thread',item['thread_id'])
    if item['case_id']!=thread['case_id']:raise ValueError('This issue belongs to an older case')
    if p.get('request_revision')!=item.get('revision',0):raise ValueError('Issue changed; refresh before updating')
    if p.get('confirmed') is not True:raise ValueError('Confirm this progress was actually checked')
    state=p.get('state');old=view(item)['state']
    transitions={'QUEUED':{'ACCEPTED'},'ACCEPTED':{'IN_PROGRESS','BLOCKED'},'IN_PROGRESS':{'IN_PROGRESS','BLOCKED','WORK_DONE'},'BLOCKED':{'BLOCKED','IN_PROGRESS'},'WORK_DONE':set()}
    if state not in transitions.get(old,set()):raise ValueError('Choose the next valid work stage')
    if state=='ACCEPTED' and not item.get('location_complete') and item.get('severity') not in {'HIGH','CRITICAL'}:raise ValueError('Collect the affected location before accepting routine work')
    if any(o['status'] in {'QUEUED','UNKNOWN','SENDING'} and (o.get('request_id')==item['id'] or o.get('reply_to_message_id')==item.get('origin_message_id')) for o in service.store.all(db,'wa_outgoing')):raise ValueError('Wait for the queued reply or check the unconfirmed customer send before changing this issue')
    note=bounded(p.get('note'),8,2000)
    previous=item.get('maintenance_progress') or {}
    progress={'state':state,'owner':previous.get('owner') or p.get('_actor_name') or p.get('_actor','staff'),'updated_at':now(),'note':note,'updated_by':p.get('_actor','staff')}
    item.setdefault('maintenance_history',[]).append(progress)
    item['maintenance_progress']=progress;item['revision']=item.get('revision',0)+1
    service.store.put(db,'wa_staff',item)
    from belive.whatsapp import _queue_guidance
    _queue_guidance(service,db,item)
    service.store.event(db,item['case_id'],'INTERNAL_MAINTENANCE_PROGRESS',state+'; '+note+'; no external dispatch')
    return {'request_id':item['id'],'state':state}
