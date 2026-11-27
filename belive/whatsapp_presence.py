"""Best-effort official typing status, never a generated answer or dispatch receipt."""
import json,threading,time
from urllib.request import Request,build_opener
from belive.connectors import NoRedirect
from belive.store import now

def send(config,message_id):
    payload={'messaging_product':'whatsapp','status':'read','message_id':message_id,'typing_indicator':{'type':'text'}}
    request=Request('https://graph.facebook.com/'+config['graph_version']+'/'+config['phone_number_id']+'/messages',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+config['access_token'],'Content-Type':'application/json'},method='POST')
    with build_opener(NoRedirect).open(request,timeout=3) as response:
        return json.loads(response.read(2000)).get('success') is True

def pulse(service,tid):
    from belive import whatsapp as wa
    from belive.credentials import credential_scope
    with credential_scope(service.store.path):
        if not wa.ready():return False
        with service.lock,service.store.connect() as db:
            thread=service.store.get(db,'wa_thread',tid)
            if thread.get('simulated') or time.time()-thread.get('last_customer_at',0)>86400:return False
            case=service.store.get(db,'case',thread['case_id'])
            if case['status'] in {'CLOSED','ANSWERED','SKIPPED','VERIFIED'}:return False
            if not any(t['thread_id']==tid and t['case_id']==thread['case_id'] and t['status'] in {'PENDING','PROCESSING'} for t in service.store.all(db,'wa_turn')):return False
            message=next((m for m in service.store.all(db,'wa_message') if m['thread_id']==tid and m['case_id']==thread['case_id'] and m['direction']=='CUSTOMER' and m.get('external_id')),None)
            if not message:return False
        try:accepted=send(wa.configuration(),message['external_id'])
        except Exception:accepted=False
        with service.lock,service.store.connect() as db:
            service.store.put(db,'wa_presence',{'id':tid,'message_id':message['id'],'at':now(),'status':'ACCEPTED' if accepted else 'UNAVAILABLE'})
        return True

class Presence:
    def __init__(self,service,tid):self.service=service;self.tid=tid;self.stop=threading.Event();self.worker=None
    def __enter__(self):
        from belive.ai import SupportAI
        if isinstance(self.service.ai,SupportAI) and self.service.settings.agent_engine=='hermes':
            with self.service.store.connect() as db:thread=self.service.store.get(db,'wa_thread',self.tid)
            if not thread.get('simulated'):
                def run():
                    deadline=time.monotonic()+180
                    while not self.stop.is_set() and time.monotonic()<deadline:
                        try:
                            if not pulse(self.service,self.tid):break
                        except Exception:break
                        if self.stop.wait(20):break
                self.worker=threading.Thread(target=run,daemon=True);self.worker.start()
        return self
    def __exit__(self,*exc):
        self.stop.set()
        if self.worker:self.worker.join(timeout=0.1)
