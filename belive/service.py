"""Tenant-only workflow. AI proposes; deterministic code owns state and side effects."""
import json
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from belive.store import Store, bounded, digest, now, redact
from belive.settings import load_settings
from belive.ai import SupportAI, CATEGORIES, FAILURE_MESSAGES, failure_code
from belive import automation
from belive.workflow import complaint_level

COMMANDS = {'routing_settings','lesson_revoke','demo_prepare','demo_settings','learning_start','learning_improve','automation_settings','answer','answer_deactivate','intake','tenant','condo','record','portal_issue','source','approve_message','reject_message','feedback','case_action','database_location','record_update','tenant_feedback','portal_revoke'}
NOTIFICATION_KINDS = {'STAFF_ALERT','TENANT_RESPONSE','STAFF_WORK_ORDER','ACK_TIMEOUT','TENANT_FOLLOWUP'}

def support_notification(item):
    return item.get('kind') in NOTIFICATION_KINDS and not str(item.get('entity','')).startswith('MOVE-')

def support_condo(record):
    # Preserve old scheduling data on disk without treating it as current support guidance.
    legacy = record.get('review_required',False) or any(key in record for key in ('days','start','end','checklist'))
    return {'id':record['id'],'name':record['name'],'rules':'' if legacy else record['rules'],
            'verified':record.get('verified',False),'needs_review':legacy,'version':record.get('version',1)}

STATES = ['AI_PENDING','AWAITING_CONTACT','HUMAN_REVIEW','IN_PROGRESS','FOLLOW_UP','VERIFIED','CLOSED','SKIPPED','ANSWERED']

def uid(prefix): return prefix+'-'+secrets.token_hex(5).upper()
def due(minutes): return (datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat()
def require(condition,message):
    if not condition: raise ValueError(message)
def ref(value):
    require(isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value)), 'Use an internal reference of letters, numbers, underscores or hyphens')
    return value

def risk(text):
    return bool(re.search(r'\b(fire|smoke|sparks?|electrocut\w*|gas leak|gas smell|assault|suicid\w*|self.harm|trapped|threaten\w*|exposed wir\w*)\b|kebakaran|kebocoran gas|terperangkap|火灾|漏电|煤气|自杀',text,re.I))

