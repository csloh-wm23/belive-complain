"""OAuth grants, company-number binding and public routing; all Meta calls mocked."""
import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from belive import meta_signup as m
from belive.service import Service
from belive.store import digest
from test_backend import FakeAI

spec=importlib.util.spec_from_file_location('https_entry',Path(__file__).resolve().parents[1]/'scripts/whatsapp_https.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

class SignupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=Service(self.root/'qa.db',FakeAI())
        self.patches=[patch.object(m,'RUNTIME',self.root/'https.json'),patch.object(m,'CREDENTIALS',self.root/'credentials.json'),patch.object(m,'config',return_value={'app_id':'123456','config_id':'234567','app_secret':'fictional-secret','graph_version':'v27.0'})]
        for p in self.patches:p.start()
        m.private_write(m.RUNTIME,{'origin':'https://qa.example.test','verify_token':'fictional-verify'})
        with self.s.store.connect() as db:self.s.store.put(db,'wa_channel',{'id':'company','public_number':'60100000000'})
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def grant(self):
        ticket=m.new_link(self.s)['url'].split('#')[1];cookie,csrf=m.consume_ticket(self.s,ticket);return ticket,cookie,csrf,m.session(self.s,cookie,csrf)
    def seed_token(self):
        _,_,_,row=self.grant();row.update(status='TOKEN_READY',business_token='fictional-token')
        with self.s.store.connect() as db:self.s.store.put(db,'meta_signup',row)
        return row
    def test_ticket_single_use_csrf_expiry_and_new_link_revocation(self):
        ticket,cookie,csrf,row=self.grant()
        with self.assertRaises(ValueError):m.consume_ticket(self.s,ticket)
        with self.assertRaises(ValueError):m.session(self.s,cookie,'wrong')
        m.new_link(self.s)
        with self.assertRaises(ValueError):m.session(self.s,cookie,csrf)
    def test_code_exchange_verifies_app_and_scopes_never_returns_token(self):
        _,_,_,row=self.grant()
        with patch.object(m,'graph',side_effect=[{'access_token':'fictional-token'},{'data':{'is_valid':True,'app_id':'123456','scopes':['whatsapp_business_management','whatsapp_business_messaging']}}]) as graph:
            result=m.exchange(self.s,row,'fictional-auth-code');self.assertNotIn('token',json.dumps(result));self.assertEqual(graph.call_count,2)
        with self.assertRaises(ValueError):m.exchange(self.s,row,'fictional-auth-code')
    def test_wrong_app_token_is_not_accepted(self):
        _,_,_,row=self.grant()
        with patch.object(m,'graph',side_effect=[{'access_token':'fictional-token'},{'data':{'is_valid':True,'app_id':'other'}}]):
            with self.assertRaises(ValueError):m.exchange(self.s,row,'fictional-auth-code')
        with self.s.store.connect() as db:self.assertEqual(self.s.store.get(db,'meta_signup',row['id'])['business_token'],'')
    def test_webhook_receipts_exclude_customer_content_and_rejected_payloads(self):
        from types import SimpleNamespace
        receiver=entry.handler(self.s)
        raw=json.dumps({'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{'messages':[{'from':'60111111111','text':{'body':'PRIVATE_TEST_CONTENT'}}]}}]}]}).encode()
        receiver.record_webhook_receipt(SimpleNamespace(command='POST'),200,len(raw),raw)
        with self.s.store.connect() as db:record=self.s.store.all(db,'wa_webhook_receipt')[0]
        self.assertEqual(record['message_count'],1);self.assertEqual(record['fields'],['messages'])
        self.assertNotIn('PRIVATE_TEST_CONTENT',json.dumps(record));self.assertNotIn('60111111111',json.dumps(record))
        receiver.record_webhook_receipt(SimpleNamespace(command='POST'),403,len(raw),raw)
        with self.s.store.connect() as db:record=self.s.store.all(db,'wa_webhook_receipt')[0]
        self.assertEqual(record['count'],2);self.assertEqual(record['http_status'],403)
        self.assertEqual(record['message_count'],0);self.assertEqual(record['fields'],[])
    def test_wrong_number_or_non_coexistence_never_subscribes_or_registers(self):
        row=self.seed_token()
        for number,on_app in [('60199999999',True),('60100000000',False)]:
            with patch.object(m,'graph',return_value={'data':[{'id':'345678','display_phone_number':number,'is_on_biz_app':on_app,'platform_type':'CLOUD_API'}]}) as graph:
                with self.assertRaises(ValueError):m.complete(self.s,row,'456789')
                self.assertEqual(graph.call_count,1);self.assertFalse(m.CREDENTIALS.exists())
    def test_verified_phone_receives_only_its_override_and_keeps_existing_waba_subscription(self):
        row=self.seed_token()
        with patch.object(m,'graph',side_effect=[{'data':[{'id':'345678','display_phone_number':'+60 10 000 0000','is_on_biz_app':True,'platform_type':'CLOUD_API'}]}, {'data':[{'whatsapp_business_api_data':{'id':'123456'}}]}, {'success':True}]) as graph:
            result=m.complete(self.s,row,'456789');self.assertTrue(result['authorised']);self.assertFalse(result['delivery_verified'])
            self.assertEqual(graph.call_count,3);self.assertEqual(graph.call_args.args[0],'345678');self.assertIn('webhook_configuration',graph.call_args.kwargs['payload'])
        self.assertEqual(m.read_json(m.CREDENTIALS)['phone_number_id'],'345678')
    def test_public_routes_never_expose_dashboard_files_or_accept_foreign_origin(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),entry.handler(self.s));worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(path,method='GET',body=None,**headers):
            c=HTTPConnection('127.0.0.1',server.server_port);c.request(method,path,body,{'Host':'qa.example.test',**headers});r=c.getresponse();status=r.status;data=r.read();c.close();return status,data
        try:
            self.assertEqual(request('/connect/whatsapp')[0],200)
            for path in ['/','/api/status','/.env','/data/belive.db','/assets/app.js','/connect/../.env']:
                self.assertEqual(request(path)[0],404,path)
            self.assertEqual(request('/connect/init')[0],403)
            self.assertEqual(request('/connect/session','POST','{}',Origin='https://evil.example')[0],403)
            ticket=m.new_link(self.s)['url'].split('#')[1]
            c=HTTPConnection('127.0.0.1',server.server_port);c.request('POST','/connect/session',json.dumps({'ticket':ticket}),{'Host':'qa.example.test','Origin':'https://qa.example.test'});r=c.getresponse();self.assertEqual(r.status,200);cookie=r.getheader('Set-Cookie');r.read();c.close();self.assertIn('Secure; HttpOnly; SameSite=Strict',cookie)
            status,data=request('/connect/init',Cookie=cookie.split(';')[0]);self.assertEqual(status,200);self.assertNotIn(b'fictional-secret',data)
        finally:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
