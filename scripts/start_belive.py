"""One local supervisor: BeLive, bounded HTTPS gateway and account-only Meta callback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,build_opener
import webbrowser

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from belive import meta_signup as meta
from belive.connectors import NoRedirect
from belive.credentials import credential_scope
from belive.hermes_native import native_request
from belive.launch_status import PATH
from belive.settings import load_env,load_settings
from belive.store import now
from belive.whatsapp import configuration
from belive.whatsapp_channel import phone
from belive.workspace import selected_database

ERRORS={
 'BACKEND':'BeLive could not start. Close any other app using port 8877, then double-click the launcher again.',
 'GATEWAY':'The WhatsApp HTTPS gateway could not start. Check port 8878 and try again.',
 'CLOUDFLARED':'Cloudflare Tunnel is missing. Install cloudflared or place its official executable in output/tools/cloudflared.exe.',
 'TUNNEL':'HTTPS could not connect. Check the Internet connection; this window will retry automatically.',
 'CREDENTIALS':'WhatsApp access is incomplete or locked. Check the saved company connection settings; do not register the number again.',
 'META':'Meta did not confirm this company number, App or callback. Check the saved company access and permissions; this window will retry.',
 'HERMES':'Official Hermes could not be verified. Run Install Hermes Agent.bat and check AI connection settings.',
}

class StartupError(Exception):pass

def http(url,headers=None):
    # Never follow a redirect carrying a verification token.
    with build_opener(NoRedirect()).open(Request(url,headers=headers or {}),timeout=12) as response:
        return response.read(200000).decode('utf-8')

def occupied(port):
    with socket.socket() as sock:
        sock.settimeout(.5);return sock.connect_ex(('127.0.0.1',port))==0

def backend_ok(database):
    try:
        row=json.loads(http('http://127.0.0.1:8877/startup-health'))
        return row=={'service':'belive','protocol':1,'database':hashlib.sha256(str(database.resolve()).casefold().encode()).hexdigest()}
    except Exception:return False

def gateway_ok():
    try:return json.loads(http('http://127.0.0.1:8878/startup-health'))=={'service':'belive-whatsapp-gateway','protocol':1}
    except Exception:return False

def challenge(origin,verify):
    expected=secrets.token_hex(16)
    return http(origin+'/webhooks/whatsapp?'+urlencode({'hub.mode':'subscribe','hub.verify_token':verify,'hub.challenge':expected}))==expected

def company_number(database):
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute("SELECT body FROM objects WHERE kind='wa_channel' AND id='company'").fetchone()
    return json.loads(row[0]).get('public_number','') if row else ''

def update_meta(database,origin):
    """Verify the existing company and App, update only its phone/WABA overrides."""
    with credential_scope(database):c=configuration()
    config=meta.config();saved=meta.read_json(meta.CREDENTIALS)
    if not all(c.get(k) for k in ('access_token','verify_token','phone_number_id')) or not config['app_id'] or not config['app_secret'] or not re.fullmatch(r'\d{5,30}',saved.get('waba_id','')):
        raise StartupError('CREDENTIALS')
    token=c['access_token'];waba=saved['waba_id']
    details=meta.graph('debug_token',config['app_id']+'|'+config['app_secret'],params={'input_token':token}).get('data',{})
    if not details.get('is_valid') or str(details.get('app_id'))!=config['app_id'] or not {'whatsapp_business_management','whatsapp_business_messaging'}.issubset(details.get('scopes',[])):
        raise StartupError('META')
    number=company_number(database)
    numbers=meta.graph(waba+'/phone_numbers',token,params={'fields':'id,display_phone_number,is_on_biz_app,platform_type'}).get('data',[])
    match=next((x for x in numbers if x.get('id')==c['phone_number_id'] and phone(x.get('display_phone_number',''))==number),None)
    if not number or not match or match.get('is_on_biz_app') is not True or match.get('platform_type')!='CLOUD_API':raise StartupError('META')
    subscriptions=meta.graph(waba+'/subscribed_apps',token).get('data',[])
    if not any(str(x.get('whatsapp_business_api_data',{}).get('id'))==config['app_id'] for x in subscriptions):raise StartupError('META')
    callback={'override_callback_uri':origin+'/webhooks/whatsapp','verify_token':c['verify_token']}
    if not meta.graph(c['phone_number_id'],token,payload={'webhook_configuration':callback}).get('success'):raise StartupError('META')
    if not meta.graph(waba+'/subscribed_apps',token,payload=callback).get('success'):raise StartupError('META')
    # A successful save is not proof a customer message was delivered.
    return True

class Supervisor:
    def __init__(self,database,*,new_tunnel=False):
        self.database=database;self.started=now();self.children={};self.logs=[];self.new_tunnel=new_tunnel
        self.checks={key:False for key in ('backend','hermes','https','meta')};self.base='';self.last_detail=''

    def status(self,state,detail):
        meta.private_write(PATH,{'state':state,'detail':detail,'checks':self.checks,'started_at':self.started,'updated_at':now(),'pid':os.getpid()})
        if detail!=self.last_detail:print(detail,flush=True);self.last_detail=detail

    def spawn(self,name,command):
        previous=self.children.get(name)
        if previous and previous.poll() is None:previous.terminate();previous.wait(timeout=8)
        folder=ROOT/'data'/'launcher';folder.mkdir(parents=True,exist_ok=True)
        log=open(folder/(name+'.log'),'w',encoding='utf-8');self.logs.append(log)
        child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.children[name]=child;return child

    def ensure_local(self):
        for name,port,probe,command,code in [
            ('backend',8877,lambda:backend_ok(self.database),[sys.executable,str(ROOT/'server.py'),'--no-browser','--database',str(self.database)],'BACKEND'),
            ('gateway',8878,gateway_ok,[sys.executable,str(ROOT/'scripts/whatsapp_https.py')],'GATEWAY')]:
            if not probe():
                if occupied(port):raise StartupError(code)
                self.status('STARTING','Starting '+name+'…');child=self.spawn(name,command)
                deadline=time.monotonic()+30
                while time.monotonic()<deadline and child.poll() is None:
                    if probe():break
                    time.sleep(.3)
                else:raise StartupError(code)
            if name=='backend':self.checks['backend']=True

    def ensure_tunnel(self):
        with credential_scope(self.database):verify=configuration()['verify_token']
        if not verify:raise StartupError('CREDENTIALS')
        if not self.new_tunnel:
            try:
                base=meta.origin()
                if challenge(base,verify):self.base=base;self.checks['https']=True;return
            except Exception:pass
        self.new_tunnel=False
        self.checks.update(https=False,meta=False)
        self.status('STARTING','Connecting public HTTPS…')
        binary=shutil.which('cloudflared') or str(ROOT/'output/tools/cloudflared.exe')
        if not Path(binary).is_file():raise StartupError('CLOUDFLARED')
        child=self.spawn('tunnel',[binary,'tunnel','--url','http://127.0.0.1:8878','--no-autoupdate'])
        deadline=time.monotonic()+65;log=ROOT/'data/launcher/tunnel.log'
        while time.monotonic()<deadline and child.poll() is None:
            urls=re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com',log.read_text(encoding='utf-8',errors='replace'))
            if urls:
                self.base=urls[0];runtime=meta.read_json(meta.RUNTIME)
                runtime['origin']=self.base;meta.private_write(meta.RUNTIME,runtime)
                try:
                    if challenge(self.base,verify):self.checks['https']=True;return
                except Exception:pass
            time.sleep(1)
        raise StartupError('TUNNEL')

    def start(self):
        self.status('STARTING','Checking BeLive and WhatsApp…');self.ensure_local()
        settings=load_settings(self.database)
        if settings.agent_engine!='hermes' or settings.llm_provider!='openai' or not settings.llm_api_key:raise StartupError('HERMES')
        self.status('STARTING','Verifying official Hermes runtime (no model message sent)…')
        result=native_request([],settings,mode='memory',home=ROOT/'data/hermes_memory/launcher-check',examples=[])
        if result.get('agent_class')!='run_agent.AIAgent' or result.get('engine')!='hermes-native':raise StartupError('HERMES')
        self.checks['hermes']=True
        self.ensure_tunnel();self.status('STARTING','Verifying company number and updating its Meta callback…')
        try:update_meta(self.database,self.base)
        except StartupError:raise
        except Exception:raise StartupError('META') from None
        self.checks['meta']=True
        self.status('READY','READY — BeLive, official Hermes, HTTPS and Meta callback checked. Send a message from another phone to verify delivery. Keep this window open.')

    def monitor(self):
        try:
            with credential_scope(self.database):verify=configuration()['verify_token']
            self.checks['backend']=backend_ok(self.database)
            self.checks['https']=gateway_ok() and challenge(self.base,verify)
            if not self.checks['backend'] or not self.checks['https']:raise StartupError('TUNNEL')
            self.status('READY',self.last_detail)
            return True
        except Exception:
            self.checks.update(https=False,meta=False)
            self.status('RECONNECTING','Connection lost. Reconnecting automatically; last successful delivery is historical.')
            return False

def lock_launcher(path):
    handle=open(path,'a+b');handle.seek(0);handle.write(b'1');handle.flush();handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:handle.close();return None
    return handle

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--no-browser',action='store_true');parser.add_argument('--new-tunnel',action='store_true');args=parser.parse_args()
    load_env();(ROOT/'data').mkdir(exist_ok=True)
    lock=lock_launcher(ROOT/'data/whatsapp-launcher.lock')
    if lock is None:
        print('BeLive launcher is already running. Check Customer Support for live connection status.',flush=True)
        if not args.no_browser:webbrowser.open('http://127.0.0.1:8877')
        return
    supervisor=Supervisor(selected_database(),new_tunnel=args.new_tunnel);opened=args.no_browser
    try:
        while True:
            try:
                supervisor.start()
                if not opened:webbrowser.open('http://127.0.0.1:8877');opened=True
                while supervisor.monitor():time.sleep(20)
            except StartupError as exc:
                supervisor.status('ERROR',ERRORS.get(str(exc),'Startup failed; check local connection settings. Retrying automatically.'))
                if not opened and backend_ok(supervisor.database):webbrowser.open('http://127.0.0.1:8877');opened=True
                time.sleep(20)
            except Exception:
                supervisor.checks.update(https=False,meta=False)
                supervisor.status('ERROR','Connection check failed. No credentials displayed. Retrying automatically.');time.sleep(20)
    except KeyboardInterrupt:supervisor.status('STOPPED','Launcher stopped. Use Run BeLive Prototype.bat before the next demonstration.')
    finally:lock.close()

if __name__=='__main__':main()