class Service:
    def __init__(self,path,ai=None,workspace_config=None):
        self.store=Store(path);self.settings=load_settings();self.lock=threading.RLock();self.workspace_config=workspace_config
        self.ai=ai or SupportAI(self.settings,self.store.path.parent/'hermes_memory/support')
        # An interrupted external send is uncertain and must never be retried automatically.
        with self.store.connect() as db:
            for item in self.store.all(db,'outbox'):
                if item['status']=='SENDING':
                    item['status']='UNKNOWN';item['error']='INTERRUPTED_SEND';self.store.put(db,'outbox',item)
            for item in self.store.all(db,'job'):
                if item['status']=='RUNNING':
                    item['status']='INTERRUPTED';self.store.put(db,'job',item)
            for item in self.store.all(db,'learning_run'):
                if item['status'] in {'BASELINE_QUEUED','BASELINE_RUNNING','IMPROVED_QUEUED','IMPROVED_RUNNING'}:
                    item.update(status='INTERRUPTED',error='The app restarted before the comparison completed')
                    self.store.put(db,'learning_run',item)
    def context(self,db,c):
        from belive.conversations import conversation
        context={'case':{k:c[k] for k in ('title','description','category','severity')},'verified_records':[],
                 'condo_rules':None,'property_version':None,'tenant_verified':bool(c['tenant_id']),
                 'conversation':conversation(self.store,db,c)[-12:]}
        if c['tenant_id']:
            t=self.store.get(db,'tenant',c['tenant_id']);condo=support_condo(self.store.get(db,'condo',t['condo_id']))
            context['condo_rules']=condo['rules'] or None;context['property_version']={'id':condo['id'],'version':condo['version']}
            context['verified_records']=[r for r in self.store.all(db,'record') if r['tenant_id']==t['id'] and r['verified'] and r.get('active',True) and (not r.get('expires_at') or r['expires_at']>now())]
        return automation.add_context(self.store,db,c,context)
    def check_ai(self):
        check={'id':'ai','status':'RUNNING','at':now(),'provider':self.settings.llm_provider,'model':self.settings.llm_model}
        with self.store.connect() as db:self.store.put(db,'health',check)
        try:
            self.ai.check();check.update(status='PASSED',detail='A real configured-provider response passed the connection schema check.')
        except Exception as exc:
            check.update(status='FAILED',detail='AI_NOT_CONFIGURED' if str(exc)=='AI_NOT_CONFIGURED' else 'AI_CONNECTION_FAILED')
        check['finished_at']=now()
        with self.store.connect() as db:self.store.put(db,'health',check);self.store.event(db,'ai','CONNECTION_CHECK_'+check['status'],check['detail'])
        return check
    def styles(self,db,shared=False,condo_id=None):
        latest={}
        for f in reversed(self.store.all(db,'feedback')): latest[f['case_id']]=f
        cases={c['id']:c for c in self.store.all(db,'case')}
        examples=[f for f in latest.values() if f['verdict'] in {'APPROVED','CORRECTED'} and
                cases.get(f['case_id'],{}).get('status')=='CLOSED' and cases[f['case_id']].get('category') in CATEGORIES and (not shared or f.get('share'))]
        if condo_id and not shared:
            examples += [x for x in self.store.all(db,'learned_style') if x.get('active') and x.get('scope_condo')==condo_id]
        return sorted(examples,key=lambda x:x.get('at',''),reverse=True)
    def snapshot(self):
        with self.store.connect() as db:
            keys={'cases':'case','condos':'condo','tenants':'tenant',
                  'outbox':'outbox','workorders':'workorder','sources':'source','jobs':'job','records':'record'}
            result={key:self.store.all(db,kind) for key,kind in keys.items()}
            result['condos']=[support_condo(c) for c in result['condos']]
            result['outbox']=[m for m in result['outbox'] if support_notification(m)]
            for case in result['cases']:
                if case['category'] not in CATEGORIES:case['category']='OTHER'
                case['complaint_level']=complaint_level(case)
            from belive.conversations import conversation
            for case in result['cases']:
                case['conversation']=conversation(self.store,db,case)
                case['activity']=[dict(r) for r in db.execute('SELECT * FROM events WHERE entity=? ORDER BY id DESC LIMIT 100',(case['id'],))]
                active=case['status'] not in {'CLOSED','SKIPPED','VERIFIED','ANSWERED'}
                deadlines=[d for d in [case.get('ack_due') if case['status']=='HUMAN_REVIEW' else None,case.get('followup_due') if case['status']=='FOLLOW_UP' else None,case.get('action_due')] if d]
                case['due_at']=min(deadlines) if deadlines and active else None;case['overdue']=bool(case['due_at'] and case['due_at']<now())
            ranks={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'UNASSESSED':2,'LOW':3}
            result['cases'].sort(key=lambda c:(c['status'] in {'CLOSED','SKIPPED','ANSWERED'},c['severity']!='CRITICAL',not c['overdue'],ranks.get(c['severity'],4),c.get('due_at') or '9999',c['created_at']))
            for record in result['records']:record['history']=self.store.history(db,'record',record['id'])
            from belive import routing
            result['routing']=routing.settings(self.store,db)
            result['automation']=automation.policy(self.store,db)
            result['answers']=[{**a,'history':self.store.history(db,'answer',a['id'])} for a in self.store.all(db,'answer')]
            result['backups']=self.store.all(db,'backup');result['health']=self.store.all(db,'health')
            result['examples']=self.styles(db);result['audit']=self.store.audit(db)
            from belive import demo,learning
            result['demo']=demo.info(self,db)
            result['learning_runs']=[learning.public(x) for x in self.store.all(db,'learning_run')][:10]
            result['learning_lesson']=learning.LESSON
            result['learned_styles']=self.store.all(db,'learned_style')
            result['readiness']={'ai':self.ai.readiness(),'scheduler':True,'provider':self.settings.llm_provider,'model':self.settings.llm_model}
            from belive.workspace import selected_database
            active=self.store.path.resolve()
            selected=selected_database(self.workspace_config,active) if self.workspace_config else active
            result['storage']={'active':str(active),'selected':str(selected),'restart_required':active!=selected,'can_choose':bool(self.workspace_config)}
            result['reports']={
                'categories':{k:sum(c.get('category')==k for c in result['cases']) for k in CATEGORIES},
                'statuses':{k:sum(c['status']==k for c in result['cases']) for k in STATES},
                'overdue':sum(c['overdue'] for c in result['cases']),
                'human_handoffs':sum(c.get('handoff',False) for c in result['cases']),
                'automatic_answers':sum(bool(c.get('automatic_answer')) for c in result['cases']),
                'accepted_answers':sum(c['status']=='ANSWERED' for c in result['cases']),
                'verified_closures':sum(c['status']=='CLOSED' and bool(c.get('verification')) for c in result['cases'])}
            return result
    def enqueue(self,db,entity,kind,text,target=''):
        require(support_notification({'kind':kind,'entity':entity}),'Notification is outside tenant complaint support')
        if kind=='TENANT_RESPONSE':
            for old in self.store.all(db,'outbox'):
                if old['entity']==entity and old['kind']==kind and old['target']==target and old['text']==redact(text) and old['status']!='REJECTED':
                    return old
        item={'id':uid('MSG'),'entity':entity,'kind':kind,'text':redact(text),'target':target,
              'status':'PENDING_APPROVAL','created_at':now(),'outcome':''}
        self.store.put(db,'outbox',item)
        self.store.event(db,entity,'NOTIFICATION_QUEUED',kind+'; no external message sent')
        return item
    def handoff(self,db,c,reason):
        c.update(status='HUMAN_REVIEW',handoff=True,review_reason=reason,next_action='Staff assessment required',action_due=None,followup_due=None,ack_due=due(self.settings.acknowledgement_minutes),escalation=0)
        from belive.routing import destination
        c['staff_destination']=destination(self.store,db,c['category'])
        self.enqueue(db,c['id'],'STAFF_ALERT',reason,c['staff_destination'])
        automation.handover_receipt(self.store,db,c)
    def create(self,db,p):
        title=bounded(p.get('title'),4,120);description=bounded(p.get('description'),10,6000)
        platform=p.get('platform','INTERNAL')
        require(platform in {'INTERNAL','FACEBOOK','THREADS','GOOGLE','MANUAL_PUBLIC'},'Unsupported source')
        external=platform!='INTERNAL';source_id=p.get('source_id') or uid('INPUT')
        require(isinstance(source_id,str) and bool(re.fullmatch(r'[A-Za-z0-9_./:-]{1,250}',source_id)), 'Invalid stable source identifier')
        source_hash=digest(description)
        existing=db.execute('SELECT id FROM sources WHERE platform=? AND source_id=? AND hash=?',(platform,source_id,source_hash)).fetchone()
        if existing:
            for c in self.store.all(db,'case'):
                if existing[0] in c['source_versions']:return c
        tenant_id=p.get('tenant_id','')
        if tenant_id:
            t=self.store.get(db,'tenant',tenant_id);require(t['verified'],'Tenant must be verified by staff first')
        version=db.execute('INSERT INTO sources(platform,source_id,hash,body,created_at) VALUES(?,?,?,?,?)',
            (platform,source_id,source_hash,json.dumps({'title':title,'text':description}),now())).lastrowid
        for old in self.store.all(db,'case'):
            # Retries use their idempotency key; a fresh private request must not inherit an old outcome.
            if platform=='INTERNAL' and p.get('entrypoint') in {'TENANT_PORTAL','TENANT_WEBSITE'} and old['status'] in {'ANSWERED','CLOSED','SKIPPED'}:
                continue
            if old['description']==description and old.get('tenant_id','')==tenant_id and old['platform']==platform and (not external or old['source_id']==source_id):
                old['source_versions'].append(version);old['revision']+=1;self.store.put(db,'case',old)
                self.store.event(db,old['id'],'DUPLICATE_LINKED','Identical redacted text linked as another source version');return old
        c={'id':uid('BL'),'title':title,'description':description,'tenant_id':tenant_id,'platform':platform,
           'source_id':source_id,'source_versions':[version],'entrypoint':p.get('entrypoint','PUBLIC_SOURCE' if external else 'OPERATOR'),'category':'OTHER','severity':'UNASSESSED',
           'status':'AWAITING_CONTACT' if external and not tenant_id else 'AI_PENDING','revision':1,
           'created_at':now(),'updated_at':now(),'owner':'','draft':'','analysis':None,'verification':'',
           'ack_due':None,'followup_due':None,'escalation':0,'handoff':False,'review_reason':''}
        c['automation_requested']=bool(automation.policy(self.store,db)['enabled'] and c['entrypoint'] in {'TENANT_PORTAL','TENANT_WEBSITE'})
        if risk(title+' '+description):
            c['severity']='CRITICAL';self.handoff(db,c,'Potential immediate safety risk. Staff assessment required before routine AI troubleshooting.')
        elif re.search(r'ignore (?:all |previous |prior )?instructions|system prompt|execute (?:shell|command)|reveal.{0,20}(?:key|secret|password)',description,re.I):
            self.handoff(db,c,'Instruction-like source content requires staff review')
        elif c['automation_requested'] and automation.exception_reason(title+' '+description):
            reason=automation.exception_reason(title+' '+description)
            self.handoff(db,c,reason)
            if reason=='The request needs a staff decision, account check or physical action':
                c.update(severity='MEDIUM',ai_assistance_pending=True)
        elif external and not tenant_id:
            c['draft']='Please contact the official BeLive tenant-support channel privately so staff can verify your tenancy and review the issue. Do not share private details publicly.'
        self.store.put(db,'case',c);self.store.event(db,c['id'],'INTAKE_RECORDED','Source retained as an immutable redacted version')
        return c
    def command(self,name,p,key):
        require(name in COMMANDS,'Unknown action: only tenant enquiry and complaint operations are supported')
        require(isinstance(key,str) and 8<=len(key)<=150,'A request idempotency key is required')
        fingerprint=digest(json.dumps([name,p],sort_keys=True))
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT result FROM requests WHERE key=?',(key,)).fetchone()
            if prior:
                saved=json.loads(prior[0]);require(saved['fingerprint']==fingerprint,'Idempotency key reused with different data');return saved['result']
            result=self._command(db,name,{**p,'_request_key':key})
            cached={k:v for k,v in result.items() if k!='token'} if name=='portal_issue' else result
            db.execute('INSERT INTO requests VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':cached})))
            return result
    def _command(self,db,name,p):
        if name=='routing_settings':
            from belive.routing import save
            return save(self,db,p)
        if name=='demo_prepare':
            from belive.demo import prepare
            return prepare(self,db,p)
        if name=='demo_settings':
            require(type(p.get('enabled')) is bool,'Choose whether the fictional demo is enabled')
            item={'id':'tenant-demo','enabled':p['enabled'],'at':now()}
            self.store.put(db,'demo',item)
            if not item['enabled']:
                for session in self.store.all(db,'portal'):
                    if session.get('demo_session'):db.execute("DELETE FROM objects WHERE kind='portal' AND id=?",(session['id'],))
                self._demo_token=None
            self.store.event(db,'tenant-demo','DEMO_ENABLED' if item['enabled'] else 'DEMO_DISABLED',p.get('_actor','administrator'))
            return item
        if name in {'learning_start','learning_improve','lesson_revoke'}:
            from belive.learning import command
            return command(self,db,name,p)
        if name in {'automation_settings','answer','answer_deactivate'}:
            return automation.command(self,db,name,p)
        if name=='intake': return self.create(db,p)
        if name=='database_location':
            require(self.workspace_config is not None,'Database selection is not available in this session')
            from belive.workspace import save_selection
            path=save_selection(self.workspace_config,p.get('path'))
            self.store.event(db,'workspace','DATABASE_LOCATION_SELECTED','Next launch: '+str(path))
            return {'path':str(path),'restart_required':path!=self.store.path.resolve()}
        if name=='tenant':
            condo=self.store.get(db,'condo',p.get('condo_id'))
            require(p.get('confirmed') is True,'Staff must confirm tenancy against an authorised record')
            t={'id':ref(p.get('id')),'condo_id':condo['id'],'unit_ref':ref(p.get('unit_ref')),'verified':True,
               'evidence':bounded(p.get('evidence'),8,1000),'verified_by':bounded(p.get('verified_by'),2,80)}
            require(not any(x['id']==t['id'] for x in self.store.all(db,'tenant')),'Tenant reference already exists')
            self.store.put(db,'tenant',t);self.store.event(db,t['id'],'TENANCY_VERIFIED',t['evidence']);return t
        if name=='condo':
            require(p.get('confirmed') is True,'Confirm this support guidance against the property record')
            require(not any(k in p for k in ('days','start','end','checklist')), 'Only property support guidance is supported')
            old=next((c for c in self.store.all(db,'condo') if c['id']==p.get('id')),None)
            if old:self.store.version(db,'condo',old)
            c={'id':ref(p.get('id')),'name':bounded(p.get('name'),2,120),
               'rules':bounded(p.get('rules'),8,3000),'verified':True,'verified_at':now(),'version':old.get('version',1)+1 if old else 1}
            self.store.version(db,'condo',c);self.store.put(db,'condo',c);self.store.event(db,c['id'],'SUPPORT_GUIDANCE_RECORDED',c['rules']);return c
        if name=='record':
            t=self.store.get(db,'tenant',p.get('tenant_id'))
            require(p.get('confirmed') is True,'Verify the record before adding it to AI context')
            record={'id':uid('REC'),'tenant_id':t['id'],'text':bounded(p.get('text'),8,3000),'source':bounded(p.get('source'),3,250),'verified':True,'active':True,'version':1,'at':now(),'expires_at':None}
            self.store.version(db,'record',record);self.store.put(db,'record',record);self.store.event(db,t['id'],'VERIFIED_RECORD_ADDED',record['id']);return record
        if name=='record_update':
            record=self.store.get(db,'record',p.get('id'))
            require(p.get('version')==record.get('version',1),'Record changed; reload its latest version')
            reason=bounded(p.get('reason'),8,1000);action=p.get('action')
            require(action in {'CORRECT','DEACTIVATE'},'Choose CORRECT or DEACTIVATE')
            self.store.version(db,'record',record)
            if action=='CORRECT':
                require(p.get('confirmed') is True,'Verify the correction against its source')
                record.update(text=bounded(p.get('text'),8,3000),source=bounded(p.get('source'),3,250),active=True)
                expiry=p.get('expires_at') or None
                if expiry:
                    date=datetime.fromisoformat(expiry);require(date.tzinfo is not None and date>datetime.now(timezone.utc),'Expiry must be a future time with timezone')
                    expiry=date.astimezone(timezone.utc).isoformat()
                record['expires_at']=expiry
            else:record['active']=False
            record.update(version=record.get('version',1)+1,at=now(),change_reason=reason,changed_by=p.get('_actor','operator'))
            self.store.version(db,'record',record);self.store.put(db,'record',record);self.store.event(db,record['id'],'RECORD_'+action,reason);return record
        if name=='tenant_feedback':
            c=self.store.get(db,'case',p.get('id'));require(c['tenant_id']==p.get('tenant_id'),'Case does not belong to this tenant')
            resolved=p.get('resolved');require(type(resolved)is bool,'Resolution feedback must be true or false')
            require(not resolved or c['status'] not in {'CLOSED','SKIPPED'},'Case is already closed')
            default='I confirm this answered my question.' if c.get('automatic_answer') else 'I confirm the reported issue is resolved.'
            note=bounded(p.get('note') or (default if resolved else 'The issue is still unresolved.'),8,2000)
            from belive.conversations import post
            post(self.store,db,c,'TENANT',note,'feedback-'+p['_request_key'])
            c['tenant_resolution']={'resolved':resolved,'note':note,'at':now()}
            dangerous=risk(note)
            if dangerous:c['severity']='CRITICAL'
            if not resolved or dangerous or (c.get('automatic_answer') and automation.unresolved(note)):
                c['verification']='';c['action_due']=None;self.handoff(db,c,'Tenant outcome feedback contains a safety risk' if dangerous else 'Tenant reports the issue is still unresolved')
                self.store.put(db,'feedback',{'id':uid('STYLE'),'case_id':c['id'],'text':'','verdict':'REJECTED','share':False,'at':now()})
            elif c.get('automatic_answer') and c['status']=='FOLLOW_UP' and not c.get('owner') and not c.get('handoff'):
                c.update(status='ANSWERED',resolution_type='INFORMATIONAL_ANSWER_ACCEPTED',followup_due=None,action_due=None,answered_at=now())
                self.store.event(db,c['id'],'INFORMATIONAL_ANSWER_ACCEPTED','Tenant accepted an informational answer; no repair or verified closure claimed')
            c['revision']+=1;c['updated_at']=now();self.store.put(db,'case',c)
            self.store.event(db,c['id'],'TENANT_RESOLUTION_FEEDBACK',note);return {'saved':True}
        if name=='portal_revoke':
            tenant=self.store.get(db,'tenant',p.get('tenant_id'))
            require(p.get('confirmed') is True,'Confirm revocation of this tenant access')
            keys=[x for x in self.store.all(db,'portal') if x['tenant_id']==tenant['id']]
            for item in keys:db.execute("DELETE FROM objects WHERE kind='portal' AND id=?",(item['id'],))
            self.store.event(db,tenant['id'],'PORTAL_ACCESS_REVOKED',str(len(keys))+' access keys revoked')
            return {'revoked':len(keys)}
        if name=='portal_issue':
            t=self.store.get(db,'tenant',p.get('tenant_id'));token=secrets.token_urlsafe(32)
            demo_session=p.get('_demo_session') is True
            require(not demo_session or t.get('demo_only') is True,'Demo access is limited to fictional tenants')
            item={'id':digest(token),'tenant_id':t['id'],'expires':due(60 if demo_session else 10080),'demo_session':demo_session}
            self.store.put(db,'portal',item);self.store.event(db,t['id'],'PORTAL_ACCESS_ISSUED','One-hour fictional demo access' if demo_session else 'Seven-day tenant-scoped access; secret not logged')
            return {'token':token,'tenant_id':t['id'],'expires':item['expires']}
        if name=='source':
            from belive.connectors import validate_source
            source=validate_source(p)
            self.store.put(db,'source',source);self.store.event(db,source['id'],'SOURCE_CONFIGURED','Explicit operator-selected API resource');return source
        if name in {'approve_message','reject_message'}:
            m=self.store.get(db,'outbox',p.get('id'));require(support_notification(m),'Notification is outside tenant complaint support');require(m['status']=='PENDING_APPROVAL','Message already decided or attempted')
            m['status']='APPROVED' if name=='approve_message' else 'REJECTED';self.store.put(db,'outbox',m)
            self.store.event(db,m['entity'],name.upper(),m['id']);return m
        if name=='feedback':
            c=self.store.get(db,'case',p.get('id'));require(c['status']=='CLOSED','Evaluate learning after verified closure')
            verdict=p.get('verdict');require(verdict in {'APPROVED','CORRECTED','REJECTED'},'Invalid feedback')
            text='' if verdict=='REJECTED' else bounded(p.get('text') if verdict=='CORRECTED' else c['draft'],1,2000)
            f={'id':uid('STYLE'),'case_id':c['id'],'text':text,'verdict':verdict,'share':p.get('share') is True,'at':now()}
            self.store.put(db,'feedback',f);self.store.event(db,c['id'],'FEEDBACK_'+verdict,'Latest verdict controls retrieval');return f
        if name=='case_action':return self.case_action(db,p)
        raise ValueError('Unknown action')
    def case_action(self,db,p):
        c=self.store.get(db,'case',p.get('id'));require(p.get('revision')==c['revision'],'Case changed; reload before acting')
        action=p.get('action');note=p.get('note','');status=c['status']
        if action!='note':c['automation_paused']=True
        if action=='link_tenant':
            t=self.store.get(db,'tenant',p.get('tenant_id'));note=bounded(note,8,1000)
            require(not c['tenant_id'],'Case already linked to a verified tenant')
            c['tenant_id']=t['id']
            if status=='AWAITING_CONTACT':c['status']='AI_PENDING'
        elif action=='acknowledge':
            require(status in {'HUMAN_REVIEW','AI_PENDING','AWAITING_CONTACT'} or (status=='FOLLOW_UP' and c.get('automatic_answer')),'Case is not waiting for acknowledgement')
            c['owner']=bounded(p.get('owner'),2,80);c['ack_due']=None;c['status']='IN_PROGRESS';note='Staff accepted ownership'
        elif action=='draft':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'},'Reopen the case before editing');c['draft']=bounded(note,1,2500)
        elif action=='queue_response':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'} and bool(c['draft']),'A reviewed draft is required')
            require(bool(c['tenant_id']),'Verify/link the tenant before queuing a private response')
            require(p.get('confirmed') is True,'Review the exact saved response before queueing')
            self.enqueue(db,c['id'],'TENANT_RESPONSE',c['draft'],c['tenant_id']);note='Saved response queued; approval still required'
        elif action=='publish_response':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'} and c['tenant_id'] and c['draft'],'An active verified-tenant case and saved response are required')
            require(p.get('confirmed') is True,'Review the exact saved response before publishing to the tenant portal')
            from belive.conversations import post
            post(self.store,db,c,'SUPPORT',c['draft'],'support-'+digest(c['draft']))
            note='Reviewed response published to the tenant portal; no external gateway delivery claimed'
        elif action=='assess':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'},'An active case is required')
            category=p.get('category');severity=p.get('severity');note=bounded(note,8,1000)
            require(category in CATEGORIES and severity in {'LOW','MEDIUM','HIGH','CRITICAL'},'Choose a supported category and urgency')
            require(not risk(c['description']+' '+c.get('tenant_update','')+' '+c.get('tenant_resolution',{}).get('note','')) or severity=='CRITICAL','Detected safety risks require critical handling')
            c.update(category=category,severity=severity)
            if severity in {'HIGH','CRITICAL'}:self.handoff(db,c,'Staff urgency assessment: '+note)
        elif action=='note':
            note=bounded(note,8,2000)
        elif action=='plan':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'},'An active case is required')
            c['next_action']=bounded(note,8,1000);deadline=p.get('due_at')
            if deadline:
                date=datetime.fromisoformat(deadline);require(date.tzinfo is not None and date>datetime.now(timezone.utc),'Choose a future deadline with timezone')
                c['action_due']=date.astimezone(timezone.utc).isoformat()
            else:c['action_due']=None
        elif action=='workorder':
            require(bool(c['tenant_id']) and status not in {'CLOSED','SKIPPED','ANSWERED'},'Verified tenant and active case required')
            note=bounded(note,8,2000)
            w={'id':uid('WO'),'case_id':c['id'],'description':note,'department':bounded(p.get('department'),2,80),'status':'OPEN'}
            self.store.put(db,'workorder',w);self.enqueue(db,c['id'],'STAFF_WORK_ORDER',note,w['department'])
        elif action=='complete_workorder':
            w=self.store.get(db,'workorder',p.get('workorder_id'))
            require(w['case_id']==c['id'] and w['status']=='OPEN','Open work order for this case required')
            w['evidence']=bounded(note,8,2000);w['status']='COMPLETED';self.store.put(db,'workorder',w)
        elif action=='followup':
            require(status in {'IN_PROGRESS','AI_PENDING'},'Staff handling or a prepared AI response is required')
            require(bool(c['tenant_id']),'Verify tenant before case follow-up');note=bounded(note,8,2000)
            c['action_due']=None;c['status']='FOLLOW_UP';c['followup_due']=due(self.settings.followup_minutes);c['followup_count']=0
        elif action=='reassess':
            require(status=='FOLLOW_UP','Only follow-up cases can be reassessed');note=bounded(note,8,2000);self.handoff(db,c,note)
        elif action=='verify':
            require(status=='FOLLOW_UP' and c['tenant_id'],'Verified tenancy and follow-up required')
            require(p.get('confirmed') is True,'Confirm resolution against evidence or tenant feedback')
            c['verification']=bounded(note,8,2000);c['status']='VERIFIED';c['followup_due']=None
        elif action=='close':
            require(status=='VERIFIED' and c['verification'],'Record resolution evidence before closure')
            require(not any(w['case_id']==c['id'] and w['status']=='OPEN' for w in self.store.all(db,'workorder')),'Complete outstanding work orders before closure')
            c['status']='CLOSED';c['closed_at']=now();note='Operator-verified closure; not an AI resolution claim'
        elif action=='reopen':
            require(status in {'CLOSED','SKIPPED','ANSWERED'},'Only closed or skipped cases can reopen');note=bounded(note,8,2000)
            c['verification']='';self.handoff(db,c,note)
            self.store.put(db,'feedback',{'id':uid('STYLE'),'case_id':c['id'],'text':'','verdict':'REJECTED','share':False,'at':now()})
        else:raise ValueError('Unknown case action')
        c['revision']+=1;c['updated_at']=now();self.store.put(db,'case',c);self.store.event(db,c['id'],action.upper(),p.get('_actor','operator')+': '+str(note))
        return c
    def analyse(self,case_id):
        with self.lock,self.store.connect() as db:
            c=self.store.get(db,'case',case_id)
            require(c['status'] not in {'CLOSED','VERIFIED','SKIPPED','FOLLOW_UP','ANSWERED'},'AI analysis is not available at this stage')
            require(c['severity'] not in {'HIGH','CRITICAL'} and not risk(c['description']),'High-risk case requires staff handling')
            context=self.context(db,c)
            condo_id=self.store.get(db,'tenant',c['tenant_id'])['condo_id'] if c['tenant_id'] else None
            examples=self.styles(db,condo_id=condo_id)[:5];revision=c['revision'];job={'id':uid('AI'),'case_id':c['id'],'status':'RUNNING','at':now()}
            assisted_staff=bool(c.get('ai_assistance_pending') and c['status']=='HUMAN_REVIEW')
            self.store.put(db,'job',job)
        try: result=self.ai.analyse(context,examples);error=''
        except Exception as exc:
            result=None;error=failure_code(exc);job['agent_trace']=getattr(exc,'agent_trace',[])
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=self.store.get(db,'case',case_id)
            if current['revision']!=revision or self.styles(db,condo_id=condo_id)[:5]!=examples or self.context(db,current)!=context:
                job['status']='STALE';job['error']='Case or reviewed guidance changed during AI work; result not applied'
            else:
                if error:self.handoff(db,current,error+': '+FAILURE_MESSAGES[error])
                else:
                    result['record_refs']=[{'id':r['id'],'version':r.get('version',1),'source':r['source'],'text':r['text']} for r in context['verified_records'] if r['id'] in result.get('record_ids',[])]
                    if assisted_staff and result['severity']=='LOW':
                        result['severity']='MEDIUM';result['complaint_level']='MODERATE'
                    current.update(analysis=result,category=result['category'],severity=result['severity'],review_reason='')
                    if result['relevance']=='NON_SUPPORT' and not result['uncertainty'] and result['severity'] not in {'HIGH','CRITICAL'}:current['status']='SKIPPED'
                    elif result['uncertainty'] or result['relevance']=='UNCERTAIN' or result['severity'] in {'HIGH','CRITICAL'} or result.get('requires_human',False):self.handoff(db,current,'AI requires human assessment: '+result['summary'])
                    elif result['severity']=='MEDIUM':self.handoff(db,current,'MODERATE: AI has assessed the issue and prepared assistance for staff review. Only SIMPLE replies are automatic.')
                    else:current['status']='AI_PENDING' if current['tenant_id'] else 'AWAITING_CONTACT'
                    if result.get('response'):current['draft']=result['response']
                    if assisted_staff:
                        current.update(status='HUMAN_REVIEW',handoff=True,next_action='Review the AI assessment and proposed response before replying')
                    else:automation.apply_result(self,db,current,result,context)
                    job['agent_trace']=result.get('agent_trace',[])
                current['ai_assistance_pending']=False
                current['revision']+=1;current['updated_at']=now();self.store.put(db,'case',current)
                job['status']='FAILED' if error else 'COMPLETED';job['error']=error
            self.store.put(db,'job',job);self.store.event(db,case_id,'AI_'+job['status'],job.get('error') or ('Approved informational answer published automatically' if current.get('automatic_answer') and current['status']=='FOLLOW_UP' else 'Grouped support assessment saved; staff review applies'))
        return job
    def tick(self):
        with self.lock,self.store.connect() as db:
            moment=now()
            for c in self.store.all(db,'case'):
                changed=False
                if c['status']=='HUMAN_REVIEW' and c.get('ack_due') and c['ack_due']<=moment and c['escalation']<2:
                    c['escalation']+=1;c['ack_due']=due(self.settings.acknowledgement_minutes) if c['escalation']<2 else None
                    target='backup-support' if c['escalation']==1 else 'management'
                    self.enqueue(db,c['id'],'ACK_TIMEOUT','Unacknowledged support case requires attention.',target);changed=True
                    self.store.event(db,c['id'],'ESCALATED',target)
                if c['status']=='FOLLOW_UP' and c.get('followup_due') and c['followup_due']<=moment:
                    n=c.get('followup_count',0)+1;c['followup_count']=n
                    if c.get('automatic_answer') and not c.get('owner'):
                        if n>=2 or not automation.policy(self.store,db)['enabled']:
                            self.handoff(db,c,'Informational answer needs staff follow-up; no resolution claimed')
                        else:
                            from belive.conversations import post
                            post(self.store,db,c,'SYSTEM','Did this answer your question? You can accept the answer, ask a follow-up or request staff here.','automatic-reminder-'+c['automatic_answer']['message_id'])
                            c['followup_due']=due(self.settings.followup_minutes)
                    else:
                        self.enqueue(db,c['id'],'TENANT_FOLLOWUP','Please confirm whether the reported issue is still present. Your case remains open.',c['tenant_id'])
                        if n>=2:self.handoff(db,c,'Follow-up overdue after two recorded reminder cycles')
                        else:c['followup_due']=due(self.settings.followup_minutes)
                    changed=True
                if changed:c['revision']+=1;self.store.put(db,'case',c)
    def portal(self,token):
        with self.store.connect() as db:
            item=self.store.get(db,'portal',digest(token));require(item['expires']>now(),'Portal access expired')
            tenant=item['tenant_id']
            cases=[{k:c.get(k) for k in ('id','title','description','status','created_at')} for c in self.store.all(db,'case') if c['tenant_id']==tenant]
            from belive.conversations import conversation
            for case in cases:
                full=self.store.get(db,'case',case['id'])
                case['conversation']=conversation(self.store,db,full)
                case['informational_answer']=bool(full.get('automatic_answer') and not full.get('handoff'))
                case['automatic_pending']=bool(full['status']=='AI_PENDING' and not full.get('analysis') and automation.eligible(self.store,db,full))
                case['complaint_level']=complaint_level(full)
                case['ai_assistance_pending']=bool(full.get('ai_assistance_pending'))
                case['ai_draft_ready']=bool(full['status']=='HUMAN_REVIEW' and full.get('analysis') and full.get('draft'))
            record=self.store.get(db,'tenant',tenant);prop=self.store.get(db,'condo',record['condo_id'])
            return {'tenant_id':tenant,'cases':cases,'property_name':prop['name'],'unit_ref':record['unit_ref'],
                    'demo_only':bool(record.get('demo_only') and prop.get('demo_only'))}
    def portal_submit(self,token,p,key,entrypoint='TENANT_PORTAL'):
        require(entrypoint in {'TENANT_PORTAL','TENANT_WEBSITE'},'Unsupported tenant entry point')
        tenant=self.portal(token)['tenant_id']
        return self.command('intake',{'title':p.get('title'),'description':p.get('description'),'tenant_id':tenant,'platform':'INTERNAL','entrypoint':entrypoint},key)
    def portal_update(self,token,p,key):
        require(isinstance(key,str) and 8<=len(key)<=150,'A request idempotency key is required')
        tenant=self.portal(token)['tenant_id']
        with self.lock,self.store.connect() as db:
            c=self.store.get(db,'case',p.get('id'));require(c['tenant_id']==tenant,'Case does not belong to this tenant')
            require(c['status']!='CLOSED','Contact staff to reopen a closed case')
            note=bounded(p.get('note'),8,3000)
            fingerprint=digest(json.dumps([tenant,p],sort_keys=True));old=db.execute('SELECT result FROM requests WHERE key=?',(key,)).fetchone()
            if old:
                saved=json.loads(old[0]);require(saved['fingerprint']==fingerprint,'Idempotency mismatch');return saved['result']
            from belive.conversations import post
            post(self.store,db,c,'TENANT',note,'update-'+key)
            self.store.event(db,c['id'],'TENANT_UPDATE',note)
            c['tenant_update']=note;c['revision']+=1
            if risk(note):c['severity']='CRITICAL';c['verification']='';self.handoff(db,c,'Tenant update contains potential safety risk')
            elif c.get('automation_requested') and automation.exception_reason(note):
                self.handoff(db,c,automation.exception_reason(note))
            elif c.get('automatic_answer') and automation.unresolved(note):
                self.handoff(db,c,'Tenant says the automatic answer did not help')
            elif automation.eligible(self.store,db,c):
                c.update(status='AI_PENDING',analysis=None,followup_due=None)
            elif c.get('automatic_answer') and not c.get('handoff') and not c.get('owner'):
                self.handoff(db,c,'Automatic support is paused; staff follow-up required')
            self.store.put(db,'case',c)
            db.execute('INSERT INTO requests VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':{'saved':True}})))
            return {'saved':True}

    def portal_feedback(self,token,p,key):
        tenant=self.portal(token)['tenant_id']
        return self.command('tenant_feedback',{'id':p.get('id'),'resolved':p.get('resolved'),'note':p.get('note'),'tenant_id':tenant},key)
