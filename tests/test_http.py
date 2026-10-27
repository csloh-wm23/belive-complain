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
        self.cookie=''
        code,_=self.request('/api/setup',dict(username='qa-admin',name='QA Administrator',password='Isolated-test-password-123'),{'X-CSRF-Token':self.csrf})
        self.assertEqual(code,200)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        h={'Content-Type':'application/json','Cookie':self.cookie,**(headers or {})}
        try:
            with urlopen(Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=h)) as r:
                if r.headers.get('Set-Cookie') is not None:self.cookie=r.headers['Set-Cookie'].split(';',1)[0]
                return r.status,r.read()
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
    def test_tenant_website_links_to_scoped_portal(self):
        # The public entry page must never grant operator or tenant-record access.
        code,body=self.request('/belive',headers={'Cookie':''})
        self.assertEqual(code,200)
        self.assertIn(b'href="/portal#report"',body)
        self.assertIn(b'href="/portal#conversations"',body)
        self.assertNotIn(b'csrf-token',body)
        for path in ['/assets/tenant-site.css','/assets/tenant-home.svg','/portal?topic=wifi']:
            self.assertEqual(self.request(path,headers={'Cookie':''})[0],200,path)
        self.assertEqual(self.request('/api/status',headers={'Cookie':'','X-CSRF-Token':self.csrf})[0],401)
        self.assertEqual(self.request('/api/portal',headers={'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/portal/intake',dict(title='Website complaint',description='A fictional issue for the public website test.'),{'Cookie':'','Idempotency-Key':secrets.token_hex(16)})[0],400)
        with self.s.store.connect() as db:self.assertEqual(self.s.store.all(db,'case'),[])

    def test_authentication_roles_and_session_revocation(self):
        auth={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
        self.assertEqual(self.request('/api/status',headers={**auth,'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/setup',dict(username='second',name='Second admin',password='Another-test-password-123'),auth)[0],400)
        code,_=self.request('/api/users',dict(username='qa-support',name='QA Support',password='Support-test-password-123',role='SUPPORT'),auth)
        self.assertEqual(code,200);admin_cookie=self.cookie
        self.assertEqual(self.request('/api/logout',{},auth)[0],200)
        code,_=self.request('/api/login',dict(username='qa-support',password='Support-test-password-123'),auth);self.assertEqual(code,200)
        for route in ['backup','restore','users','source','record_update','select-database','ai-check']:
            self.assertEqual(self.request('/api/'+route,{},auth)[0],403,route)
        self.assertEqual(self.request('/api/users',headers=auth)[0],403)
        with self.s.store.connect() as db:
            stored=self.s.store.all(db,'user');self.assertNotIn('Support-test-password-123',str(stored))
        support_cookie=self.cookie;self.cookie=admin_cookie
        # The old admin session was explicitly logged out.
        self.assertEqual(self.request('/api/status',headers=auth)[0],401)
        self.request('/api/login',dict(username='qa-admin',password='Isolated-test-password-123'),auth)
        self.assertEqual(self.request('/api/deactivate-user',{'id':'qa-support'},auth)[0],200)
        self.assertEqual(self.request('/api/status',headers={**auth,'Cookie':support_cookie})[0],401)
    def test_removed_operation_routes_are_unavailable(self):
        for name in ['move','move_complete','staff']:
            code,body=self.request('/api/'+name,{},headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})
            self.assertEqual(code,400);self.assertIn('only tenant enquiry and complaint',json.loads(body)['error'])
    def test_database_picker_is_operator_only_and_can_be_cancelled(self):
        self.s.workspace_config=Path(self.tmp.name)/'workspace.json'
        with patch('server.choose_database',return_value=None) as picker:
            self.assertEqual(self.request('/api/select-database',{})[0],403)
            picker.assert_not_called()
            self.assertEqual(self.request('/api/select-database',{},headers={'X-CSRF-Token':self.csrf})[0],400)
            picker.assert_not_called()
            code,body=self.request('/api/select-database',{},headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})
            self.assertEqual(code,200);self.assertTrue(json.loads(body)['cancelled']);picker.assert_called_once()
            self.assertFalse(self.s.workspace_config.exists())
    def test_shared_memory_never_exports_tenant_records(self):
        with patch.dict(os.environ,{'BELIVE_MEMORY_CLIENTS':json.dumps({'test':'isolated-test-token'})}):
            self.assertEqual(self.request('/api/shared-memory')[0],401)
            code,body=self.request('/api/shared-memory',headers={'Authorization':'Bearer isolated-test-token'})
            self.assertEqual(code,200);self.assertEqual(json.loads(body),{'examples':[]})
    def test_website_complaint_is_scoped_idempotent_and_reaches_dashboard(self):
        def cmd(name,p):return self.s.command(name,p,secrets.token_hex(16))
        cmd('condo',dict(id='WEB',name='Fictional website property',rules='Fictional support guidance for this isolated website test.',confirmed=True))
        for tid in ['WEB-A','WEB-B']:cmd('tenant',dict(id=tid,condo_id='WEB',unit_ref='DEMO',verified_by='Fixture staff',evidence='Fictional tenancy checked for this test.',confirmed=True))
        token=cmd('portal_issue',{'tenant_id':'WEB-A'})['token']
        payload=dict(title='Website Wi-Fi complaint',description='Fictional website complaint: the Wi-Fi disconnects each evening.',tenant_id='WEB-B',entrypoint='OPERATOR')
        headers={'Authorization':'Bearer '+token,'Idempotency-Key':secrets.token_hex(16)}
        code,body=self.request('/api/website/complaints',payload,headers)
        self.assertEqual(code,200);receipt=json.loads(body)
        self.assertEqual(self.request('/api/website/complaints',payload,headers)[1],body)
        with self.s.store.connect() as db:
            cases=self.s.store.all(db,'case');self.assertEqual(len(cases),1)
            self.assertEqual(cases[0]['id'],receipt['id']);self.assertEqual(cases[0]['tenant_id'],'WEB-A')
            self.assertEqual(cases[0]['entrypoint'],'TENANT_WEBSITE')
        code,body=self.request('/api/status',headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(code,200);self.assertIn(receipt['id'],[c['id'] for c in json.loads(body)['cases']])
        self.assertEqual(self.request('/api/status',headers={'X-CSRF-Token':self.csrf,'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/website/complaints',payload,{**headers,'Origin':'https://foreign.example'})[0],403)
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.name.startswith('Thread') and thread is not self.thread:thread.join(2)

    def test_website_complaint_needs_tenant_key_and_screens_risk(self):
        payload=dict(title='Website risk test',description='Smoke and sparks are coming from the electrical socket.')
        self.assertEqual(self.request('/api/website/complaints',payload,{'Idempotency-Key':secrets.token_hex(16)})[0],400)
        with self.s.store.connect() as db:self.assertEqual(self.s.store.all(db,'case'),[])
        def cmd(name,p):return self.s.command(name,p,secrets.token_hex(16))
        cmd('condo',dict(id='SAFE',name='Fictional safety property',rules='Fictional fixture: immediate risks need staff.',confirmed=True))
        cmd('tenant',dict(id='SAFE-A',condo_id='SAFE',unit_ref='DEMO',verified_by='Fixture staff',evidence='Fictional tenancy checked for safety test.',confirmed=True))
        token=cmd('portal_issue',{'tenant_id':'SAFE-A'})['token']
        code,body=self.request('/api/website/complaints',payload,{'Authorization':'Bearer '+token,'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(code,200);self.assertEqual(json.loads(body)['status'],'HUMAN_REVIEW')
        with self.s.store.connect() as db:
            c=self.s.store.get(db,'case',json.loads(body)['id']);self.assertEqual(c['severity'],'CRITICAL')
            self.assertEqual(self.s.store.all(db,'job'),[])

    def test_portal_cannot_choose_another_tenant_on_intake(self):
        def cmd(name,p):return self.s.command(name,p,secrets.token_hex(16))
        cmd('condo',dict(id='C',name='Fixture condo',rules='Fictional support guidance: report Wi-Fi issues privately.',confirmed=True))
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
