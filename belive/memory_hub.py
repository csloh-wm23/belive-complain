"""Private knowledge-only hub. Never exposes operator accounts or customer records."""
import hashlib
import hmac
import json
import re
import sqlite3
import threading
from contextlib import contextmanager,closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from belive.store import now

FIELDS={
 'sop':{'id','title','text','active','verified','version','property_ref','source','document_id','policy','topics','pages','clauses','source_excerpt','reference_scope'},
 'document':{'id','sha256','filename','page_count','scope','active','issues','revision'},
 'experience':{'id','question','answer','category','sample_data','enabled','provenance'},
 'tip':{'id','question','tip','category','sample_data','enabled','status','approved','scope_condo'},
}


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def clean(kind,value):
    if kind not in FIELDS or not isinstance(value,dict) or set(value)-FIELDS[kind]:raise ValueError('Only reviewed knowledge fields can be shared')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(value.get('id',''))):raise ValueError('Invalid knowledge identifier')
    if len(json.dumps(value))>180000:raise ValueError('Knowledge entry too large')
    for k in ('active','verified','enabled','approved','sample_data'):
        if k in value and type(value[k]) is not bool:raise ValueError('Invalid knowledge state')
    if kind=='sop':
        if not isinstance(value.get('text'),str) or not 8<=len(value['text'])<=18000 or not isinstance(value.get('title'),str):raise ValueError('Invalid SOP')
        if value.get('policy') not in {None,'GENERAL_GUIDANCE','STAFF_DECISION','CONFLICT_REVIEW'}:raise ValueError('Invalid SOP policy')
    if kind=='experience' and (not isinstance(value.get('question'),str) or not isinstance(value.get('answer'),str)):raise ValueError('Invalid approved experience')
    if kind=='tip' and (value.get('scope_condo') is not None or not isinstance(value.get('tip'),str)):raise ValueError('Only general approved writing tips are shared')
    if kind=='tip' and value.get('enabled') and (value.get('approved') is not True or value.get('status')!='APPROVED' or not 8<=len(value['tip'])<=1000):raise ValueError('Only reviewed and approved writing tips can be enabled')
    if kind=='experience' and value.get('enabled') and (not 5<=len(value['question'])<=1000 or not 8<=len(value['answer'])<=3000):raise ValueError('Use a reviewed general question and customer-facing answer')
    if kind=='document' and not re.fullmatch(r'[a-f0-9]{64}',value.get('sha256','')):raise ValueError('Invalid document hash')
    return value


class Hub:
    def __init__(self,path,workspace_id,tokens):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.workspace_id=workspace_id;self.tokens=tokens;self.lock=threading.RLock()
        with self.connect() as db:db.executescript('''
            CREATE TABLE IF NOT EXISTS items(key TEXT PRIMARY KEY,kind TEXT NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,actor TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history(seq INTEGER PRIMARY KEY,key TEXT NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,actor TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS peers(name TEXT PRIMARY KEY,last_seen TEXT NOT NULL);
        ''')
    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path,timeout=15)) as db:
            with db:yield db
    def snapshot(self):
        with self.lock,self.connect() as db:
            records=[{'key':k,'kind':kind,'value':json.loads(body),'revision':rev,'updated_at':at,'actor':actor} for k,kind,body,rev,at,actor in db.execute('SELECT * FROM items ORDER BY key')]
            if len(records)>5000:raise ValueError('Knowledge capacity reached; configure a larger shared service')
            available=[p.stem for p in (self.path.parent/'documents').glob('*.pdf')]
            peers=[{'name':n,'last_seen':at} for n,at in db.execute('SELECT * FROM peers ORDER BY name')]
            return {'schema_version':1,'workspace_id':self.workspace_id,'records':records,'peers':peers,'available_documents':available,'sequence':db.execute('SELECT coalesce(max(seq),0) FROM history').fetchone()[0]}
    def seen(self,actor):
        with self.lock,self.connect() as db:db.execute('INSERT INTO peers VALUES(?,?) ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen',(actor,now()))
    def document(self,sha):
        if not re.fullmatch(r'[a-f0-9]{64}',sha):raise ValueError('Invalid source hash')
        if not any(x['kind']=='document' and x['value']['sha256']==sha for x in self.snapshot()['records']):raise ValueError('Unknown shared document')
        return self.path.parent/'documents'/(sha+'.pdf')
    def put(self,p,actor):
        kind=p.get('kind');value=clean(kind,p.get('value'));key=kind+':'+value['id']
        expected=p.get('expected_revision')
        if type(expected) is not int or expected<0:raise ValueError('Expected shared revision is required')
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT body,revision FROM items WHERE key=?',(key,)).fetchone()
            rev=old[1] if old else 0
            if old and fingerprint(json.loads(old[0]))==fingerprint(value):return 200,{'revision':rev,'key':key}
            if rev!=expected:return 409,{'error':'SHARED_CONFLICT','key':key,'current_revision':rev,'current_value':json.loads(old[0]) if old else None}
            rev+=1;at=now();body=json.dumps(value)
            db.execute('INSERT INTO items VALUES(?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET body=excluded.body,revision=excluded.revision,updated_at=excluded.updated_at,actor=excluded.actor',(key,kind,body,rev,at,actor))
            db.execute('INSERT INTO history(key,body,revision,updated_at,actor) VALUES(?,?,?,?,?)',(key,body,rev,at,actor))
            return 200,{'revision':rev,'key':key}


