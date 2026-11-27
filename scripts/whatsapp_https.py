"""Dedicated public surface: Embedded Signup and signed WhatsApp webhooks only."""
import argparse
import http.client
import json
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from belive import meta_signup as meta
from types import SimpleNamespace
from belive.store import Store
from belive.workspace import selected_database
from belive.store import now

def handler(service,main_port=8877):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # Never log authorisation codes, cookies or tokens.
        def record_webhook_receipt(self,code,count,raw):
            if self.command!='POST':return
            # Keep routing diagnostics, never message content, sender IDs or signatures.
            fields=[];messages=0
            if code==200:
                try:
                    payload=json.loads(raw or b'{}')
                    for entry in payload.get('entry',[]):
                        for change in entry.get('changes',[]):
                            field=change.get('field')
                            if field in {'messages','smb_message_echoes','history','smb_app_state_sync','account_update','standby','messaging_handovers'}:fields.append(field)
                            messages+=len(change.get('value',{}).get('messages',[]))
                except (ValueError,TypeError,AttributeError):pass
            try:
                with service.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    previous=next(iter(service.store.all(db,'wa_webhook_receipt')),{'count':0})
                    service.store.put(db,'wa_webhook_receipt',{'id':'latest','count':previous['count']+1,'at':now(),'http_status':code,'bytes':count,'fields':sorted(set(fields)),'message_count':messages})
            except Exception:pass  # Diagnostics must not change the webhook acknowledgement.
        def send(self,code,body,kind='application/json',cookie=None):
            raw=body.encode() if isinstance(body,str) else json.dumps(body).encode()
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self' https://connect.facebook.net; style-src 'self'; connect-src 'self' https://*.facebook.com; frame-src https://www.facebook.com https://web.facebook.com; img-src 'self' data: https://*.facebook.com; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            if cookie:self.send_header('Set-Cookie','belive_meta='+cookie+'; Path=/connect; Secure; HttpOnly; SameSite=Strict; Max-Age=1800')
            self.end_headers();self.wfile.write(raw)
        def valid_host(self):
            try:return self.headers.get('Host')==urlsplit(meta.origin()).netloc
            except ValueError:return False
        def cookie(self):
            try:return SimpleCookie(self.headers.get('Cookie',''))['belive_meta'].value
            except Exception:return ''
        def proxy(self):
            try:
                count=int(self.headers.get('Content-Length','0'))
                if not 0<=count<=2_000_000:return self.send(413,{'error':'Webhook too large'})
                raw=self.rfile.read(count) if count else None
                c=http.client.HTTPConnection('127.0.0.1',main_port,timeout=25)
                c.request(self.command,self.path,body=raw,headers={'Content-Type':self.headers.get('Content-Type','application/json'),'X-Hub-Signature-256':self.headers.get('X-Hub-Signature-256','')})
                r=c.getresponse();data=r.read(1_000_001);code=r.status;kind=r.getheader('Content-Type','application/json');c.close()
                self.record_webhook_receipt(code,count,raw)
                if len(data)>1_000_000:return self.send(502,{'error':'Invalid webhook response'})
                return self.send(code,data.decode('utf-8'),kind)
            except Exception:return self.send(503,{'error':'Local WhatsApp service unavailable'})
        def do_GET(self):
            if self.path=='/startup-health' and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}':
                return self.send(200,{'service':'belive-whatsapp-gateway','protocol':1})
            if not self.valid_host():return self.send(403,{'error':'Host not allowed'})
            path=urlsplit(self.path).path
            if path=='/webhooks/whatsapp':return self.proxy()
            if path=='/connect/whatsapp':return self.send(200,(ROOT/'meta-signup.html').read_text(encoding='utf-8'),'text/html; charset=utf-8')
            if path=='/connect/signup.js':return self.send(200,(ROOT/'assets/meta-signup.js').read_text(encoding='utf-8'),'text/javascript; charset=utf-8')
            if path=='/connect/style.css':return self.send(200,'body{font:17px system-ui;background:#f4f7f5;color:#183d34;padding:24px}main{max-width:640px;margin:6vh auto;background:white;padding:32px;border-radius:16px}button{padding:14px;margin:8px;background:#176e57;color:white;border:0;border-radius:7px}button:disabled{opacity:.45}','text/css')
            if path=='/connect/init':
                try:
                    row=meta.session(service,self.cookie());c=meta.config();ready=bool(c['app_secret'] and c['graph_version'])
                    return self.send(200,{'csrf':row['csrf'],'app_id':c['app_id'],'config_id':c['config_id'],'graph_version':c['graph_version'],'ready':ready,'connected':row['status']=='COMPLETE','reason':'Add the current Meta App Secret to the local .env, then reopen this page.' if not ready else ''})
                except ValueError as e:return self.send(403,{'error':str(e)})
            return self.send(404,{'error':'Not found'})
        def do_POST(self):
            if not self.valid_host():return self.send(403,{'error':'Host not allowed'})
            if urlsplit(self.path).path=='/webhooks/whatsapp':return self.proxy()
            if self.headers.get('Origin')!=meta.origin():return self.send(403,{'error':'Origin not allowed'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16000:return self.send(413,{'error':'Request too large'})
                p=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
                if not isinstance(p,dict):raise ValueError('JSON object required')
                if path=='/connect/session':
                    cookie,_=meta.consume_ticket(service,p.get('ticket',''));return self.send(200,{'accepted':True},cookie=cookie)
                row=meta.session(service,self.cookie(),self.headers.get('X-Setup-CSRF',''))
                if path=='/connect/exchange':return self.send(200,meta.exchange(service,row,p.get('code')))
                if path=='/connect/complete':return self.send(200,meta.complete(service,row,p.get('waba_id',''),p.get('phone_id','')))
                return self.send(404,{'error':'Not found'})
            except ValueError as e:return self.send(400,{'error':str(e)})
            except Exception:return self.send(502,{'error':'Meta did not complete this request. Check app permissions and onboarding status; no credentials are displayed.'})
    return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8878);a=p.parse_args()
    ThreadingHTTPServer(('127.0.0.1',a.port),handler(SimpleNamespace(store=Store(selected_database())))).serve_forever()
