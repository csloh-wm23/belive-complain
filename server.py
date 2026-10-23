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
from http.cookies import SimpleCookie
from belive.access import Access
from belive.backups import operation as backup_operation
from belive.service import Service
from belive.store import now
from belive.connectors import scan,deliver
from belive.workspace import DEFAULT_CONFIG,selected_database,choose_database

ROOT=Path(__file__).resolve().parent
STATIC={'/':'index.html','/index.html':'index.html','/assets/app.js':'assets/app.js',
        '/assets/style.css':'assets/style.css','/portal':'portal.html','/assets/portal.js':'assets/portal.js'}

class Tasks:
    def __init__(self,service):self.service=service;self.running=set();self.lock=threading.Lock();self.stop=threading.Event()
    def start(self,key,fn):
        with self.lock:
            if key in self.running:return False
            self.running.add(key)
        def run():
            try:fn()
            except Exception:
                with self.service.store.connect() as db:self.service.store.event(db,key,'BACKGROUND_FAILED','Operation failed; inspect case/source state')
            finally:
                with self.lock:self.running.discard(key)
        threading.Thread(target=run,daemon=True).start();return True
    def analyse(self,c):
        with self.service.store.connect() as db:c=self.service.store.get(db,'case',c['id'])
        if c['status'] in {'AI_PENDING','AWAITING_CONTACT'} and c['severity'] not in {'HIGH','CRITICAL'} and not c.get('analysis'):
            self.start('ai-'+c['id'],lambda:self.service.analyse(c['id']))
    def scan(self,source_id):
        def run():
            ids=scan(self.service,source_id)
            with self.service.store.connect() as db:cases=[self.service.store.get(db,'case',i) for i in ids]
            for c in cases:self.analyse(c)
        return self.start('source-'+source_id,run)
    def loop(self):
        while not self.stop.wait(self.service.settings.scheduler_seconds):
            try:
                self.service.tick()
                snapshot=self.service.snapshot()
                for c in snapshot['cases']:self.analyse(c)
                for source in snapshot['sources']:
                    if source['enabled'] and source['next_scan']<=now():self.scan(source['id'])
            except Exception:
                with self.service.store.connect() as db:self.service.store.event(db,'scheduler','SCHEDULER_FAILED','Tick failed; next scheduled attempt will recheck persisted state')

