"""HTTP access boundaries against a real temporary localhost server."""
import json
import os
import re
import secrets
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from belive.service import Service
from server import make_handler
from test_backend import FakeAI

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'test.db',FakeAI())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.s))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        page=urlopen(self.url).read().decode();self.csrf=re.search('name="csrf-token" content="([^"]+)"',page)[1]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        h={'Content-Type':'application/json',**(headers or {})}
        try:
            with urlopen(Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=h)) as r:return r.status,r.read()
        except HTTPError as e:
            with e:return e.code,e.read()
    def test_operator_csrf_host_origin_and_private_files(self):
        self.assertEqual(self.request('/api/status')[0],403)
        self.assertEqual(self.request('/api/status',headers={'X-CSRF-Token':self.csrf})[0],200)
        self.assertEqual(self.request('/',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/tick',{},headers={'X-CSRF-Token':self.csrf,'Origin':'https://evil.example'})[0],403)
        for path in ['/data/belive.db','/.env','/belive/settings.py','/../server.py']:
            self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/api/portal',headers={'Authorization':'Bearer invalid'})[0],401)
    def test_shared_memory_never_exports_tenant_records(self):
        with patch.dict(os.environ,{'BELIVE_MEMORY_CLIENTS':json.dumps({'test':'isolated-test-token'})}):
            self.assertEqual(self.request('/api/shared-memory')[0],401)
            code,body=self.request('/api/shared-memory',headers={'Authorization':'Bearer isolated-test-token'})
            self.assertEqual(code,200);self.assertEqual(json.loads(body),{'examples':[]})
    def test_portal_cannot_choose_another_tenant_on_intake(self):
        def cmd(name,p):return self.s.command(name,p,secrets.token_hex(16))
        cmd('condo',dict(id='C',name='Fixture condo',days=[5,6],start='08:00',end='18:00',checklist=['Room inspection'],rules='Fictional weekend move rules.',confirmed=True))
        for tid in ['T-A','T-B']:cmd('tenant',dict(id=tid,condo_id='C',unit_ref='U',verified_by='Test staff',evidence='Fictional tenancy checked.',confirmed=True))
        token=cmd('portal_issue',dict(tenant_id='T-A'))['token']
        code,body=self.request('/api/portal/intake',dict(title='Tenant Wi-Fi issue',description='The room Wi-Fi drops during the evening.',tenant_id='T-B'),{'Authorization':'Bearer '+token,'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(code,200);cid=json.loads(body)['id']
        with self.s.store.connect() as db:self.assertEqual(self.s.store.get(db,'case',cid)['tenant_id'],'T-A')
        code,body=self.request('/api/portal',headers={'Authorization':'Bearer '+token})
        self.assertEqual(code,200);self.assertNotIn('draft',json.loads(body)['cases'][0])
        # Wait for the test-only background AI to release its SQLite connection.
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.name.startswith('Thread') and thread is not self.thread:thread.join(2)
