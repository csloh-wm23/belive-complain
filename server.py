"""Independent localhost BeLive tenant-support server with SQLite and native Hermes."""
import argparse
import hmac
import json
import os
import secrets
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from http.cookies import CookieError,SimpleCookie
from belive.access import Access
from belive.credentials import credential_scope
from belive.backups import operation as backup_operation
from belive.service import Service
from belive.store import now
from belive.connectors import scan,deliver
from belive.workspace import DEFAULT_CONFIG,selected_database,choose_database

ROOT=Path(__file__).resolve().parent
STATIC={'/':'index.html','/index.html':'index.html','/assets/app.js':'assets/app.js',
        '/assets/style.css':'assets/style.css','/portal':'portal.html','/assets/portal.js':'assets/portal.js',
        '/belive':'tenant-site.html','/assets/tenant-site.css':'assets/tenant-site.css',
        '/assets/tenant-home.svg':'assets/tenant-home.svg','/assets/tenant-site.js':'assets/tenant-site.js'}

STATIC['/assets/learning-ui.js']='assets/learning-ui.js'
STATIC['/assets/whatsapp-ui.js']='assets/whatsapp-ui.js'
STATIC['/assets/whatsapp-staff-ui.js']='assets/whatsapp-staff-ui.js'
STATIC['/assets/shared-memory-ui.js']='assets/shared-memory-ui.js'
STATIC['/assets/credential-settings-ui.js']='assets/credential-settings-ui.js'
STATIC['/assets/fyp.css']='assets/fyp.css'
STATIC['/assets/workspace-v2.css']='assets/workspace-v2.css'
STATIC['/assets/workspace-v2.js']='assets/workspace-v2.js'
STATIC['/assets/property-directory.json']='assets/property-directory.json'

class Tasks:
    def __init__(self,service):self.service=service;self.running=set();self.lock=threading.Lock();self.stop=threading.Event()
    def start(self,key,fn):
        with self.lock:
            if key in self.running:return False
            self.running.add(key)
        def run():
            try:
                with credential_scope(self.service.store.path):fn()
            except Exception:
                with self.service.store.connect() as db:self.service.store.event(db,key,'BACKGROUND_FAILED','Operation failed; inspect case/source state')
            finally:
                with self.lock:self.running.discard(key)
        threading.Thread(target=run,daemon=True).start();return True
    def analyse(self,c):
        with self.service.store.connect() as db:c=self.service.store.get(db,'case',c['id'])
        if c.get('entrypoint')=='WHATSAPP':return
        pending=c['status'] in {'AI_PENDING','AWAITING_CONTACT'} or (c['status']=='HUMAN_REVIEW' and c.get('ai_assistance_pending'))
        if pending and c['severity'] not in {'HIGH','CRITICAL'} and not c.get('analysis'):
            self.start('ai-'+c['id'],lambda:self.service.analyse(c['id']))
    def analyse_batch(self, cases):
        with self.lock:
            keys = ['ai-'+c['id'] for c in cases if c['status']=='AWAITING_CONTACT'
                    and 'ai-'+c['id'] not in self.running]
            self.running.update(keys)
        if not keys:
            return

        def run():
            remaining = set(keys)
            try:
                for key in keys:
                    if self.stop.is_set():
                        break
                    try:
                        self.service.analyse(key.removeprefix('ai-'))
                    except Exception:
                        with self.service.store.connect() as db:
                            self.service.store.event(db,key,'BACKGROUND_FAILED','Review assessment did not complete')
                    finally:
                        with self.lock:
                            self.running.discard(key)
                            remaining.discard(key)
            finally:
                with self.lock:
                    self.running.difference_update(remaining)

        threading.Thread(target=run,daemon=True).start()

    def learning(self,run_id):
        from belive.learning import execute
        return self.start('learning-'+run_id,lambda:execute(self.service,run_id))
    def reply_feedback(self,item_id):
        from belive.reply_learning import execute
        def run():
            execute(self.service,item_id);self.memory_pending()
        return self.start('reply-feedback-'+item_id,run)
    def memory_pending(self):
        from belive import shared_memory
        with self.service.store.connect() as db:active=shared_memory.enabled(self.service,db)
        if active:return self.start('shared-memory-sync',lambda:shared_memory.sync(self.service))
    def pending_reply_feedback(self,case_id=None):
        if not hasattr(self.service.ai,'reply_improvement'):return
        with self.service.store.connect() as db:
            pending=[x for x in self.service.store.all(db,'reply_learning')
                     if (not case_id or x['case_id']==case_id) and (x['status'] in {'PENDING','APPROVAL_QUEUED'} or x.get('preview_status')=='QUEUED')]
        for item in pending[:1]:self.reply_feedback(item['id'])
    def scan(self,source_id):
        def run():
            ids=scan(self.service,source_id)
            with self.service.store.connect() as db:cases=[self.service.store.get(db,'case',i) for i in ids]
            for c in cases:self.analyse(c)
        return self.start('source-'+source_id,run)
    def loop(self):
        with credential_scope(self.service.store.path):self._loop()
    def _loop(self):
        while not self.stop.wait(self.service.settings.scheduler_seconds):
            try:
                self.service.tick()
                self.memory_pending()
                self.whatsapp_pending()
                self.pending_reply_feedback()
                snapshot=self.service.snapshot()
                for c in snapshot['cases']:self.analyse(c)
                for source in snapshot['sources']:
                    if source['enabled'] and source['next_scan']<=now():self.scan(source['id'])
            except Exception:
                with self.service.store.connect() as db:self.service.store.event(db,'scheduler','SCHEDULER_FAILED','Tick failed; next scheduled attempt will recheck persisted state')

    def whatsapp_pending(self):
        from belive.whatsapp import process_thread,deliver
        with self.service.store.connect() as db:
            tids={x['thread_id'] for x in self.service.store.all(db,'wa_turn') if x['status']=='PENDING'}
            outgoing=[x for x in self.service.store.all(db,'wa_outgoing') if x['status']=='QUEUED']
        for tid in list(tids)[:4]:self.start('whatsapp-'+tid,lambda tid=tid:process_thread(self.service,tid))
        for item in outgoing[:4]:self.start('wa-send-'+item['id'],lambda key=item['id']:deliver(self.service,key))