def make_handler(service,tasks=None):
    tasks=tasks or Tasks(service);access=Access(service);csrf=secrets.token_urlsafe(32)
    support_routes={'intake','case_action','feedback','approve_message','reject_message','analyse','deliver','tick'}
    class Handler(SimpleHTTPRequestHandler):
        extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript'}
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
        def end_headers(self):
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            super().end_headers()
        def valid_host(self):return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        def json(self,code,value,cookie=None):
            data=json.dumps(value).encode();self.send_response(code)
            if cookie is not None:self.send_header('Set-Cookie','belive_session='+cookie+'; Path=/; HttpOnly; SameSite=Strict; Max-Age='+('28800' if cookie else '0'))
            self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def token(self):return self.headers.get('Authorization','').removeprefix('Bearer ')
        def session(self):
            try:
                cookie=SimpleCookie(self.headers.get('Cookie',''));return cookie['belive_session'].value if 'belive_session' in cookie else ''
            except Exception:return ''
        def do_GET(self):
            if not self.valid_host():return self.json(403,{'error':'Local host required'})
            path=urlsplit(self.path).path
            if path=='/api/auth':return self.json(200,{'setup_required':not access.users(),'user':access.current(self.session())})
            if path=='/api/shared-memory':
                clients=json.loads(os.getenv('BELIVE_MEMORY_CLIENTS','{}'))
                if not any(isinstance(v,str) and v and hmac.compare_digest(self.token(),v) for v in clients.values()):return self.json(401,{'error':'Scoped client token required'})
                with service.store.connect() as db:items=service.styles(db,shared=True)
                return self.json(200,{'examples':[{'id':x['id'],'text':x['text'],'use':'style-only'} for x in items]})
            if path=='/api/portal':
                try:return self.json(200,service.portal(self.token()))
                except ValueError:return self.json(401,{'error':'Invalid or expired tenant access key'})
            if path.startswith('/api/'):
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf):return self.json(403,{'error':'Open the operator dashboard to access this endpoint'})
                user=access.current(self.session())
                if not user:return self.json(401,{'error':'Sign in to the operator dashboard'})
                if path=='/api/users':
                    if user['role']!='ADMIN':return self.json(403,{'error':'Administrator access required'})
                    return self.json(200,{'users':access.users()})
                if path=='/api/status':
                    snapshot=service.snapshot();snapshot.update(tasks=sorted(tasks.running),operator=user)
                    if user['role']!='ADMIN':snapshot['storage']['can_choose']=False;snapshot['backups']=[]
                    return self.json(200,snapshot)
                return self.json(404,{'error':'Unknown endpoint'})
            if path not in STATIC:return self.send_error(404)
            file=ROOT/STATIC[path]
            if not file.is_file():return self.send_error(404)
            data=file.read_bytes()
            if path in {'/','/index.html'}:data=data.replace(b'__CSRF_TOKEN__',csrf.encode())
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if file.suffix=='.html' else self.guess_type(str(file)));self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_HEAD(self):return self.send_error(405)
        def do_POST(self):
            if not self.valid_host():return self.json(403,{'error':'Local host required'})
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.json(403,{'error':'Foreign origin rejected'})
            path=urlsplit(self.path).path;route=path.removeprefix('/api/')
            portal=path in {'/api/portal/intake','/api/portal/update','/api/portal/feedback'}
            if not portal and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf):return self.json(403,{'error':'Invalid operator token'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=64000:raise ValueError('Request size must be 1–64,000 bytes')
                p=json.loads(self.rfile.read(size));key=self.headers.get('Idempotency-Key','')
                if not isinstance(p,dict):raise ValueError('JSON object required')
                if portal:
                    if path=='/api/portal/intake':
                        result=service.portal_submit(self.token(),p,key);tasks.analyse(result)
                        return self.json(200,{'id':result['id'],'status':result['status']})
                    if path=='/api/portal/feedback':return self.json(200,service.portal_feedback(self.token(),p,key))
                    return self.json(200,service.portal_update(self.token(),p,key))
                if route in {'setup','login'}:
                    if route=='setup':access.create(p,bootstrap=True)
                    session,user=access.login(p);return self.json(200,{'user':user},cookie=session)
                user=access.current(self.session())
                if not user:return self.json(401,{'error':'Sign in to the operator dashboard'})
                if route=='logout':access.logout(self.session());return self.json(200,{'signed_out':True},cookie='')
                if user['role']!='ADMIN' and route not in support_routes:return self.json(403,{'error':'Administrator access required'})
                if route=='users':return self.json(200,access.create(p))
                if route=='deactivate-user':return self.json(200,access.deactivate(p.get('id'),user['id']))
                if route=='tenant_feedback':raise ValueError('Tenant feedback requires tenant portal access')
                p={**p,'_actor':user['id']}
                if route=='case_action' and p.get('action')=='acknowledge':p['owner']=user['name']
                if route=='analyse':
                    with service.store.connect() as db:c=service.store.get(db,'case',p.get('id'))
                    if c['severity'] in {'HIGH','CRITICAL'}:raise ValueError('Safety risk requires staff handling')
                    return self.json(202,{'started':tasks.start('ai-'+c['id'],lambda:service.analyse(c['id']))})
                if route=='ai-check':return self.json(202,{'started':tasks.start('ai-connection',service.check_ai)})
                if route=='scan':return self.json(202,{'started':tasks.scan(p.get('id'))})
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
    with ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(service,tasks)) as server:
        thread=threading.Thread(target=tasks.loop,daemon=True);thread.start()
        url=f'http://127.0.0.1:{args.port}';print('BeLive tenant support: '+url,flush=True)
        print('Database: '+str(service.store.path.resolve()),flush=True)
        print('Keep this window open. Press Ctrl+C once to stop.',flush=True)
        if not args.no_browser:threading.Timer(.4,lambda:webbrowser.open(url)).start()
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:tasks.stop.set();thread.join(2)

if __name__=='__main__':main()
