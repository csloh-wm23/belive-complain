"""Public case messages are separate from private operator audit notes."""
from belive.store import now,bounded,digest

def post(store,db,case,sender,text,key):
    mid='CHAT-'+digest(case['id']+':'+key)[:24]
    existing=next((x for x in store.all(db,'message') if x['id']==mid),None)
    if existing:return existing
    message={'id':mid,'case_id':case['id'],'tenant_id':case['tenant_id'],'sender':sender,'text':bounded(text,1,3000),'at':now()}
    store.put(db,'message',message);return message

def conversation(store,db,case):
    result=[{'id':'REPORT-'+case['id'],'sender':'REPORTED_ISSUE','text':case['description'],'at':case['created_at']}]
    result += [{k:m[k] for k in ('id','sender','text','at')} for m in store.all(db,'message') if m['case_id']==case['id'] and m['tenant_id']==case['tenant_id']]
    # Preserve tenant updates from versions that predate the conversation table.
    for row in db.execute("SELECT id,detail,created_at FROM events WHERE entity=? AND action='TENANT_UPDATE'",(case['id'],)):
        if not any(m['sender']=='TENANT' and m['text']==row['detail'] for m in result):
            result.append({'id':'HISTORIC-'+str(row['id']),'sender':'TENANT','text':row['detail'],'at':row['created_at']})
    return sorted(result,key=lambda m:m['at'])
