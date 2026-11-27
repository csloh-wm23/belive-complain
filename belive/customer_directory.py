"""Empty, private customer-record store; explicitly selected facts for support only."""
import re
from belive.store import now,digest

FIELDS=('customer_id','name','phone','tenancy_id','property_id','property_name','unit','source')

class LocalCustomerRecords:
    """Replace this adapter after the sales database contract is agreed."""
    def records(self,service,db):return service.store.all(db,'customer_profile')

def records(service,db):
    return (getattr(service,'customer_records',None) or LocalCustomerRecords()).records(service,db)

def selected(service,db,thread):
    link=thread.get('customer_record') or {}
    if link.get('case_id')!=thread['case_id']:return None
    return next((r for r in records(service,db) if r['id']==link.get('id') and r.get('active') is True and r['version']==link.get('version')),None)

def facts(service,db,thread):
    r=selected(service,db,thread)
    if not r:return None
    # Names and contact details stay in the staff interface. The model only needs
    # the selected support location; this never establishes account identity.
    return {k:r[k] for k in ('id','version','property_id','property_name','unit')}|{'identity_verified':False,'selection':'STAFF_CONFIRMED_FOR_CURRENT_CASE'}

def command(service,db,name,p):
    if p.get('confirmed') is not True:raise ValueError('Confirm you checked these details')
    if name=='customer_profile_save':
        value={}
        for field in FIELDS:
            text=p.get(field,'')
            if not isinstance(text,str) or len(text.strip())>160:raise ValueError('Invalid '+field)
            value[field]=text.strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value['customer_id']):raise ValueError('Enter a stable customer ID')
        if not value['name'] or not value['source']:raise ValueError('Customer name and source are required')
        key='CUSTOMER-'+digest([value['customer_id'],value['tenancy_id']])[:20]
        old=next((r for r in records(service,db) if r['id']==key),None)
        if not old and p.get('version') is not None:raise ValueError('Customer or tenancy ID changed; clear the form to create a separate record')
        if old and p.get('version')!=old['version']:raise ValueError('Record changed; refresh before saving')
        if type(p.get('active',True)) is not bool:raise ValueError('Invalid active state')
        record={**value,'id':key,'version':old['version']+1 if old else 1,'active':p.get('active',True),'checked_at':now(),'checked_by':p.get('_actor','staff')}
        service.store.put(db,'customer_profile',record)
        service.store.event(db,key,'CUSTOMER_RECORD_SAVED','Private support record updated')
        return {'id':key,'version':record['version']}
    if name!='customer_profile_link':raise ValueError('Unknown customer-record action')
    thread=service.store.get(db,'wa_thread',p.get('thread_id'))
    if p.get('revision')!=thread['revision']:raise ValueError('Conversation changed; refresh before linking')
    record_id=p.get('record_id','')
    if record_id:
        record=next((r for r in records(service,db) if r['id']==record_id and r.get('active')),None)
        if not record or p.get('version')!=record['version']:raise ValueError('Choose a current active customer record')
        thread['customer_record']={'id':record['id'],'version':record['version'],'case_id':thread['case_id']}
    else:thread.pop('customer_record',None)
    thread['revision']+=1;service.store.put(db,'wa_thread',thread)
    service.store.event(db,thread['case_id'],'CUSTOMER_RECORD_LINKED','Staff selected support facts' if record_id else 'Staff cleared support facts')
    return {'thread_id':thread['id']}

def snapshot(service,db):
    return {'records':records(service,db),'automatic_matching':False,'provider':'LOCAL_PLACEHOLDER'}
