"""HTTP access boundaries against a real temporary localhost server."""
import json
import os
import re
import secrets
import tempfile
import threading
import time
import unittest
from http.cookies import SimpleCookie
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
                if r.headers.get('Set-Cookie') is not None:
                    cookies=SimpleCookie(self.cookie)
                    for header in r.headers.get_all('Set-Cookie'):
                        cookies.load(header)
                    self.cookie='; '.join(f'{k}={v.value}' for k,v in cookies.items())
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
        self.assertIn(b'href="/portal?view=make"',body)
        self.assertIn(b'href="/portal?view=track"',body)
        self.assertNotIn(b'csrf-token',body)
        for path in ['/assets/tenant-site.css','/assets/tenant-home.svg','/assets/workspace-v2.css','/assets/workspace-v2.js','/portal?topic=wifi']:
            self.assertEqual(self.request(path,headers={'Cookie':''})[0],200,path)
        self.assertEqual(self.request('/api/status',headers={'Cookie':'','X-CSRF-Token':self.csrf})[0],401)
        self.assertEqual(self.request('/api/portal',headers={'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/portal/intake',dict(title='Website complaint',description='A fictional issue for the public website test.'),{'Cookie':'','Idempotency-Key':secrets.token_hex(16)})[0],400)
        with self.s.store.connect() as db:self.assertEqual(self.s.store.all(db,'case'),[])

    def test_demo_session_requires_explicit_fictional_setup_and_preserves_isolation(self):
        headers={'Cookie':'','Idempotency-Key':secrets.token_hex(16)}
        self.assertFalse(json.loads(self.request('/api/demo',headers={'Cookie':''})[1])['available'])
        self.assertEqual(self.request('/api/demo/session',{},headers)[0],400)
        self.s.command('demo_prepare',{'confirmed':True},secrets.token_hex(12))
        self.assertTrue(json.loads(self.request('/api/demo',headers={'Cookie':''})[1])['available'])
        code,body=self.request('/api/demo/session',{'tenant_id':'NOT-THE-DEMO'},headers)
        self.assertEqual(code,200);token=json.loads(body)['token']
        code,body=self.request('/api/portal',headers={'Cookie':'','Authorization':'Bearer '+token})
        self.assertEqual(code,200);self.assertEqual(json.loads(body)['tenant_id'],'DEMO-AUTOMATION-TEST')
        self.assertTrue(json.loads(body)['demo_only'])
        self.assertEqual(self.request('/api/demo/session',{},dict(headers,Origin='https://foreign.example'))[0],403)
        self.s.command('demo_settings',{'enabled':False},secrets.token_hex(12))
        self.assertEqual(self.request('/api/portal',headers={'Cookie':'','Authorization':'Bearer '+token})[0],401)

    def test_demo_setup_is_admin_only(self):
        auth={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
        self.request('/api/users',dict(username='qa-support',name='QA Support',password='Support-test-password-123',role='SUPPORT'),auth)
        self.request('/api/logout',{},auth)
        self.request('/api/login',dict(username='qa-support',password='Support-test-password-123'),auth)
        for route in ['demo_prepare','demo_settings','routing_settings']:
            self.assertEqual(self.request('/api/'+route,{'confirmed':True},auth)[0],403)

    def test_authentication_roles_and_session_revocation(self):
        auth={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
        self.assertEqual(self.request('/api/status',headers={**auth,'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/setup',dict(username='second',name='Second admin',password='Another-test-password-123'),auth)[0],400)
        code,_=self.request('/api/users',dict(username='qa-support',name='QA Support',password='Support-test-password-123',role='SUPPORT'),auth)
        self.assertEqual(code,200);admin_cookie=self.cookie
        self.assertEqual(self.request('/api/logout',{},auth)[0],200)
        code,_=self.request('/api/login',dict(username='qa-support',password='Support-test-password-123'),auth);self.assertEqual(code,200)
        for route in ['backup','restore','users','source','record_update','select-database','ai-check','review-chrome-sign-in','answer','answer_deactivate','automation_settings']:
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
        payload=dict(title='Website Wi-Fi complaint',description='Fictional website complaint: the Wi-Fi disconnects each evening.',tenant_id='WEB-B',entrypoint='OPERATOR',rental_property='Fixture Residence',rental_unit='Block B, 12-03')
        headers={'Idempotency-Key':secrets.token_hex(16)}
        code,body=self.request('/api/website/complaints',payload,headers)
        self.assertEqual(code,200);receipt=json.loads(body)
        self.assertNotIn('complaint_code',receipt)
        self.assertEqual(self.request('/api/website/complaints',payload,headers)[1],body)
        with self.s.store.connect() as db:
            cases=self.s.store.all(db,'case');self.assertEqual(len(cases),1)
            self.assertEqual(cases[0]['id'],receipt['id']);self.assertEqual(cases[0]['tenant_id'],'')
            self.assertEqual(cases[0]['entrypoint'],'TENANT_WEBSITE')
            self.assertEqual(cases[0]['reported_location'],{'property':'Fixture Residence','unit':'Block B, 12-03'})
            browser=SimpleCookie(self.cookie)['belive_complaints'].value
            self.assertNotIn(browser,str([tuple(x) for x in db.execute('SELECT * FROM requests')]))
            self.assertNotIn(browser,str(self.s.store.all(db,'portal')))
        code,portal=self.request('/api/portal')
        self.assertEqual(code,200);portal=json.loads(portal)
        self.assertEqual(portal['access_scope'],'BROWSER');self.assertEqual([c['id'] for c in portal['cases']],[receipt['id']])
        code,body=self.request('/api/status',headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(code,200);self.assertIn(receipt['id'],[c['id'] for c in json.loads(body)['cases']])
        self.assertEqual(self.request('/api/status',headers={'X-CSRF-Token':self.csrf,'Cookie':''})[0],401)
        self.assertEqual(self.request('/api/website/complaints',payload,{**headers,'Origin':'https://foreign.example'})[0],403)
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.name.startswith('Thread') and thread is not self.thread:thread.join(2)

    def test_website_complaint_needs_no_tenant_key_and_screens_risk(self):
        payload=dict(title='Website risk test',description='Smoke and sparks are coming from the electrical socket.')
        code,body=self.request('/api/website/complaints',payload,{'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(code,200);self.assertEqual(json.loads(body)['status'],'HUMAN_REVIEW')
        receipt=json.loads(body)
        code,body=self.request('/api/portal')
        self.assertEqual(code,200)
        messages=json.loads(body)['cases'][0]['conversation']
        self.assertTrue(any(m['sender']=='SYSTEM' and 'staff queue' in m['text'] for m in messages))
        self.assertTrue(any(m['sender']=='SYSTEM' and 'received your complaint' in m['text'] for m in messages))
        with self.s.store.connect() as db:
            c=self.s.store.get(db,'case',receipt['id']);self.assertEqual(c['severity'],'CRITICAL')
            self.assertEqual(self.s.store.all(db,'job'),[])

    def test_website_property_directory_resolves_address(self):
        status,body=self.request('/assets/property-directory.json')
        self.assertEqual(status,200)
        directory=json.loads(body)
        self.assertEqual(len(directory),47)
        listing=directory[0]
        status,body=self.request('/api/website/complaints',{
            'title':'Property lookup test','description':'Smoke from a fictional socket.',
            'rental_property':listing['name'].lower(),'rental_unit':'Block B, 12-03'
        },{'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(status,200)
        with self.s.store.connect() as db:
            case=self.s.store.get(db,'case',json.loads(body)['id'])
            self.assertEqual(case['reported_location'],{
                'property':listing['name'],'unit':'Block B, 12-03','address':listing['address']})

    def test_public_faq_replies_without_verification_and_can_escalate(self):
        payload=dict(title='complaint follow up',description='How do I track my complaint? i forget the complaint id',rental_property='Fixture Residence')
        status,body=self.request('/api/website/complaints',payload,{'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(status,200)
        receipt=json.loads(body)
        self.assertEqual(receipt['status'],'FOLLOW_UP')
        headers={'Idempotency-Key':secrets.token_hex(16)}
        status,body=self.request('/api/portal',headers=headers)
        self.assertEqual(status,200)
        complaint=json.loads(body)['cases'][0]
        self.assertTrue(complaint['informational_answer'])
        self.assertTrue(any('Track complaint' in m['text'] for m in complaint['conversation']))
        self.assertTrue(any('original complaint reference' in m['text'] or 'recovery email' in m['text'] for m in complaint['conversation']))
        self.assertEqual(self.request('/api/portal/update',{'id':receipt['id'],'note':'ok thank'},headers)[0],200)
        status,body=self.request('/api/portal',headers=headers)
        self.assertEqual(status,200)
        self.assertIn('welcome',json.loads(body)['cases'][0]['conversation'][-1]['text'])
        with self.s.store.connect() as db:
            self.assertEqual(self.s.store.get(db,'case',receipt['id'])['status'],'FOLLOW_UP')
        headers['Idempotency-Key']=secrets.token_hex(16)
        self.assertEqual(self.request('/api/portal/feedback',{'id':receipt['id'],'resolved':False},headers)[0],200)
        with self.s.store.connect() as db:
            self.assertEqual(self.s.store.get(db,'case',receipt['id'])['status'],'HUMAN_REVIEW')
            self.assertEqual(self.s.store.all(db,'job'),[])

    def test_operator_can_refresh_stale_csrf_token(self):
        status,body=self.request('/api/status',headers={'X-CSRF-Token':'from-a-previous-server'})
        self.assertEqual(status,403)
        self.assertEqual(json.loads(body)['code'],'STALE_CSRF')
        status,body=self.request('/api/auth')
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/status',headers={'X-CSRF-Token':json.loads(body)['csrf_token']})[0],200)

    def test_scan_all_honors_saved_interval_and_deduplicates(self):
        headers={'X-CSRF-Token':self.csrf}
        self.assertEqual(self.request('/api/scan-all',{},headers)[0],400)
        self.assertEqual(self.request('/api/source_schedule',{'minutes':7},
                                     {**headers,'Idempotency-Key':secrets.token_hex(16)})[0],200)
        for platform,resource in [('GOOGLE','accounts/1/locations/2'),('FACEBOOK','1/feed'),('THREADS','2/replies')]:
            self.s.command('source',{'platform':platform,'resource':resource,'authorised':True},secrets.token_hex(16))
        auth={**headers,'Idempotency-Key':secrets.token_hex(16)}
        self.assertEqual(self.request('/api/users',dict(username='scan-staff',name='Scan Staff',
                         password='Support-fixture-only-123',role='SUPPORT'),auth)[0],200)
        self.assertEqual(self.request('/api/login',dict(username='scan-staff',password='Support-fixture-only-123'),auth)[0],200)
        self.assertEqual(self.request('/api/source',{},auth)[0],403)
        with patch('belive.connectors.read_source',return_value=[{'id':'123','text':'There is smoke coming from a fictional socket.'}]) as read:
            for _ in range(2):
                code,body=self.request('/api/scan-all',{},headers)
                self.assertEqual(code,202)
                self.assertEqual(json.loads(body)['started'],3)
                for _ in range(100):
                    code,body=self.request('/api/status',headers=headers)
                    status=json.loads(body)
                    if not status['tasks']:break
                    time.sleep(.02)
                self.assertFalse(status['tasks'])
                self.assertEqual(len(status['cases']),3)
            self.assertEqual(read.call_count,6)
        self.assertEqual(status['source_interval_minutes'],7)
        self.assertEqual({c['platform'] for c in status['cases']},{'GOOGLE','FACEBOOK','THREADS'})
        self.assertTrue(all(s['last_count']==1 and s['next_scan']>s['last_scan'] for s in status['sources']))

    def test_public_link_intake_only_accepts_supported_platforms(self):
        payload={'title':'Fictional public complaint','description':'Smoke and sparks from the socket.'}
        def submit(url):
            return self.request('/api/intake',{**payload,'public_url':url},
                                {'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(submit('https://threads.com.example.org/@demo/post/1')[0],400)
        for platform,url in [
            ('GOOGLE','https://www.google.com/maps/place/Fictional+Residence'),
            ('FACEBOOK','https://www.facebook.com/example/posts/123'),
            ('THREADS','https://www.threads.com/@example/post/test123'),
        ]:
            status,body=submit(url)
            self.assertEqual(status,200)
            case=json.loads(body)
            self.assertEqual(case['platform'],platform)
            self.assertEqual(case['public_url'],url)
            self.assertEqual(case['status'],'HUMAN_REVIEW')
            self.assertEqual(json.loads(submit(url)[1])['id'],case['id'])

    def test_api_free_review_import_reuses_an_existing_google_case(self):
        from belive.browser_reviews import read_browser_review

        headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
        link='https://www.google.com/maps/contrib/123456789/place/ExamplePlace'
        captured={'source_id':'google-browser-test','rating':1,'review_url':link,
                  'description':'The washing machine stopped working and shared laundry could not be used.'}
        with self.assertRaisesRegex(ValueError,'individual Google Maps review link'):
            read_browser_review('https://www.google.com/maps/place/Fictional+Residence')
        with patch('belive.browser_reviews.read_browser_review',return_value=captured):
            first=json.loads(self.request('/api/import-review',{'url':link},headers)[1])
            changed=link+'/@1.2,3.4,8z?hl=en'
            second=json.loads(self.request('/api/import-review',{'url':changed},headers)[1])
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['id'],second['id'])
        with self.s.store.connect() as db:
            self.assertEqual(len(self.s.store.all(db,'case')),1)
            case=self.s.store.get(db,'case',first['id'])
            self.assertEqual((case['review_url'],case['source_id']),(link,captured['source_id']))

    def test_review_chrome_sign_in_requires_admin(self):
        headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
        with patch('belive.browser_reviews.open_review_chrome_sign_in') as open_window:
            self.assertEqual(self.request('/api/review-chrome-sign-in',{},dict(headers,Cookie=''))[0],401)
            open_window.assert_not_called()
            code,body=self.request('/api/review-chrome-sign-in',{},headers)
            self.assertEqual(code,200)
            self.assertEqual(json.loads(body),{'opened':True})
            open_window.assert_called_once_with()

    def test_browser_batch_caps_imports_and_deduplicates_by_review_id(self):
        listing='https://www.google.com/maps/place/Fictional+Residence'
        captured=[
            {'source_id':f'google-browser-fixture-{number}', 'rating':1, 'listing_url':listing,
             'description':f'Smoke and sparks were reported from a socket in fictional room {number}.'}
            for number in range(12)
        ]
        with patch('belive.browser_reviews.read_browser_review_batch',return_value=(captured,0)):
            headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
            status,body=self.request('/api/import-review-batch',{'links':listing},headers)
            first=json.loads(body)
            headers['Idempotency-Key']=secrets.token_hex(16)
            again=json.loads(self.request('/api/import-review-batch',{'links':listing},headers)[1])
        self.assertEqual(status,200)
        self.assertEqual(len(first['created']),10)
        self.assertEqual(first['created'],again['duplicates'])
        self.assertEqual(again['created'],[])
        cases=self.s.snapshot()['cases']
        self.assertEqual(len(cases),10)
        self.assertTrue(all(c['public_url']==listing and c['review_rating']==1
                            and not c['can_contact_customer'] for c in cases))

    def test_save_individual_google_review_link_preserves_source_evidence(self):
        headers={'X-CSRF-Token':self.csrf}
        def post(route,data):
            return self.request('/api/'+route,data,{**headers,'Idempotency-Key':secrets.token_hex(16)})
        listing='https://www.google.com/maps/place/?q=place_id:example'
        code,body=post('intake',{'title':'Review link fixture','description':'Smoke and sparks from the socket.','public_url':listing})
        self.assertEqual(code,200)
        case=json.loads(body)
        update={'id':case['id'],'revision':case['revision'],'action':'review_link'}
        for invalid in (listing,'https://g.page/r/Example/review','https://maps.app.goo.gl.example.org/Example'):
            self.assertEqual(post('case_action',{**update,'review_url':invalid})[0],400)
        direct='https://maps.app.goo.gl/ExampleReviewLink'
        code,body=post('case_action',{**update,'review_url':direct})
        self.assertEqual(code,200)
        saved=json.loads(body)
        self.assertEqual(saved['review_url'],direct)
        for name in ('public_url','source_id','source_versions','status','analysis'):
            self.assertEqual(saved.get(name),case.get(name))
        self.assertEqual(saved.get('automation_paused'),case.get('automation_paused'))
        self.assertEqual(post('case_action',{**update,'review_url':direct})[0],400)
        code,body=self.request('/api/status',headers=headers)
        self.assertEqual(code,200)
        self.assertEqual(next(c for c in json.loads(body)['cases'] if c['id']==case['id'])['review_url'],direct)
        full='https://www.google.com/maps/contrib/123456789/place/Place-ID/@1.2,3.4,8z/data=!4m6?hl=en'
        code,body=post('case_action',{**update,'revision':saved['revision'],'review_url':full})
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['review_url'],full)
        profile='https://www.google.com/maps/contrib/123456789/reviews/'
        self.assertEqual(post('case_action',{**update,'revision':json.loads(body)['revision'],'review_url':profile})[0],400)

    def test_staff_reply_and_closure_remain_available_in_the_submitting_browser(self):
        code,body=self.request('/api/website/complaints',{
            'title':'Electrical concern','description':'Smoke and sparks from the socket.',
            'rental_property':'Fixture Residence'}, {'Idempotency-Key':secrets.token_hex(16),'Cookie':''})
        self.assertEqual(code,200)
        receipt=json.loads(body)
        self.assertEqual(receipt['status'],'HUMAN_REVIEW')
        cid=receipt['id']
        def staff(action,**fields):
            headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
            status,snapshot=self.request('/api/status',headers=headers)
            self.assertEqual(status,200)
            case=next(c for c in json.loads(snapshot)['cases'] if c['id']==cid)
            self.assertFalse(case['tenant_id'])
            return self.request('/api/case_action',dict(id=cid,revision=case['revision'],action=action,**fields),headers)
        browser_cookie='belive_complaints='+SimpleCookie(self.cookie)['belive_complaints'].value
        def customer(path='/api/portal',payload=None):
            return self.request(path,payload,{'Cookie':browser_cookie,
                                              'Idempotency-Key':secrets.token_hex(16)})
        reply='We received your report. Please tell us which shared area is affected.'
        self.assertEqual(staff('acknowledge')[0],200)
        self.assertEqual(staff('draft',note=reply)[0],200)
        self.assertNotIn(reply.encode(),customer()[1])
        self.assertEqual(staff('publish_response',confirmed=False)[0],400)
        self.assertEqual(staff('publish_response',confirmed=True,reviewed_reply='Different unsaved reply.')[0],400)
        self.assertEqual(staff('publish_response',confirmed=True,reviewed_reply=reply)[0],200)
        edited='Please avoid that socket. The maintenance team is handling the report.'
        self.assertEqual(staff('send_reply',confirmed=False,reviewed_reply=edited)[0],400)
        self.assertNotIn(edited.encode(),customer()[1])
        self.assertEqual(staff('send_reply',confirmed=True,reviewed_reply='')[0],400)
        self.assertEqual(staff('send_reply',confirmed=True,reviewed_reply=edited)[0],200)
        self.assertEqual(staff('send_reply',confirmed=True,reviewed_reply=edited)[0],200)
        status,body=customer()
        self.assertEqual(status,200)
        messages=json.loads(body)['cases'][0]['conversation']
        self.assertEqual(messages[-1]['text'],edited)
        self.assertEqual(sum(m['text']==edited for m in messages),1)
        note='It is near the shared laundry room.'
        self.assertEqual(customer('/api/portal/update',{'id':cid,'note':note})[0],200)
        status,body=self.request('/api/status',headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(status,200)
        case=next(c for c in json.loads(body)['cases'] if c['id']==cid)
        self.assertEqual(case['conversation'][-1]['text'],note)
        self.assertEqual(case['status'],'IN_PROGRESS')
        evidence='Staff recorded the action and checked the customer feedback.'
        self.assertEqual(staff('verify_staff_close',note=evidence,confirmed=True)[0],400)
        self.assertEqual(staff('followup',note=evidence)[0],200)
        self.assertEqual(staff('verify',note=evidence,confirmed=True)[0],400)
        self.assertEqual(staff('verify_close',note=evidence,confirmed=True)[0],400)
        self.assertEqual(customer('/api/portal/feedback',{'id':cid,'resolved':False})[0],200)
        self.assertEqual(json.loads(customer()[1])['cases'][0]['status'],'HUMAN_REVIEW')
        self.assertEqual(staff('acknowledge')[0],200)
        self.assertEqual(staff('followup',note=evidence)[0],200)
        self.assertEqual(customer('/api/portal/feedback',{'id':cid,'resolved':True})[0],200)
        case=json.loads(customer()[1])['cases'][0]
        self.assertTrue(case['resolution_confirmed'])
        self.assertEqual(case['status'],'FOLLOW_UP')
        self.assertEqual(staff('verify_close',note=evidence,confirmed=False)[0],400)
        self.assertEqual(staff('verify_close',note='short',confirmed=True)[0],400)
        self.assertEqual(staff('verify_close',note=evidence,confirmed=True)[0],200)
        self.assertEqual(json.loads(customer()[1])['cases'][0]['status'],'CLOSED')
        self.assertEqual(customer('/api/portal/feedback',{'id':cid,'resolved':False})[0],200)
        self.assertEqual(json.loads(customer()[1])['cases'][0]['status'],'HUMAN_REVIEW')
        with self.s.store.connect() as db:
            reopened=self.s.store.get(db,'case',cid)
            self.assertFalse(reopened['owner'])
            self.assertTrue(reopened['ack_due'])
            self.assertTrue(any(item['kind']=='STAFF_ALERT' and item['entity']==cid for item in self.s.store.all(db,'outbox')))

    def test_complaint_email_recovery_only_sends_to_matching_address(self):
        payload={'title':'Safety test','description':'Smoke from a fictional socket.','email':'fixture@example.test'}
        receipt=self.s.website_submit(payload,secrets.token_hex(16))
        with patch('belive.complaint_mail.configured',return_value=True),patch('belive.complaint_mail.send_verification') as mail:
            payload_email={'email':payload['email']}
            headers={'Authorization':'Bearer '+receipt['complaint_code']}
            with patch('belive.complaint_mail.send_code') as recovery:
                self.request('/api/website/complaint-recovery',{'reference':receipt['id'],'email':payload['email']})
                recovery.assert_not_called()
            status,_=self.request('/api/portal/verify-email',payload_email,headers)
            self.assertEqual(status,200)
            sent_code=mail.call_args.args[1]
            wrong='000000' if sent_code!='000000' else '111111'
            self.assertEqual(self.request('/api/portal/verify-email',{**payload_email,'code':wrong},headers)[0],400)
            self.assertEqual(self.request('/api/portal/verify-email',{**payload_email,'code':sent_code},headers)[0],200)
        with patch('belive.complaint_mail.configured',return_value=True),patch('belive.complaint_mail.send_code') as send:
            for email in ('wrong@example.test',payload['email'],payload['email']):
                code,body=self.request('/api/website/complaint-recovery',{'reference':receipt['id'],'email':email})
                self.assertEqual(code,200)
                self.assertEqual(json.loads(body),{'accepted':True})
            send.assert_called_once_with(payload['email'],receipt['complaint_code'])

    def test_browser_scope_isolates_complaints_and_keeps_multiple_cases(self):
        def submit(title, cookie=None, key=None):
            headers={'Idempotency-Key':key or secrets.token_hex(16)}
            if cookie is not None:
                headers['Cookie']=cookie
            code,body=self.request('/api/website/complaints',{
                'title':title,'description':'A fictional complaint with enough details for the isolation test.'},headers)
            return code,json.loads(body)

        key=secrets.token_hex(16)
        code,first=submit('First private complaint',key=key)
        self.assertEqual(code,200)
        first_browser=self.cookie
        self.assertEqual(submit('First private complaint',cookie='',key=key)[0],400)
        code,second=submit('Second private complaint',cookie='')
        self.assertEqual(code,200)
        self.assertNotEqual(first['id'],second['id'])
        code,body=self.request('/api/portal',headers={'Cookie':first_browser})
        self.assertEqual(code,200)
        self.assertEqual([c['id'] for c in json.loads(body)['cases']],[first['id']])
        code,body=self.request('/api/portal/update',{'id':second['id'],'note':'A message to another browser’s case.'},
                               {'Cookie':first_browser,'Idempotency-Key':secrets.token_hex(16)})
        self.assertEqual(code,400)
        self.assertIn('unavailable in this browser session',json.loads(body)['error'])
        code,third=submit('Third private complaint',cookie=first_browser)
        self.assertEqual(code,200)
        code,body=self.request('/api/portal',headers={'Cookie':first_browser})
        self.assertEqual(code,200)
        self.assertEqual({c['id'] for c in json.loads(body)['cases']},{first['id'],third['id']})

    def test_staff_can_close_public_case_with_checked_evidence(self):
        case=self.s.command('intake',{
            'title':'Fictional public review','description':'The shared washer stopped working and no one came to repair it.',
            'public_url':'https://www.google.com/maps/place/Fictional+Residence'},secrets.token_hex(16))
        def action(name,**payload):
            with self.s.store.connect() as db:
                current=self.s.store.get(db,'case',case['id'])
            return self.request('/api/case_action',dict(id=case['id'],revision=current['revision'],action=name,**payload),
                                {'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})
        evidence='Maintenance work order confirmed the washer works after repair.'
        self.assertEqual(action('verify_staff_close',note=evidence,confirmed=True)[0],400)
        self.assertEqual(action('acknowledge')[0],200)
        self.assertEqual(action('staff_followup',note='short')[0],400)
        self.assertEqual(action('staff_followup',note=evidence,due_at='2000-01-01T00:00:00+00:00')[0],400)
        code,body=action('staff_followup',note='Maintenance is still investigating; check the next update tomorrow.')
        self.assertEqual(code,200)
        followup=json.loads(body)
        self.assertEqual(followup['status'],'FOLLOW_UP')
        self.assertTrue(followup['staff_followup'])
        self.assertTrue(followup['action_due'])
        self.assertFalse(followup.get('verification'))
        self.assertFalse(followup.get('waiting_since'))
        with patch('belive.service.now',return_value='2099-01-01T00:00:00+00:00'):self.s.tick()
        with self.s.store.connect() as db:self.assertEqual(self.s.store.get(db,'case',case['id'])['status'],'FOLLOW_UP')
        self.assertEqual(action('acknowledge')[0],200)
        self.assertEqual(action('staff_followup',note='Staff checked again; further follow-up is required.')[0],200)
        self.assertEqual(action('verify_staff_close',note=evidence,confirmed=False)[0],400)
        code,body=action('verify_staff_close',note=evidence,confirmed=True)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['status'],'CLOSED')
        self.assertEqual(json.loads(body)['verification'],evidence)
        self.assertEqual(self.request('/api/portal_issue',{},{
            'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})[0],404)

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