def handler(hub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,value):
            data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def actor(self):
            # Public Funnel traffic has no identity header. A Serve proxy must be private.
            host=self.headers.get('Host','').split(':')[0].lower()
            if (self.headers.get('X-Forwarded-For') or self.headers.get('X-Forwarded-Proto')) and not self.headers.get('Tailscale-User-Login'):return None
            if host not in {'localhost','127.0.0.1'} and not self.headers.get('Tailscale-User-Login'):return None
            if self.headers.get('Origin'):return None
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            actor=next((label for secret,label in hub.tokens.items() if secret and hmac.compare_digest(secret,token)),None)
            if actor:hub.seen(actor)
            return actor
        def do_GET(self):
            if not self.actor():return self.respond(401,{'error':'Private shared-memory access required'})
            if urlsplit(self.path).path.startswith('/v1/document/'):
                try:
                    data=hub.document(self.path.rsplit('/',1)[-1]).read_bytes();self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
                except (ValueError,FileNotFoundError):return self.respond(404,{'error':'Source document not available'})
            if urlsplit(self.path).path!='/v1/knowledge':return self.respond(404,{'error':'Knowledge endpoint only'})
            try:return self.respond(200,hub.snapshot())
            except ValueError as exc:return self.respond(400,{'error':str(exc)})
        def do_POST(self):
            actor=self.actor()
            if not actor:return self.respond(401,{'error':'Private shared-memory access required'})
            if urlsplit(self.path).path.startswith('/v1/document/'):
                try:
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=20*1024*1024:return self.respond(413,{'error':'Source PDF too large'})
                    sha=self.path.rsplit('/',1)[-1];path=hub.document(sha);data=self.rfile.read(size)
                    if not data.startswith(b'%PDF-') or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Source checksum mismatch')
                    path.parent.mkdir(exist_ok=True)
                    if not path.exists():path.write_bytes(data)
                    return self.respond(200,{'stored':True})
                except (ValueError,FileNotFoundError):return self.respond(400,{'error':'Invalid source PDF'})
            if urlsplit(self.path).path!='/v1/knowledge':return self.respond(404,{'error':'Knowledge endpoint only'})
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=200000:return self.respond(413,{'error':'Knowledge request too large'})
                status,value=hub.put(json.loads(self.rfile.read(size)),actor);return self.respond(status,value)
            except (ValueError,TypeError,KeyError):return self.respond(400,{'error':'Invalid reviewed knowledge update'})
    return Handler


def serve(hub,port=8878):
    server=ThreadingHTTPServer(('127.0.0.1',port),handler(hub))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();return server