def make_handler(service,tasks=None):
    from belive.credentials import apply as apply_credentials
    apply_credentials(service)
    tasks=tasks or Tasks(service);access=Access(service);csrf=secrets.token_urlsafe(32)
    support_routes={'scan-all','import-review','import-review-batch','public-preview','lesson_revoke','learning_start','learning_improve','intake','case_action','feedback','approve_message','reject_message','analyse','deliver','tick'}
    support_routes.add('google-reply')
    support_routes.update({'reply_learning_scan','reply_learning_action'})
    support_routes.update({'wa_simulate','wa_staff_reply','wa_staff_complete','wa_property'})
    class Handler(SimpleHTTPRequestHandler):
        def handle_one_request(self):
            with credential_scope(service.store.path):return super().handle_one_request()
        extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript'}
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
        def end_headers(self):
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            super().end_headers()
        def valid_host(self):return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        def json(self,code,value,cookie=None,browser_cookie=None):
            data=json.dumps(value).encode();self.send_response(code)
            if cookie is not None:self.send_header('Set-Cookie','belive_session='+cookie+'; Path=/; HttpOnly; SameSite=Strict; Max-Age='+('28800' if cookie else '0'))
            if browser_cookie is not None:self.set_browser_cookie(browser_cookie)
            self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass  # The browser may navigate away during polling.
        def token(self):return self.headers.get('Authorization','').removeprefix('Bearer ')
        def _cookie(self, name):
            try:
                cookies=SimpleCookie(self.headers.get('Cookie',''))
                return cookies[name].value if name in cookies else ''
            except (CookieError, ValueError):
                return ''
        def session(self):return self._cookie('belive_session')
        def portal_token(self):return self.token() or self._cookie('belive_complaints')
        def set_browser_cookie(self, token):
            self.send_header('Set-Cookie','belive_complaints='+token+'; Path=/; HttpOnly; SameSite=Strict; Max-Age=15552000')
        def do_GET(self):
            if urlsplit(self.path).path=='/webhooks/whatsapp':
                from belive.whatsapp import challenge,configuration
                if not self.valid_host() and self.headers.get('Host')!=configuration()['webhook_host']:return self.json(403,{'error':'Webhook host not configured'})
                try:
                    data=challenge(urlsplit(self.path).query).encode();self.send_response(200);self.send_header('Content-Type','text/plain');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
                except ValueError:return self.json(403,{'error':'Webhook verification failed'})
            if not self.valid_host():return self.json(403,{'error':'Local host required'})
            path=urlsplit(self.path).path
            if path=='/startup-health':
                import hashlib
                return self.json(200,{'service':'belive','protocol':1,'database':hashlib.sha256(str(service.store.path.resolve()).casefold().encode()).hexdigest()})
            if path=='/support/whatsapp':
                from belive.whatsapp_channel import public
                with service.store.connect() as db:channel=public(service,db)
                if not channel['available']:return self.json(503,{'error':'The company WhatsApp number has not been configured. Please use the website complaint form.'})
                self.send_response(302);self.send_header('Location',channel['chat_url']);self.send_header('Cache-Control','no-store');self.end_headers();return
            if path=='/api/auth':return self.json(200,{'setup_required':not access.users(),'user':access.current(self.session()),'csrf_token':csrf})
            if path=='/api/support-channel':
                from belive.whatsapp_channel import public
                with service.store.connect() as db:return self.json(200,public(service,db))
            if path=='/api/demo':
                from belive.demo import info
                with service.store.connect() as db:result=info(service,db)
                return self.json(200,result)
            if path=='/api/shared-memory':
                clients=json.loads(os.getenv('BELIVE_MEMORY_CLIENTS','{}'))
                if not any(isinstance(v,str) and v and hmac.compare_digest(self.token(),v) for v in clients.values()):return self.json(401,{'error':'Scoped client token required'})
                with service.store.connect() as db:items=service.styles(db,shared=True)
                return self.json(200,{'examples':[{'id':x['id'],'text':x['text'],'use':'style-only'} for x in items]})
            if path=='/api/portal':
                try:return self.json(200,service.portal(self.portal_token()))
                except ValueError:return self.json(401,{'error':'This browser has no active complaint session'})
            if path.startswith('/api/'):
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf):return self.json(403,{'error':'Open the operator dashboard to access this endpoint','code':'STALE_CSRF'})
                user=access.current(self.session())
                if not user:return self.json(401,{'error':'Sign in to the operator dashboard'})
                if path=='/api/credential-settings':
                    if user['role']!='ADMIN':return self.json(403,{'error':'Administrator access required'})
                    from belive.credentials import status as credential_status
                    return self.json(200,credential_status(service.store.path))
                if path=='/api/users':
                    if user['role']!='ADMIN':return self.json(403,{'error':'Administrator access required'})
                    return self.json(200,{'users':access.users()})
                if path.startswith('/api/wa-photo/'):
                    from belive.whatsapp import media_path
                    try:
                        with service.store.connect() as db:message=service.store.get(db,'wa_message',path.rsplit('/',1)[-1])
                        data=media_path(service,message).read_bytes();self.send_response(200);self.send_header('Content-Type',message['media']['mime']);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
                    except (ValueError,FileNotFoundError):return self.json(404,{'error':'Photo not available'})
                if path.startswith('/api/wa-document/'):
                    from belive.company_sop import document_path
                    try:
                        with service.store.connect() as db:document=service.store.get(db,'sop_document',path.rsplit('/',1)[-1])
                        content=document_path(service,document).read_bytes()
                        self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition','attachment; filename="company-support-reference.pdf"');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content);return
                    except (ValueError,FileNotFoundError):return self.json(404,{'error':'Document not available'})
                if path=='/api/status':
                    with tasks.lock:active_tasks=sorted(tasks.running)
                    snapshot=service.snapshot();snapshot.update(tasks=active_tasks,operator=user)
                    if user['role']!='ADMIN':snapshot['storage']['can_choose']=False;snapshot['backups']=[]
                    return self.json(200,snapshot)
                return self.json(404,{'error':'Unknown endpoint'})
            if path not in STATIC:return self.send_error(404)
            file=ROOT/STATIC[path]
            if not file.is_file():return self.send_error(404)
            data=file.read_bytes()
            if path in {'/','/index.html'}:data=data.replace(b'__CSRF_TOKEN__',csrf.encode())
            self.send_response(200)
            if path=='/portal':
                browser_token=service.browser_session(self._cookie('belive_complaints'))
                self.set_browser_cookie(browser_token)
            if path in {'/','/index.html','/assets/learning-ui.js'}:self.send_header('Cache-Control','no-store')
            self.send_header('Content-Type','text/html; charset=utf-8' if file.suffix=='.html' else self.guess_type(str(file)))
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_HEAD(self):return self.send_error(405)
        def do_POST(self):
            if urlsplit(self.path).path=='/webhooks/whatsapp':
                from belive.whatsapp import webhook,configuration
                if not self.valid_host() and self.headers.get('Host')!=configuration()['webhook_host']:return self.json(403,{'error':'Webhook host not configured'})
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=2000000:return self.json(413,{'error':'Webhook too large'})
                    webhook(service,self.rfile.read(size),self.headers.get('X-Hub-Signature-256',''));tasks.whatsapp_pending()
                    return self.json(200,{'received':True})
                except PermissionError:return self.json(403,{'error':'Invalid webhook signature'})
                except (ValueError,TypeError,KeyError) as exc:
                    import traceback
                    frames=traceback.extract_tb(exc.__traceback__)[-6:]
                    with service.store.connect() as db:
                        service.store.put(db,'wa_webhook_error',{'id':'latest','at':now(),'error_type':type(exc).__name__,
                            'locations':[Path(f.filename).name+':'+str(f.lineno)+':'+f.name for f in frames]})
                    return self.json(400,{'error':'Invalid WhatsApp payload'})
            if not self.valid_host():return self.json(403,{'error':'Local host required'})
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.json(403,{'error':'Foreign origin rejected'})
            path=urlsplit(self.path).path;route=path.removeprefix('/api/')
            website=path=='/api/website/complaints'
            portal=website or path in {'/api/demo/session','/api/portal/intake','/api/portal/update','/api/portal/feedback','/api/website/complaint-recovery','/api/portal/verify-email'}
            if not portal and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf):return self.json(403,{'error':'Invalid operator token','code':'STALE_CSRF'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=(8000000 if route=='wa_simulate' else 64000):raise ValueError('Request too large')
                p=json.loads(self.rfile.read(size));key=self.headers.get('Idempotency-Key','')
                if not isinstance(p,dict):raise ValueError('JSON object required')
                if portal:
                    if path=='/api/portal/verify-email':
                        return self.json(200,service.verify_recovery_email(self.token(),p))
                    if path=='/api/website/complaint-recovery':
                        service.recover_complaint(p)
                        return self.json(200,{'accepted':True})
                    if path=='/api/demo/session':
                        if not isinstance(key,str) or not 8<=len(key)<=150:raise ValueError('A request idempotency key is required')
                        from belive.demo import session
                        return self.json(200,session(service))
                    if website:
                        browser_token=service.browser_session(self._cookie('belive_complaints'))
                        result=service.website_submit(p,key,browser_token=browser_token)
                        tasks.analyse(result)
                        return self.json(200,result,browser_cookie=browser_token)
                    if path=='/api/portal/intake':
                        result=service.portal_submit(self.portal_token(),p,key);tasks.analyse(result)
                        return self.json(200,{'id':result['id'],'status':result['status']})
                    if path=='/api/portal/feedback':
                        result=service.portal_feedback(self.portal_token(),p,key)
                        tasks.pending_reply_feedback(p['id'])
                        return self.json(200,result)
                    result=service.portal_update(self.portal_token(),p,key)
                    tasks.pending_reply_feedback(p['id'])
                    tasks.analyse({'id':p['id']})
                    return self.json(200,result)
                if route in {'setup','login'}:
                    if route=='setup':access.create(p,bootstrap=True)
                    session,user=access.login(p);return self.json(200,{'user':user},cookie=session)
                user=access.current(self.session())
                if not user:return self.json(401,{'error':'Sign in to the operator dashboard'})
                if route=='logout':access.logout(self.session());return self.json(200,{'signed_out':True},cookie='')
                if user['role']!='ADMIN' and route not in support_routes:return self.json(403,{'error':'Administrator access required'})
                if route=='credential-settings':
                    from belive.credentials import save as save_credentials
                    with tasks.lock:
                        if tasks.running:raise ValueError('Wait for active AI, collection or delivery work to finish before changing connection settings.')
                        result=save_credentials(service,p,user['id'])
                    return self.json(200,result)
                if route=='users':return self.json(200,access.create(p))
                if route=='deactivate-user':return self.json(200,access.deactivate(p.get('id'),user['id']))
                if route in {'portal_issue','portal_revoke'}:return self.json(404,{'error':'This access action has been retired'})
                if route=='tenant_feedback':raise ValueError('Tenant feedback requires tenant portal access')
                p={**p,'_actor':user['id']}
                if route=='source' and p.get('platform')=='THREADS' and p.get('resource')=='me/threads':
                    from belive.connectors import resolve_threads_account
                    with credential_scope(service.store.path):p=resolve_threads_account(p)
                    with service.store.connect() as db:
                        existing=next((s for s in service.store.all(db,'source')
                                       if s['platform']=='THREADS' and s['resource']==p['resource']),None)
                    from belive.store import digest
                    p['id']=existing['id'] if existing else 'SRC-threads-'+digest(p['resource'])[:12]
                if route.startswith('shared-memory-'):
                    from belive import shared_memory
                    if route=='shared-memory-import-key':
                        from belive.repository_memory import import_key
                        return self.json(200,import_key(service,p.get('key','')))
                    if route=='shared-memory-host':return self.json(200,shared_memory.setup_host(service))
                    if route=='shared-memory-connect':return self.json(200,shared_memory.configure(service,p))
                    if route=='shared-memory-sync':return self.json(200,shared_memory.sync(service))
                    if route=='shared-memory-pairing':return self.json(200,shared_memory.pairing(service,p.get('url','')))
                    if route=='shared-memory-resolve':return self.json(200,shared_memory.resolve(service,p))
                    if route=='shared-memory-action':return self.json(200,shared_memory.change(service,p))
                    if route=='shared-memory-network':return self.json(200,shared_memory.network_status())
                    if route=='shared-memory-private-serve':return self.json(200,shared_memory.enable_private_service(service))
                    raise ValueError('Unknown shared memory action')
                if route in {'wa_simulate','wa_knowledge','wa_staff_reply','wa_staff_complete','wa_property','wa_document_action'}:
                    result=service.command(route,p,key);tasks.memory_pending();tasks.whatsapp_pending();return self.json(200,result)
                if route=='wa-signup-start':
                    from belive.meta_signup import new_link
                    return self.json(200,new_link(service))
                if route in {'learning_start','learning_improve'}:
                    result=service.command(route,p,key);tasks.learning(result['id'])
                    return self.json(200,result)
                if route in {'reply_learning_scan','reply_learning_action'}:
                    result=service.command(route,p,key)
                    if route=='reply_learning_action':tasks.reply_feedback(result['id'])
                    else:tasks.pending_reply_feedback()
                    return self.json(200,result)
                if route=='case_action' and p.get('action')=='acknowledge':p['owner']=user['name']
                if route=='import-review':
                    from belive.browser_reviews import read_browser_review
                    review=read_browser_review(p.get('url'))
                    case,created=service.import_browser_review(review,user['id'])
                    if created:tasks.analyse(case)
                    return self.json(200,{'id':case['id'],'created':created})
                if route=='review-chrome-sign-in':
                    from belive.browser_reviews import open_review_chrome_sign_in
                    open_review_chrome_sign_in()
                    return self.json(200,{'opened':True})
                if route=='import-review-batch':
                    from belive.browser_reviews import BATCH_LIMIT, read_browser_review_batch
                    reviews, skipped = read_browser_review_batch(p.get('links'))
                    created, duplicates = [], []
                    for review in reviews[:BATCH_LIMIT]:
                        case, is_new = service.import_browser_review(review,user['id'])
                        (created if is_new else duplicates).append(case)
                    tasks.analyse_batch(created)
                    return self.json(200,{'created':[c['id'] for c in created],
                                          'duplicates':[c['id'] for c in duplicates],'skipped':skipped})
                if route=='google-reply':
                    from belive.google_replies import publish
                    return self.json(200,publish(service,p,user['id'],key))
                if route=='public-preview':
                    return self.json(200,service.prepare_public_preview(p.get('id'),p.get('revision'),user['id']))
                if route=='analyse':
                    with service.store.connect() as db:c=service.store.get(db,'case',p.get('id'))
                    if c['severity'] in {'HIGH','CRITICAL'}:raise ValueError('Safety risk requires staff handling')
                    return self.json(202,{'started':tasks.start('ai-'+c['id'],lambda:service.analyse(c['id']))})
                if route=='ai-check':return self.json(202,{'started':tasks.start('ai-connection',service.check_ai)})
                if route=='scan':return self.json(202,{'started':tasks.scan(p.get('id'))})
                if route=='scan-all':
                    with service.store.connect() as db:
                        sources=[source for source in service.store.all(db,'source') if source['enabled']]
                    if not sources:raise ValueError('Add and enable at least one authorised platform source first')
                    started=sum(tasks.scan(source['id']) for source in sources)
                    return self.json(202,{'started':started,'already_running':len(sources)-started})
                if route=='deliver':return self.json(200,deliver(service,p.get('id')))
                if route in {'backup','restore'}:return self.json(200,backup_operation(service,route,p,key))
                if route=='memory-sync':
                    with service.store.connect() as db:examples=service.styles(db)
                    return self.json(200,{'entries':service.ai.sync(examples)['entries']})
                if route=='select-database':
                    if not 8<=len(key)<=150:raise ValueError('A request idempotency key is required')
                    if service.workspace_config is None:raise ValueError('Database selection is not available in this session')
                    chosen=choose_database(service.store.path.resolve())
                    if chosen is None:return self.json(200,{'cancelled':True})
                    return self.json(200,service.command('database_location',{'path':str(chosen),'_actor':user['id']},key))
                if route=='tick':service.tick();return self.json(200,{'checked':True})
                result=service.command(route,p,key)
                tasks.memory_pending()
                if route=='intake':tasks.analyse(result)
                return self.json(200,result)
            except (ValueError,TypeError,KeyError) as exc:return self.json(400,{'error':str(exc)[:300]})
            except Exception:return self.json(500,{'error':'OPERATION_FAILED: no success confirmed; inspect activity and configuration'})
        def log_message(self,*args):pass
    return Handler

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8877)
    parser.add_argument('--database',type=Path,default=None);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Port must be 1024–65535')
    database=args.database or selected_database()
    service=Service(database,workspace_config=DEFAULT_CONFIG);tasks=Tasks(service)
    from belive.repository_memory import startup as restore_repository_memory
    restore_repository_memory(service)
    from belive import shared_memory
    shared_memory.start_host(service);tasks.memory_pending()
    with ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(service,tasks)) as server:
        thread=threading.Thread(target=tasks.loop,daemon=True);thread.start()
        url=f'http://127.0.0.1:{args.port}';print('BeLive tenant support: '+url,flush=True)
        print('Database: '+str(service.store.path.resolve()),flush=True)
        print('Keep this window open. Press Ctrl+C once to stop.',flush=True)
        if not args.no_browser:threading.Timer(.4,lambda:webbrowser.open(url)).start()
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:
            tasks.stop.set();thread.join(2)
            if getattr(service,'memory_hub',None):service.memory_hub.shutdown();service.memory_hub.server_close()

if __name__=='__main__':main()
