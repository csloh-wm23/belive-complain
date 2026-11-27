"""Tenant-only workflow. AI proposes; deterministic code owns state and side effects."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from belive.store import Store, bounded, digest, now, redact
from belive.settings import load_settings
from belive.ai import SupportAI, CATEGORIES, FAILURE_MESSAGES, failure_code
from belive import automation, hosted_ai, decisions
from belive import closure
from belive.workflow import complaint_level

COMMANDS = {'routing_settings','lesson_revoke','demo_prepare','demo_settings','learning_start','learning_improve','automation_settings','answer','answer_deactivate','intake','tenant','condo','record','portal_issue','source','approve_message','reject_message','feedback','case_action','database_location','record_update','tenant_feedback','portal_revoke'}
NOTIFICATION_KINDS = {'STAFF_ALERT','TENANT_RESPONSE','STAFF_WORK_ORDER','ACK_TIMEOUT','TENANT_FOLLOWUP'}
COMMANDS.add('source_schedule')
COMMANDS.add('closure_settings')
COMMANDS.update({'reply_learning_scan','reply_learning_action'})
COMMANDS.update({'wa_simulate','wa_knowledge','wa_staff_reply','wa_staff_complete','wa_property'})
COMMANDS.add('wa_document_action')
COMMANDS.add('wa_channel')
COMMANDS.add('public_followup')

PROPERTY_DIRECTORY = Path(__file__).resolve().parents[1] / 'assets' / 'property-directory.json'

def directory_location(location):
    entered = ' '.join(location['property'].split()).casefold()
    listings = json.loads(PROPERTY_DIRECTORY.read_text(encoding='utf-8'))
    match = next((item for item in listings if ' '.join(item['name'].split()).casefold() == entered),None)
    if match:
        return {**location,'property':match['name'],'address':match['address']}
    return location

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
        self.store=Store(path);self.settings=load_settings(path);self.lock=threading.RLock();self.memory_lock=threading.RLock();self.workspace_config=workspace_config
        self.ai=ai or SupportAI(self.settings,self.store.path.parent/'hermes_memory/support')
        if isinstance(self.ai,SupportAI):self.ai.execution_observer=self.record_native_execution
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
            for item in self.store.all(db,'reply_learning'):
                if item['status'] in {'ANALYSING','REVIEWING'}:
                    item.update(status='FAILED',approved=False,error='Interrupted; analyse or review again')
                if item.get('preview_status')=='RUNNING':item['preview_status']='FAILED'
                self.store.put(db,'reply_learning',item)
            for item in self.store.all(db,'wa_outgoing'):
                if item['status']=='SENDING':item.update(status='UNKNOWN',error='Interrupted send: check WhatsApp before retrying');self.store.put(db,'wa_outgoing',item)
            for item in self.store.all(db,'wa_turn'):
                if item['status']=='PROCESSING':item['status']='PENDING';self.store.put(db,'wa_turn',item)
    def record_native_execution(self,event):
        if event.get('engine')!='hermes-native' or event.get('agent_class')!='run_agent.AIAgent':raise ValueError('Unverified native execution record')
        allowed=('engine','agent_class','version','commit','api_calls','executed_tools','memory_entries','native_memory_loaded','role','mode','provider','model','scope_hash','elapsed_ms','queue_ms','reused_worker')
        item={k:event.get(k) for k in allowed};item.update(id='NATIVE-'+secrets.token_hex(10),at=now())
        with self.lock,self.store.connect() as db:self.store.put(db,'native_execution',item)
    def context(self,db,c):
        from belive.conversations import conversation
        context={'case':{k:c[k] for k in ('title','description','category','severity')},'verified_records':[],
                 'condo_rules':None,'property_version':None,'tenant_verified':bool(c['tenant_id']),
                 'conversation':conversation(self.store,db,c)[-12:]}
        context['reported_location']=c.get('reported_location')
        if c['tenant_id']:
            t=self.store.get(db,'tenant',c['tenant_id']);condo=support_condo(self.store.get(db,'condo',t['condo_id']))
            context['condo_rules']=condo['rules'] or None;context['property_version']={'id':condo['id'],'version':condo['version']}
            context['verified_records']=[r for r in self.store.all(db,'record') if r['tenant_id']==t['id'] and r['verified'] and r.get('active',True) and (not r.get('expires_at') or r['expires_at']>now())]
        return automation.add_context(self.store,db,c,context)
    def check_ai(self):
        check={'id':'ai','status':'RUNNING','at':now(),'provider':self.settings.llm_provider,'model':self.settings.llm_model,
               'engine':self.settings.agent_engine,
               'decisions':decisions.enabled(self.settings)}
        with self.store.connect() as db:self.store.put(db,'health',check)
        try:
            self.ai.check()
            detail = 'A real native Hermes Agent response passed the connection schema check.' if self.settings.agent_engine=='hermes' else 'A real direct-provider response passed the connection schema check (not native Hermes).'
            if decisions.enabled(self.settings):
                detail += ' Decisions triage also returned valid choices.'
            check.update(status='PASSED',detail=detail)
        except Exception as exc:
            code = failure_code(exc)
            detail = FAILURE_MESSAGES[code] if code in hosted_ai.FAILURE_MESSAGES else (
                'AI_NOT_CONFIGURED' if code == 'AI_NOT_CONFIGURED' else 'AI_CONNECTION_FAILED')
            check.update(status='FAILED', detail=detail)
        check['finished_at']=now()
        with self.store.connect() as db:self.store.put(db,'health',check);self.store.event(db,'ai','CONNECTION_CHECK_'+check['status'],check['detail'])
        return check
    def styles(self,db,shared=False,condo_id=None):
        from belive import shared_memory
        if shared_memory.enabled(self,db) and not shared:
            examples=[{'id':x['id'],'text':x['answer'],'public_question':x['question'],'verdict':'CORRECTED','sample_data':x.get('sample_data',False),'case_id':None,'at':''} for x in shared_memory.experiences(self,db)]
            examples += [{'id':x['id'],'text':x['tip'],'public_question':x['question'],'writing_tip':True,'verdict':'CORRECTED','scope_category':None,'sample_data':x.get('sample_data',False),'case_id':None,'at':''} for x in shared_memory.tips(self,db)]
            return examples
        latest={}
        for f in reversed(self.store.all(db,'feedback')): latest[f['case_id']]=f
        cases={c['id']:c for c in self.store.all(db,'case')}
        examples=[f for f in latest.values() if f['verdict'] in {'APPROVED','CORRECTED'} and
                cases.get(f['case_id'],{}).get('status')=='CLOSED' and cases[f['case_id']].get('closure_reason')!='CUSTOMER_INACTIVE' and cases[f['case_id']].get('category') in CATEGORIES and (not shared or f.get('share'))]
        from belive.relevance import sample_case
        examples=[{**f,'sample_data':sample_case(cases[f['case_id']]),'provenance':'Sample / test complaint experience' if sample_case(cases[f['case_id']]) else 'Staff-approved complaint experience'} for f in examples]
        if condo_id and not shared:
            examples += [{**x,'scope_category':x.get('scope_category','WIFI')}
                         for x in self.store.all(db,'learned_style') if x.get('active') and x.get('scope_condo')==condo_id]
        if not shared:
            from belive.relevance import domains
            examples += [{'id':x['id'],'text':x['tip'],'verdict':'CORRECTED','scope_category':None,
                          'public_question':x['question'],'general_scope':x['category']=='OTHER' and not domains(x['question']),
                          'writing_tip':True,'at':x['at'],'sample_data':x.get('sample_data',False),'case_id':x['case_id']}
                         for x in self.store.all(db,'reply_learning') if x.get('approved') and x['status']=='APPROVED' and x.get('scope_condo')==condo_id]
        return sorted(examples,key=lambda x:x.get('at',''),reverse=True)
    def public_lessons(self,db):
        from belive import shared_memory
        if shared_memory.enabled(self,db):return {x['id']:(x['question'],x['answer']) for x in shared_memory.experiences(self,db)}
        lessons={}
        seen=set()
        for feedback in self.store.all(db,'feedback'):
            cid=feedback['case_id']
            if cid in seen:continue
            seen.add(cid)
            if feedback.get('public_question') and feedback['verdict']=='CORRECTED':
                case=self.store.get(db,'case',cid)
                if case['status']=='CLOSED' and case.get('closure_reason')!='CUSTOMER_INACTIVE':
                    lessons[feedback['id']]=(feedback['public_question'],feedback['text'])
                    if len(lessons)==12:break
        return lessons

    def snapshot(self):
        with self.store.connect() as db:
            keys={'cases':'case','condos':'condo','tenants':'tenant',
                  'outbox':'outbox','workorders':'workorder','sources':'source','jobs':'job','records':'record'}
            result={key:self.store.all(db,kind) for key,kind in keys.items()}
            from belive import shared_memory
            result['shared_memory']=shared_memory.status(self,db)
            result['condos']=[support_condo(c) for c in result['condos']]
            from belive.connectors import scan_interval
            result['source_interval_minutes']=scan_interval(self.store,db)
            result['outbox']=[m for m in result['outbox'] if support_notification(m)]
            for case in result['cases']:
                if case['category'] not in CATEGORIES:case['category']='OTHER'
                case['complaint_level']=complaint_level(case)
            from belive.conversations import conversation
            for case in result['cases']:
                case['conversation']=conversation(self.store,db,case)
                from belive import public_preview
                case['public_followups']=self.public_followups(db,case['id'])
                case['public_preview_current']=public_preview.is_current(case,case['public_followups'])
                case['can_contact_customer']=bool(case['tenant_id'] or self.has_complaint_access(db,case,browser_only=True))
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
            result['closure_policy']=closure.policy(self.store,db)
            for case in result['cases']:
                case['auto_close_at']=closure.deadline(case,result['closure_policy']['days']) if closure.waiting(case) else None
                if case['platform']=='GOOGLE':
                    from belive.google_replies import readiness
                    case['google_posting']=readiness(self.store,db,case)
            result['answers']=[{**a,'history':self.store.history(db,'answer',a['id'])} for a in self.store.all(db,'answer')]
            result['backups']=self.store.all(db,'backup');result['health']=self.store.all(db,'health')
            result['examples']=[x for x in self.styles(db) if not x.get('writing_tip')];result['audit']=self.store.audit(db)
            active_public=self.public_lessons(db)
            usage={lesson_id:set() for lesson_id in active_public}
            latest={}
            for event in db.execute("SELECT entity,detail FROM events WHERE action='PUBLIC_LESSON_USED' ORDER BY id DESC"):
                for lesson_id in event['detail'].split(', '):
                    if lesson_id in usage:
                        usage[lesson_id].add(event['entity'])
                        latest.setdefault(lesson_id,event['entity'])
            result['public_lesson_count']=len(active_public)
            for example in result['examples']:
                lesson_id=example['id']
                example.update(public_active=lesson_id in active_public,
                               matched_cases=len(usage.get(lesson_id,())),
                               latest_match=latest.get(lesson_id))
            from belive import demo,learning
            result['demo']=demo.info(self,db)
            from belive.whatsapp import snapshot as whatsapp_snapshot
            result['whatsapp']=whatsapp_snapshot(self,db)
            result['learning_runs']=[learning.public(x) for x in self.store.all(db,'learning_run')][:10]
            result['learning_lesson']=''
            from belive.experience_learning import experiences
            result['learning_experiences']=experiences(self,db)
            reactions = self.store.all(db,'reply_learning')
            result['reply_learning']=[item for item in reactions if item['status']!='OBSERVED' or item.get('signal')][:60]
            result['feedback_reactions']={key:sum(item.get('reaction')==key for item in reactions)
                                          for key in ['DISSATISFIED','POSITIVE','NEUTRAL','UNCLEAR']}
            usages=self.store.all(db,'reply_tip_usage')
            signals=self.store.all(db,'reply_learning')
            for item in result['reply_learning']:
                matched=[u for u in usages if item['id'] in u['tip_ids']]
                item['provided_count']=len(matched)
                item['latest_case']=matched[0]['case_id'] if matched else None
                item['negative_after_use']=sum(any(s['case_id']==u['case_id'] and s['reply_id']==u['reply_id']
                                                       and s.get('signal',True) for s in signals) for u in matched)
                item['positive_after_use']=sum(any(s['case_id']==u['case_id'] and s['reply_id']==u['reply_id']
                                                       and s.get('reaction')=='POSITIVE' for s in signals) for u in matched)
            result['learning_scenarios']=learning.scenarios(self,db)
            result['learned_styles']=self.store.all(db,'learned_style')
            result['readiness']={'ai':self.ai.readiness(),'scheduler':True,'provider':self.settings.llm_provider,'model':self.settings.llm_model,
                                 'engine':self.settings.agent_engine,'native_executions':self.store.all(db,'native_execution')[:15],
                                 'hosted':hosted_ai.uses_direct_api(self.settings), 'decisions':decisions.enabled(self.settings)}
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
            totals = [c.get('reply_outcomes', {}) for c in result['cases']]
            result['reports']['reply_outcomes'] = {
                key: sum(outcome.get(key, 0) for outcome in totals)
                for key in ('staff_replies', 'ai_drafts_sent', 'ai_drafts_unchanged', 'reopened_after_reply')
            }
            return result
    def record_reopen(self, db, case):
        if case['status'] not in {'CLOSED', 'ANSWERED', 'VERIFIED'}:
            return
        if any(m['case_id'] == case['id'] and m['sender'] in {'SUPPORT', 'AI_SUPPORT'}
               for m in self.store.all(db, 'message')):
            case.setdefault('reply_outcomes', {})['reopened_after_reply'] = 1

    def enqueue(self,db,entity,kind,text,target=''):
        require(support_notification({'kind':kind,'entity':entity}),'Notification is outside tenant complaint support')
        if kind=='TENANT_RESPONSE':
            for old in self.store.all(db,'outbox'):
                if old['entity']==entity and old['kind']==kind and old['target']==target and old['text']==redact(text) and old['status'] not in {'REJECTED','CANCELLED'}:
                    return old
        item={'id':uid('MSG'),'entity':entity,'kind':kind,'text':redact(text),'target':target,
              'status':'PENDING_APPROVAL','created_at':now(),'outcome':''}
        self.store.put(db,'outbox',item)
        self.store.event(db,entity,'NOTIFICATION_QUEUED',kind+'; no external message sent')
        return item
    def handoff(self,db,c,reason,target=None,notify=True):
        c.pop('staff_followup',None)
        c.pop('waiting_since',None);c.pop('closure_reason',None)
        c.update(status='HUMAN_REVIEW',handoff=True,review_reason=reason,next_action='Staff assessment required',action_due=None,followup_due=None,ack_due=due(self.settings.acknowledgement_minutes),escalation=0)
        from belive.routing import destination
        c['staff_destination']=target or destination(self.store,db,c['category'])
        notification=self.enqueue(db,c['id'],'STAFF_ALERT',reason,c['staff_destination']) if notify else None
        automation.handover_receipt(self.store,db,c)
        return notification
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
            # Anonymous website complaints deduplicate only through their idempotency key: matching text can belong to different people.
            if platform=='INTERNAL' and p.get('entrypoint') in {'TENANT_WEBSITE','WHATSAPP'}:
                continue
            # A verified tenant may reuse an active matching thread, but never a completed outcome.
            if platform=='INTERNAL' and p.get('entrypoint')=='TENANT_PORTAL' and old['status'] in {'ANSWERED','CLOSED','SKIPPED'}:
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
        if name=='public_followup':
            from belive.connectors import public_link_platform
            case=self.store.get(db,'case',p.get('id'))
            require(case['revision']==p.get('revision'),'Case changed. Refresh before recording a customer reply.')
            require(case.get('entrypoint')=='PUBLIC_SOURCE' and case['platform'] in {'GOOGLE','FACEBOOK','THREADS'},'Choose a public platform complaint')
            require(case['status'] not in {'CLOSED','SKIPPED','VERIFIED','ANSWERED'},'Reopen this complaint before adding a customer reply')
            text=bounded(p.get('text'),1,3000)
            source_url=p.get('source_url') or ''
            require(isinstance(source_url,str) and len(source_url)<=2000,'Use a valid public reply link')
            if source_url:
                require(public_link_platform(source_url)==case['platform'],'Use a reply link from the same platform')
            previous=self.public_followups(db,case['id'])
            if previous and previous[-1]['text']==text and previous[-1]['source_url']==source_url:
                return {'id':case['id'],'followup_id':previous[-1]['id'],'revision':case['revision']}
            item={'id':uid('PUB'),'case_id':case['id'],'text':text,'source_url':source_url,
                  'recorded_by':p.get('_actor','operator'),'created_at':now(),'provenance':'OPERATOR_RECORDED_PUBLIC_FOLLOWUP'}
            self.store.put(db,'public_followup',item)
            self.store.event(db,case['id'],'PUBLIC_FOLLOWUP_RECORDED','Observed public reply recorded by '+item['recorded_by'])
            if risk(text):
                case['severity']='CRITICAL'
                self.handoff(db,case,'Customer follow-up reports a potential immediate safety risk')
            case['revision']+=1;case['updated_at']=now();self.store.put(db,'case',case)
            return {'id':case['id'],'followup_id':item['id'],'revision':case['revision']}
        if name=='wa_document_action':
            from belive.company_sop import document_action
            return document_action(self,db,p)
        if name=='wa_channel':
            from belive.whatsapp_channel import save
            return save(self,db,p)
        if name in {'wa_simulate','wa_knowledge','wa_staff_reply','wa_staff_complete','wa_property'}:
            from belive.whatsapp import command
            return command(self,db,name,p)
        if name in {'reply_learning_scan','reply_learning_action'}:
            from belive.reply_learning import command
            return command(self,db,name,p)
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
        if name=='closure_settings':
            days=p.get('days');require(type(days) is int and 1<=days<=90,'Choose 1–90 days')
            item={'id':'customer-inactivity','days':days,'changed_at':now()}
            self.store.put(db,'closure_policy',item);self.store.event(db,item['id'],'CLOSURE_POLICY_UPDATED',str(days)+' days; '+p.get('_actor','operator'));return item
        if name=='intake':
            if 'public_url' not in p:
                return self.create(db,p)
            from belive.connectors import public_link_platform
            url=p['public_url'].strip() if isinstance(p['public_url'],str) else ''
            platform=public_link_platform(url)
            case=self.create(db,{'title':p.get('title'),'description':p.get('description'),
                                 'platform':platform,'source_id':'public-link-'+digest(url)})
            if not case.get('public_url'):
                case['public_url']=url
                self.store.put(db,'case',case)
            return case
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
            dangerous=risk(note)
            resolved=resolved and not dangerous and not automation.unresolved(note)
            c['tenant_resolution']={'resolved':resolved,'note':note,'at':now()}
            if dangerous:c['severity']='CRITICAL'
            if not resolved:
                self.record_reopen(db,c)
                c.pop('closed_at',None)
                if c.get('entrypoint')=='TENANT_WEBSITE' and not c['tenant_id']:c.update(owner='',owner_id='')
                c['verification']='';c['action_due']=None;self.handoff(db,c,'Tenant outcome feedback contains a safety risk' if dangerous else 'Tenant reports the issue is still unresolved')
                self.store.put(db,'feedback',{'id':uid('STYLE'),'case_id':c['id'],'text':'','verdict':'REJECTED','share':False,'at':now()})
            elif c.get('automatic_answer') and c['status']=='FOLLOW_UP' and not c.get('owner') and not c.get('handoff'):
                c.update(status='ANSWERED',resolution_type='INFORMATIONAL_ANSWER_ACCEPTED',followup_due=None,action_due=None,answered_at=now())
                self.store.event(db,c['id'],'INFORMATIONAL_ANSWER_ACCEPTED','Tenant accepted an informational answer; no repair or verified closure claimed')
            elif c.get('entrypoint')=='TENANT_WEBSITE' and not c['tenant_id'] and c['status']=='FOLLOW_UP':
                c['followup_due']=None
                c['next_action']='Staff review customer confirmation and close the case'
            c['revision']+=1;c['updated_at']=now();self.store.put(db,'case',c)
            from belive.reply_learning import discover
            discover(self,db,c['id'])
            self.store.event(db,c['id'],'TENANT_RESOLUTION_FEEDBACK',note);return {'saved':True}
        if name=='portal_revoke':
            tenant=self.store.get(db,'tenant',p.get('tenant_id'))
            require(p.get('confirmed') is True,'Confirm revocation of this tenant access')
            keys=[x for x in self.store.all(db,'portal') if x.get('tenant_id')==tenant['id']]
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
        if name=='source_schedule':
            minutes=p.get('minutes')
            require(type(minutes) is int and 1<=minutes<=1440,'Choose an interval from 1 to 1440 minutes')
            config={'id':'schedule','minutes':minutes}
            self.store.put(db,'source_schedule',config)
            for source in self.store.all(db,'source'):
                if source['enabled'] and source.get('last_scan'):
                    source['next_scan']=due(minutes)
                    self.store.put(db,'source',source)
            return config
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
            require(c.get('closure_reason')!='CUSTOMER_INACTIVE','A no-reply closure has no verified outcome; reopen and verify before teaching Hermes')
            verdict=p.get('verdict');require(verdict in {'APPROVED','CORRECTED','REJECTED'},'Invalid feedback')
            text='' if verdict=='REJECTED' else bounded(p.get('text') if verdict=='CORRECTED' else c['draft'],1,2000)
            f={'id':uid('STYLE'),'case_id':c['id'],'text':text,'verdict':verdict,'share':p.get('share') is True,'at':now()}
            if p.get('publish_public') is True and verdict!='REJECTED':
                require(verdict=='CORRECTED','Write a general question and answer before approving public reuse')
                question=bounded(p.get('public_question'),8,240)
                require(len(text)<=900 and not risk(question+' '+text)
                        and not re.search(r'\[(?:email|number) removed\]|\b(?:otp|password|bank account)\b|密码',question+' '+text,re.I),
                        'Public guidance must be short, safe and free of private details')
                f.update(public_question=question,share=False)
            self.store.put(db,'feedback',f);self.store.event(db,c['id'],'FEEDBACK_'+verdict,'Latest verdict controls retrieval');return f
        if name=='case_action':return self.case_action(db,p)
        raise ValueError('Unknown action')
    def has_complaint_access(self,db,case,*,browser_only=False):
        return case.get('entrypoint')=='TENANT_WEBSITE' and any(
            (not browser_only or 'case_ids' in entry) and self.portal_case_allowed(entry,case)
            and not entry.get('tenant_id') and entry['expires']>now()
            for entry in self.store.all(db,'portal'))

    def case_action(self,db,p):
        c=self.store.get(db,'case',p.get('id'));require(p.get('revision')==c['revision'],'Case changed; reload before acting')
        action=p.get('action');note=p.get('note','');status=c['status']
        if action not in {'note','review_link'}:c['automation_paused']=True
        if action=='review_link':
            from belive.connectors import google_review_share_link
            require(c['platform']=='GOOGLE' and c['entrypoint']=='PUBLIC_SOURCE','Select a Google public review case')
            review_url=google_review_share_link(p.get('review_url'))
            if c.get('review_url')==review_url:return c
            c['review_url']=review_url
            note='Individual Google review link saved by staff'
        elif action=='link_tenant':
            t=self.store.get(db,'tenant',p.get('tenant_id'));note=bounded(note,8,1000)
            require(not c['tenant_id'],'Case already linked to a verified tenant')
            c['tenant_id']=t['id']
            if status=='AWAITING_CONTACT':c['status']='AI_PENDING'
        elif action=='acknowledge':
            require(status in {'HUMAN_REVIEW','AI_PENDING','AWAITING_CONTACT'} or (status=='FOLLOW_UP' and (c.get('automatic_answer') or c.get('staff_followup'))),'Case is not waiting for acknowledgement')
            c.pop('staff_followup',None)
            c['owner']=bounded(p.get('owner'),2,80);c['owner_id']=p.get('_actor','');c['ack_due']=None;c['status']='IN_PROGRESS';note='Staff accepted ownership'
        elif action=='draft':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'},'Reopen the case before editing');c['draft']=bounded(note,1,2500)
            c.pop('draft_tip_ids',None)
        elif action=='queue_response':
            require(status not in {'CLOSED','SKIPPED','ANSWERED'} and bool(c['draft']),'A reviewed draft is required')
            require(bool(c['tenant_id']),'Verify/link the tenant before queuing a private response')
            require(p.get('confirmed') is True,'Review the exact saved response before queueing')
            self.enqueue(db,c['id'],'TENANT_RESPONSE',c['draft'],c['tenant_id']);note='Saved response queued; approval still required'
        elif action in {'publish_response','send_reply'}:
            if action=='send_reply':c['draft']=bounded(p.get('reviewed_reply'),1,2500)
            require(status not in {'CLOSED','SKIPPED','ANSWERED'} and c['draft'],'An active complaint and saved response are required')
            require(c['tenant_id'] or self.has_complaint_access(db,c),'This case has no private complaint conversation. Ask the customer to use Make a complaint.')
            require(p.get('confirmed') is True,'Review the reply before sending it to the customer')
            if 'reviewed_reply' in p:
                require(bounded(p['reviewed_reply'],1,2500)==c['draft'],'Save the edited reply before sending it')
            from belive.conversations import post
            message_key = 'support-'+digest(c['draft'])
            message_id = 'CHAT-'+digest(c['id']+':'+message_key)[:24]
            if not db.execute("SELECT 1 FROM objects WHERE kind='message' AND id=?", (message_id,)).fetchone():
                outcome = c.setdefault('reply_outcomes', {})
                outcome['staff_replies'] = outcome.get('staff_replies',0)+1
                original = c.get('ai_draft_original')
                if original:
                    outcome['ai_drafts_sent'] = outcome.get('ai_drafts_sent',0)+1
                    outcome['ai_drafts_unchanged'] = outcome.get('ai_drafts_unchanged',0)+int(original==c['draft'])
            c.pop('ai_draft_original',None)
            post(self.store,db,c,'SUPPORT',c['draft'],message_key)
            from belive.reply_learning import usage
            tips=[x for x in self.store.all(db,'reply_learning') if x['id'] in c.get('draft_tip_ids',[]) and x.get('approved')]
            usage(self,db,c,message_id,tips)
            if c['status']=='FOLLOW_UP':c['waiting_since']=now()
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
        elif action=='staff_followup':
            require(status in {'IN_PROGRESS','FOLLOW_UP','VERIFIED'} and c.get('owner'),'Take ownership before continuing staff follow-up')
            note=bounded(note,8,2000)
            deadline=p.get('due_at') or due(1440)
            date=datetime.fromisoformat(deadline)
            require(date.tzinfo is not None and date>datetime.now(timezone.utc),'Choose a future deadline with timezone')
            c.update(status='FOLLOW_UP',staff_followup=True,next_action=note,action_due=date.astimezone(timezone.utc).isoformat(),followup_due=None,verification='')
            c.pop('waiting_since',None);c.pop('tenant_resolution',None)
        elif action=='followup':
            require(status in {'IN_PROGRESS','AI_PENDING'} or (status=='FOLLOW_UP' and c.get('staff_followup')),'Staff handling or a prepared AI response is required')
            c.pop('staff_followup',None)
            require(c['tenant_id'] or self.has_complaint_access(db,c),'There is no private conversation for this case. Ask the customer to submit through Make a complaint first.')
            note=bounded(note,8,2000)
            c['action_due']=None;c['status']='FOLLOW_UP';c['followup_due']=due(self.settings.followup_minutes);c['followup_count']=0
            c['waiting_since']=now();c.pop('tenant_resolution',None);c.pop('closure_reason',None)
            if not c['tenant_id']:
                from belive.conversations import post
                c.pop('tenant_resolution',None)
                post(self.store,db,c,'SYSTEM',f'The BeLive team has recorded an action. Please choose Issue resolved or Still unresolved. If you do not reply within {closure.policy(self.store,db)["days"]} days, this complaint will close without a confirmed resolution. You can reopen it later from Track complaint in the browser you used to submit it.','staff-followup-'+str(c['revision']))
        elif action=='reassess':
            require(status=='FOLLOW_UP','Only follow-up cases can be reassessed');note=bounded(note,8,2000);self.handoff(db,c,note)
        elif action in {'verify','verify_close','verify_staff_close'}:
            if action=='verify_staff_close':
                require(status=='IN_PROGRESS' or (status=='FOLLOW_UP' and c.get('staff_followup')),'Take ownership before recording verified closure')
                require(not c['tenant_id'] and not self.has_complaint_access(db,c,browser_only=True),
                        'Ask the customer to confirm the outcome in their private conversation')
            else:
                require(status=='FOLLOW_UP','Start follow-up before verifying resolution')
                if not c['tenant_id']:
                    require(c.get('entrypoint')=='TENANT_WEBSITE' and c.get('tenant_resolution',{}).get('resolved') is True,
                            'Wait for the customer to confirm the issue is resolved')
            require(p.get('confirmed') is True,'Confirm resolution against evidence or tenant feedback')
            c['verification']=bounded(note,8,2000);c['status']='VERIFIED';c['followup_due']=None
            if action in {'verify_close','verify_staff_close'}:
                require(not any(w['case_id']==c['id'] and w['status']=='OPEN' for w in self.store.all(db,'workorder')),'Complete outstanding work orders before closure')
                c['status']='CLOSED';c['closed_at']=now()
        elif action=='close':
            require(status=='VERIFIED' and c['verification'],'Record resolution evidence before closure')
            require(not any(w['case_id']==c['id'] and w['status']=='OPEN' for w in self.store.all(db,'workorder')),'Complete outstanding work orders before closure')
            c['status']='CLOSED';c['closed_at']=now();note='Operator-verified closure; not an AI resolution claim'
        elif action=='reopen':
            require(status in {'CLOSED','SKIPPED','ANSWERED'},'Only closed or skipped cases can reopen');note=bounded(note,8,2000)
            self.record_reopen(db,c)
            c.pop('closure_reason',None);c.pop('waiting_since',None)
            c['verification']='';self.handoff(db,c,note)
            self.store.put(db,'feedback',{'id':uid('STYLE'),'case_id':c['id'],'text':'','verdict':'REJECTED','share':False,'at':now()})
        else:raise ValueError('Unknown case action')
        c['revision']+=1;c['updated_at']=now();self.store.put(db,'case',c);self.store.event(db,c['id'],action.upper(),p.get('_actor','operator')+': '+str(note))
        return c
    def import_browser_review(self, review, actor):
        from belive.browser_reviews import google_listing_link, review_identity
        review_link = review.get('review_url')
        identity = review_identity(review_link)
        if review_link:
            require(identity is not None, 'The browser did not return an individual Google review link')
        link = review_link or google_listing_link(review.get('listing_url'))
        source_id = review['source_id']
        with self.lock, self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for case in self.store.all(db,'case'):
                if case['platform']=='GOOGLE' and case.get('entrypoint')=='PUBLIC_SOURCE':
                    existing_link=case.get('review_url') or case.get('public_url')
                    if case['source_id']==source_id or (identity and review_identity(existing_link)==identity):
                        if review_link and not case.get('review_url'):
                            case.update(review_url=review_link, revision=case['revision']+1)
                            self.store.put(db,'case',case)
                            self.store.event(db,case['id'],'REVIEW_LINK','Direct review link confirmed by browser')
                        return case,False
            rating=review['rating']
            label=f"{rating} star{'s' if rating!=1 else ''}"
            case=self.create(db,{'title':f'Google Maps review - {label}', 'description':review['description'],
                                 'platform':'GOOGLE','source_id':source_id})
            case.update(public_url=link,review_url=review_link,review_rating=rating)
            self.store.put(db,'case',case)
            self.store.event(db,case['id'],'BROWSER_REVIEW_IMPORTED',actor+': one visible Google Maps review, '+label)
            return case,True

    def public_followups(self, db, case_id):
        return sorted((item for item in self.store.all(db,'public_followup') if item['case_id']==case_id),
                      key=lambda item:item['created_at'])

    def prepare_public_preview(self, case_id, revision, actor):
        from belive import public_preview, public_diagnostics
        with self.lock, self.store.connect() as db:
            case = self.store.get(db, 'case', case_id)
            require(case['revision'] == revision, 'Case changed. Refresh it before preparing a preview.')
            require(case['entrypoint'] == 'PUBLIC_SOURCE' and case['platform'] in {'GOOGLE', 'FACEBOOK', 'THREADS'},
                    'Choose a public platform complaint')
            assessment = case.get('analysis') or {}
            require(assessment.get('report_type') == 'COMPLAINT' and assessment.get('relevance') == 'SUPPORT'
                    and not assessment.get('uncertainty') and case['status'] not in {'CLOSED', 'SKIPPED', 'VERIFIED', 'ANSWERED'},
                    'A confirmed, active public complaint assessment is required')
            context = public_preview.context(case,self.public_followups(db,case_id))
            input_fingerprint = public_preview.fingerprint(context)
        try:
            diagnostic = public_diagnostics.prepare(self,context)
            context.update(research_state=diagnostic['state'],research_details=diagnostic['details'],
                           research_summary=diagnostic['research_summary'],research_sources=diagnostic['sources'],
                           research_clarification=diagnostic.get('clarification',''))
            reply = self.ai.public_reply_preview(context)
            try:
                public_diagnostics.validate_reply(self,context,reply)
            except public_diagnostics.DiagnosticReviewFailure as rejected:
                # Rejected evidence is not proof that confirmed customer details are missing.
                diagnostic.update(state=rejected.fallback_state,research_summary='',
                                  checked_sources=diagnostic['sources'],sources=[],review_feedback=rejected.review)
                context.update(research_state=diagnostic['state'],research_details=diagnostic['details'],
                               research_summary='',research_sources=[],diagnostic_review_feedback=rejected.review)
                reply = self.ai.public_reply_preview(context)
        except Exception as exc:
            raise ValueError(FAILURE_MESSAGES[failure_code(exc)]) from exc
        with self.lock, self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self.store.get(db, 'case', case_id)
            require(current['revision'] == revision, 'Case changed. Refresh it before preparing a preview.')
            current['public_reply_preview'] = {
                'text': reply, 'agent': 'Public Reply Preview Agent', 'at': now(),
                'source_version': current['source_versions'][-1],
                'format_version':public_preview.VERSION,'input_fingerprint':input_fingerprint,
                'research_state':diagnostic['state'],'device_details':diagnostic['details'],
                'sources':diagnostic['sources'],
                'checked_sources':diagnostic.get('checked_sources',[]),
                'research_clarification':diagnostic.get('clarification',''),
                'diagnostic_review':diagnostic.get('review_feedback'),
            }
            current['revision'] += 1
            self.store.put(db, 'case', current)
            self.store.event(db, case_id, 'PUBLIC_REPLY_PREVIEW', actor + ' generated a local preview for staff review')
        return current['public_reply_preview']

    def analyse(self,case_id):
        with self.lock,self.store.connect() as db:
            c=self.store.get(db,'case',case_id)
            require(c['status'] not in {'CLOSED','VERIFIED','SKIPPED','FOLLOW_UP','ANSWERED'},'AI analysis is not available at this stage')
            require(c['severity'] not in {'HIGH','CRITICAL'} and not risk(c['description']),'High-risk case requires staff handling')
            context=self.context(db,c)
            condo_id=self.store.get(db,'tenant',c['tenant_id'])['condo_id'] if c['tenant_id'] else None
            examples=self.styles(db,condo_id=condo_id);revision=c['revision'];job={'id':uid('AI'),'case_id':c['id'],'status':'RUNNING','at':now()}
            public_source=c.get('entrypoint')=='PUBLIC_SOURCE' and not c['tenant_id']
            from belive.relevance import select
            question=c.get('public_guidance_turn',{}).get('text',c['description'])
            from belive.reply_learning import matching
            writing_tips=matching(self,db,question,condo_id)
            lessons=select(question,self.public_lessons(db)) if c.get('entrypoint') in {'TENANT_WEBSITE','PUBLIC_SOURCE'} and not c['tenant_id'] else {}
            assisted_staff=bool(c.get('ai_assistance_pending') and c['status']=='HUMAN_REVIEW')
            self.store.put(db,'job',job)
        public_reply=''
        public_turn=c.get('public_guidance_turn')
        question=public_turn['text'] if public_turn else c['description']
        classify_public=getattr(self.ai,'classify_public_guidance',None)
        result = None
        error = ''
        if public_source:
            try:
                result = self.ai.analyse(context,examples)
            except Exception as exc:
                error = failure_code(exc)
                job['agent_trace'] = getattr(exc,'agent_trace',[])
        simple_public = bool(result and result.get('report_type') == 'COMPLAINT'
                             and result.get('relevance') == 'SUPPORT' and result.get('severity') == 'LOW'
                             and not result.get('uncertainty') and not result.get('requires_human'))
        if (classify_public and not c['tenant_id']
                and ((c.get('entrypoint')=='TENANT_WEBSITE' and c['status']=='AI_PENDING')
                     or (simple_public and c['status']=='AWAITING_CONTACT'))
                and not c.get('owner') and not c.get('handoff') and not c.get('automation_paused')
                and not automation.exception_reason(c['title']+' '+question)):
            try:
                composer=getattr(self.ai,'conversational_reply',None)
                if composer and not public_source:
                    public_reply,topics=composer(context['conversation'],question,lessons,known_location=c.get('reported_location'),writing_tips=writing_tips)
                    decision={'can_answer':bool(public_reply),'topics':topics}
                else:
                    decision=classify_public(c['title'],question,c['description'] if public_turn else None,lessons)
                    public_reply=automation.public_guidance_reply(decision,lessons,public_source=public_source)
            except Exception:
                pass  # The existing assessment path handles model and parsing failures.
        if not public_source and not public_reply and not public_turn:
            try:
                result = self.ai.analyse(context,examples)
            except Exception as exc:
                error = failure_code(exc)
                job['agent_trace'] = getattr(exc,'agent_trace',[])
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=self.store.get(db,'case',case_id)
            if (current['revision']!=revision or self.styles(db,condo_id=condo_id)!=examples or self.context(db,current)!=context
                    or (public_reply and select(question,self.public_lessons(db))!=lessons)):
                job['status']='STALE';job['error']='Case or reviewed guidance changed during AI work; result not applied'
            else:
                if public_reply:
                    if public_source:
                        current.update(status='AWAITING_CONTACT',severity='LOW',draft=public_reply,
                                       next_action='Public guidance prepared; no reply posted to the source',
                                       category=result['category'], analysis=result, public_guidance_prepared=True)
                        job['agent_trace']=result.get('agent_trace',[])
                        self.store.event(db,case_id,'PUBLIC_GUIDANCE_PREPARED','Draft prepared locally; no external reply sent')
                    else:
                        automation.publish_public_guidance(self.store,db,current,public_reply,'AI_SUPPORT',public_turn['id'] if public_turn else 'initial')
                        from belive.reply_learning import usage
                        usage(self,db,current,current.get('automatic_answer',{}).get('message_id'),writing_tips)
                    used=[topic for topic in decision['topics'] if topic in lessons]
                    if used:self.store.event(db,case_id,'PUBLIC_LESSON_USED',', '.join(used))
                elif public_turn:
                    self.handoff(db,current,'No matching public guidance for the customer’s follow-up')
                elif error:self.handoff(db,current,error+': '+FAILURE_MESSAGES[error])
                else:
                    result['record_refs']=[{'id':r['id'],'version':r.get('version',1),'source':r['source'],'text':r['text']} for r in context['verified_records'] if r['id'] in result.get('record_ids',[])]
                    if assisted_staff and result['severity']=='LOW':
                        result['severity']='MEDIUM';result['complaint_level']='MODERATE'
                    current.update(analysis=result,category=result['category'],severity=result['severity'],review_reason='')
                    if result['relevance']=='NON_SUPPORT' and not result['uncertainty'] and result['severity'] not in {'HIGH','CRITICAL'}:current['status']='SKIPPED'
                    elif result['uncertainty'] or result['relevance']=='UNCERTAIN' or result['severity'] in {'HIGH','CRITICAL'} or result.get('requires_human',False):self.handoff(db,current,'AI requires human assessment: '+result['summary'])
                    elif result['severity']=='MEDIUM':self.handoff(db,current,'MODERATE: AI has assessed the issue and prepared assistance for staff review. Only SIMPLE replies are automatic.')
                    elif current.get('entrypoint')=='TENANT_WEBSITE' and not context.get('automatic'):
                        self.handoff(db,current,'Website complaint requires staff follow-up')
                    elif public_source and classify_public:
                        self.handoff(db,current,'Public complaint needs investigation or has no matching general guidance')
                    else:current['status']='AI_PENDING' if current['tenant_id'] else 'AWAITING_CONTACT'
                    if result.get('response'):
                        current['draft']=result['response']
                        current['draft_tip_ids']=[x['id'] for x in writing_tips]
                        current['ai_draft_original']=result['response']
                    if assisted_staff:
                        current.update(status='HUMAN_REVIEW',handoff=True,next_action='Review the AI assessment and proposed response before replying')
                    else:automation.apply_result(self,db,current,result,context)
                    if current.get('automatic_answer') and current['status']=='FOLLOW_UP':
                        current.pop('ai_draft_original',None)
                        from belive.reply_learning import usage
                        usage(self,db,current,current['automatic_answer'].get('message_id'),writing_tips)
                    job['agent_trace']=result.get('agent_trace',[])
                current['ai_assistance_pending']=False
                current.pop('public_guidance_turn',None)
                current['revision']+=1;current['updated_at']=now();self.store.put(db,'case',current)
                job['status']='FAILED' if error else 'COMPLETED';job['error']=error
            self.store.put(db,'job',job);self.store.event(db,case_id,'AI_'+job['status'],job.get('error') or ('Approved informational answer published automatically' if current.get('automatic_answer') and current['status']=='FOLLOW_UP' else 'Grouped support assessment saved; staff review applies'))
        return job
    def tick(self):
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            from belive.reply_learning import discover
            discover(self,db)
            moment=now()
            for c in self.store.all(db,'case'):
                changed=False
                if c['status']=='HUMAN_REVIEW' and c.get('ack_due') and c['ack_due']<=moment and c['escalation']<2:
                    c['escalation']+=1;c['ack_due']=due(self.settings.acknowledgement_minutes) if c['escalation']<2 else None
                    target='backup-support' if c['escalation']==1 else 'management'
                    self.enqueue(db,c['id'],'ACK_TIMEOUT','Unacknowledged support case requires attention.',target);changed=True
                    self.store.event(db,c['id'],'ESCALATED',target)
                if closure.waiting(c):
                    had_wait=c.get('waiting_since')
                    closed=closure.tick(self,db,c,moment)
                    changed=changed or closed or not had_wait
                if c['status']=='FOLLOW_UP' and not c.get('staff_followup') and c.get('followup_due') and c['followup_due']<=moment and not c.get('tenant_resolution',{}).get('resolved'):
                    n=c.get('followup_count',0)+1;c['followup_count']=n
                    if c.get('automatic_answer') and not c.get('owner'):
                        if not closure.waiting(c) and (n>=2 or not automation.policy(self.store,db)['enabled']):
                            self.handoff(db,c,'Informational answer needs staff follow-up; no resolution claimed')
                        else:
                            from belive.conversations import post
                            post(self.store,db,c,'SYSTEM','Did this answer your question? You can accept the answer, ask a follow-up or request staff here.','automatic-reminder-'+c['automatic_answer']['message_id'])
                            c['followup_due']=due(self.settings.followup_minutes)
                    else:
                        if c['tenant_id']:
                            self.enqueue(db,c['id'],'TENANT_FOLLOWUP','Please confirm whether the reported issue is still present. Your case remains open.',c['tenant_id'])
                        elif c.get('entrypoint')=='TENANT_WEBSITE':
                            from belive.conversations import post
                            post(self.store,db,c,'SYSTEM','Please confirm whether the reported issue is still present. Your case remains open.','complaint-reminder-'+str(c['revision']))
                        if n>=2 and not closure.waiting(c):self.handoff(db,c,'Follow-up overdue after two recorded reminder cycles')
                        else:c['followup_due']=due(self.settings.followup_minutes)
                    changed=True
                if changed:c['revision']+=1;self.store.put(db,'case',c)
    def _portal_token(self,token):
        token=str(token or '').strip()
        return token.upper() if token.upper().startswith('CMP-') else token
    def _portal_scope(self,db,token):
        item=self.store.get(db,'portal',digest(self._portal_token(token)))
        require(item['expires']>now(),'Portal access expired')
        return item
    @staticmethod
    def portal_case_allowed(scope,case):
        if 'case_ids' in scope:
            return case['id'] in scope['case_ids']
        if scope.get('case_id'):
            return case['id']==scope['case_id']
        return bool(scope.get('tenant_id')) and case['tenant_id']==scope['tenant_id']

    def browser_session(self, token):
        with self.lock,self.store.connect() as db:
            if token:
                try:
                    if 'case_ids' in self._portal_scope(db,token):
                        return token
                except ValueError:
                    pass
            token=secrets.token_urlsafe(32)
            self.store.put(db,'portal',{'id':digest(token),'case_ids':[],'expires':due(60*24*180)})
            return token

    def _complaint_code(self,db,case_id):
        try:secret=self.store.get(db,'secret','complaint-code')['value']
        except ValueError:
            secret=secrets.token_hex(32)
            self.store.put(db,'secret',{'id':'complaint-code','value':secret,'created_at':now()})
        raw=hmac.new(bytes.fromhex(secret),case_id.encode(),hashlib.sha256).digest()[:10]
        text=base64.b32encode(raw).decode().rstrip('=')
        return 'CMP-'+'-'.join(text[i:i+4] for i in range(0,len(text),4))
    def website_submit(self,p,key,*,browser_token=None):
        from belive.complaint_mail import address
        from belive.conversations import post
        require(isinstance(key,str) and 8<=len(key)<=150,'A request idempotency key is required')
        email=address(p.get('email',''))
        payload={'title':p.get('title'),'description':p.get('description'),'platform':'INTERNAL','entrypoint':'TENANT_WEBSITE'}
        # Older clients may still send complaints without location fields.
        if p.get('rental_property') or p.get('rental_unit'):
            payload['reported_location']={
                'property':bounded(p.get('rental_property',''),0,120),
                'unit':bounded(p.get('rental_unit',''),0,60)
            }
        request=['website_complaint',payload]
        if email:
            request.append(digest(email))
        if browser_token:
            request.append(digest(browser_token))
        fingerprint=digest(json.dumps(request,sort_keys=True))
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            browser=None
            if browser_token:
                browser=self._portal_scope(db,browser_token)
                require('case_ids' in browser,'Open the complaint form in this browser first')
            prior=db.execute('SELECT result FROM requests WHERE key=?',(key,)).fetchone()
            if prior:
                saved=json.loads(prior[0]);require(saved['fingerprint']==fingerprint,'Idempotency key reused with different data')
                result=saved['result'];case=self.store.get(db,'case',result['id'])
            else:
                case=self.create(db,payload)
                if 'reported_location' in payload:
                    case['reported_location']=directory_location(payload['reported_location'])
                    self.store.put(db,'case',case)
                post(self.store,db,case,'SYSTEM','We received your complaint. You can follow replies and add details here.','website-receipt')
                if not hasattr(self.ai,'conversational_reply'):
                    automation.publish_public_answer(self.store,db,case)
                if email:
                    self.store.put(db,'complaint_recovery',{'id':case['id'],'email_hash':digest(email),'retry_after':'','verified':False})
                result={'id':case['id'],'status':case['status'],'received_at':case['created_at']}
                db.execute('INSERT INTO requests VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':result})))
            if browser is not None:
                if case['id'] not in browser['case_ids']:
                    browser['case_ids'].append(case['id'])
                    browser['expires']=due(60*24*180)
                    self.store.put(db,'portal',browser)
                return result
            code=self._complaint_code(db,case['id'])
            portal={'id':digest(code),'case_id':case['id'],'expires':due(60*24*180),'complaint_access':True}
            self.store.put(db,'portal',portal)
            return {**result,'complaint_code':code}
    def recover_complaint(self,p):
        from belive.complaint_mail import address,configured,send_code
        require(configured(),'Email recovery is currently unavailable. Contact the complaint team.')
        email=address(p.get('email',''))
        case_id=str(p.get('reference','')).strip().upper()
        require(bool(email) and bool(re.fullmatch(r'BL-[A-F0-9]{10}',case_id)),'Enter your email and complaint reference')
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try: item=self.store.get(db,'complaint_recovery',case_id)
            except ValueError: return
            if not item.get('verified') or not hmac.compare_digest(item['email_hash'],digest(email)) or item['retry_after']>now():
                return
            code=self._complaint_code(db,case_id)
            try: self._portal_scope(db,code)
            except ValueError: return
            item['retry_after']=due(5)
            self.store.put(db,'complaint_recovery',item)
        send_code(email,code)

    def verify_recovery_email(self,token,p):
        from belive.complaint_mail import address,configured,send_verification
        require(configured(),'Email verification is unavailable until BeLive configures email delivery')
        email=address(p.get('email',''))
        require(bool(email),'Enter the recovery email used at submission')
        with self.lock,self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            scope=self._portal_scope(db,token)
            require(bool(scope.get('case_id')),'Use your Complaint Code to verify recovery email')
            item=self.store.get(db,'complaint_recovery',scope['case_id'])
            require(hmac.compare_digest(item['email_hash'],digest(email)),'Enter the recovery email used at submission')
            if p.get('code') is not None:
                require(item.get('verification_expires','')>now() and item.get('attempts',0)<5,'Request a new verification code')
                item['attempts']=item.get('attempts',0)+1
                valid=hmac.compare_digest(item.get('verification_hash',''),digest(str(p['code'])))
                if valid:
                    item['verified']=True
                    item.pop('verification_hash',None)
                self.store.put(db,'complaint_recovery',item)
            else:
                require(item.get('send_after','')<=now(),'Wait one minute before requesting another code')
                code=f'{secrets.randbelow(1000000):06d}'
                item.update(verification_hash=digest(code),verification_expires=due(10),send_after=due(1),attempts=0)
                self.store.put(db,'complaint_recovery',item)
        if p.get('code') is not None:
            require(valid,'Incorrect email verification code')
            return {'verified':True}
        send_verification(email,code)
        return {'sent':True}
    def portal(self,token):
        with self.store.connect() as db:
            item=self._portal_scope(db,token)
            case_id=item.get('case_id');tenant=item.get('tenant_id','')
            cases=[{k:c.get(k) for k in ('id','title','description','status','created_at')}
                   for c in self.store.all(db,'case') if self.portal_case_allowed(item,c)]
            from belive.conversations import conversation
            for case in cases:
                full=self.store.get(db,'case',case['id'])
                case['conversation']=conversation(self.store,db,full,complaint_only=not tenant)
                case['resolution_confirmed']=bool(full.get('tenant_resolution',{}).get('resolved'))
                case['informational_answer']=bool(full.get('automatic_answer') and not full.get('handoff'))
                case['automatic_pending']=bool(full['status']=='AI_PENDING' and not full.get('analysis') and (
                    automation.eligible(self.store,db,full) or (full.get('entrypoint')=='TENANT_WEBSITE'
                    and not full.get('owner') and not full.get('handoff'))))
                case['complaint_level']=complaint_level(full)
                case['ai_assistance_pending']=bool(full.get('ai_assistance_pending'))
                case['ai_draft_ready']=bool(full['status']=='HUMAN_REVIEW' and full.get('analysis') and full.get('draft'))
                case['closure_reason']=full.get('closure_reason','')
                case['staff_followup']=bool(full.get('staff_followup'))
                case['auto_close_at']=closure.deadline(full,closure.policy(self.store,db)['days']) if closure.waiting(full) else None
            if 'case_ids' in item:
                return {'tenant_id':'','cases':cases,'property_name':'BeLive complaints','unit_ref':'',
                        'demo_only':False,'access_scope':'BROWSER'}
            if case_id:
                return {'tenant_id':'','cases':cases,'property_name':'BeLive complaint','unit_ref':case_id,
                        'demo_only':False,'access_scope':'COMPLAINT'}
            record=self.store.get(db,'tenant',tenant);prop=self.store.get(db,'condo',record['condo_id'])
            return {'tenant_id':tenant,'cases':cases,'property_name':prop['name'],'unit_ref':record['unit_ref'],
                    'demo_only':bool(record.get('demo_only') and prop.get('demo_only')),'access_scope':'TENANT'}
    def portal_submit(self,token,p,key,entrypoint='TENANT_PORTAL'):
        require(entrypoint in {'TENANT_PORTAL','TENANT_WEBSITE'},'Unsupported tenant entry point')
        tenant=self.portal(token)['tenant_id']
        require(bool(tenant),'Use Make a complaint for a new request')
        return self.command('intake',{'title':p.get('title'),'description':p.get('description'),'tenant_id':tenant,'platform':'INTERNAL','entrypoint':entrypoint},key)
    def portal_update(self,token,p,key):
        require(isinstance(key,str) and 8<=len(key)<=150,'A request idempotency key is required')
        with self.lock,self.store.connect() as db:
            scope=self._portal_scope(db,token);tenant=scope.get('tenant_id','')
            c=self.store.get(db,'case',p.get('id'))
            require(self.portal_case_allowed(scope,c),'This complaint is unavailable in this browser session')
            raw_note=p.get('note')
            short_ack=(c.get('entrypoint')=='TENANT_WEBSITE' and c['status']=='FOLLOW_UP'
                       and (c.get('automatic_answer') or {}).get('id')=='PUBLIC-COMPLAINT-FAQ'
                       and isinstance(raw_note,str) and automation.acknowledgement_only(raw_note))
            note=bounded(raw_note,1 if short_ack else 8,3000)
            fingerprint=digest(json.dumps([tenant,p],sort_keys=True));old=db.execute('SELECT result FROM requests WHERE key=?',(key,)).fetchone()
            if old:
                saved=json.loads(old[0]);require(saved['fingerprint']==fingerprint,'Idempotency mismatch');return saved['result']
            from belive.conversations import post
            message=post(self.store,db,c,'TENANT',note,'update-'+key)
            from belive.reply_learning import discover
            discover(self,db,c['id'])
            if c['status']=='CLOSED':
                self.record_reopen(db,c)
                c.pop('closed_at',None);c.pop('closure_reason',None);c.pop('waiting_since',None)
                c.update(verification='',owner='',owner_id='')
                self.handoff(db,c,'Customer returned with a message after closure')
                self.store.put(db,'feedback',{'id':uid('STYLE'),'case_id':c['id'],'text':'','verdict':'REJECTED','share':False,'at':now()})
            self.store.event(db,c['id'],'TENANT_UPDATE',note)
            c['tenant_update']=note;c['revision']+=1
            public_answer=(c.get('entrypoint')=='TENANT_WEBSITE' and not c['tenant_id']
                           and c['status'] in {'FOLLOW_UP','AI_PENDING'}
                           and (c.get('automatic_answer') or {}).get('id')=='PUBLIC-COMPLAINT-FAQ'
                           and not c.get('owner') and not c.get('handoff') and not c.get('automation_paused'))
            if risk(note):c['severity']='CRITICAL';c['verification']='';self.handoff(db,c,'Tenant update contains potential safety risk')
            elif (c.get('automation_requested') or public_answer) and automation.exception_reason(note):
                self.handoff(db,c,automation.exception_reason(note))
            elif c.get('automatic_answer') and automation.unresolved(note):
                self.handoff(db,c,'Tenant says the automatic answer did not help')
            elif public_answer and automation.acknowledgement_only(note):
                c['waiting_since']=now()
                post(self.store,db,c,'SYSTEM','You’re welcome. If your question was answered, choose “This answers my question”. You can still ask for help here.','ack-'+key)
            elif public_answer:
                c.update(status='AI_PENDING',analysis=None,followup_due=None,
                         public_guidance_turn={'id':message['id'],'text':note})
            elif automation.eligible(self.store,db,c):
                c.update(status='AI_PENDING',analysis=None,followup_due=None)
            elif c.get('automatic_answer') and not c.get('handoff') and not c.get('owner'):
                self.handoff(db,c,'Customer added details after an automatic answer; staff follow-up required')
            elif c['status']=='FOLLOW_UP':
                c.update(status='IN_PROGRESS',followup_due=None,next_action='Customer replied; staff response required')
                c.pop('waiting_since',None);c.pop('tenant_resolution',None)
            self.store.put(db,'case',c)
            db.execute('INSERT INTO requests VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':{'saved':True}})))
            return {'saved':True}

    def portal_feedback(self,token,p,key):
        with self.store.connect() as db:
            scope=self._portal_scope(db,token);c=self.store.get(db,'case',p.get('id'))
            require(self.portal_case_allowed(scope,c),'This complaint is unavailable in this browser session')
            tenant=c['tenant_id']
        return self.command('tenant_feedback',{'id':p.get('id'),'resolved':p.get('resolved'),'note':p.get('note'),'tenant_id':tenant},key)
