"""Admin/CSRF/idle boundaries for encrypted settings on temporary local servers."""
import json
import secrets
import unittest
from unittest.mock import patch
import test_http
from belive import credentials as c


class CredentialHttpTests(unittest.TestCase):
    setUp=test_http.HttpTests.setUp
    tearDown=test_http.HttpTests.tearDown
    request=test_http.HttpTests.request
    def headers(self):return {'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
    def test_admin_save_masks_keys_and_requires_csrf_and_current_version(self):
        secret=secrets.token_urlsafe(40);payload={'version':0,'values':{'BELIVE_AI_KEY':secret}}
        self.assertEqual(self.request('/api/credential-settings')[0],403)
        self.assertEqual(self.request('/api/credential-settings',payload)[0],403)
        self.assertEqual(self.request('/api/credential-settings',headers={**self.headers(),'Cookie':''})[0],401)
        code,body=self.request('/api/credential-settings',payload,self.headers());self.assertEqual(code,200)
        result=json.loads(body);self.assertNotIn(secret,body.decode());self.assertEqual(result['version'],1)
        self.assertEqual(c.load(self.s.store.path)['values']['BELIVE_AI_KEY'],secret)
        self.assertEqual(self.request('/api/credential-settings',payload,self.headers())[0],400)
        code,body=self.request('/api/status',headers=self.headers());self.assertEqual(code,200);self.assertNotIn(secret,body.decode())
        for path in ['/.belive-credentials.key','/data/.belive-credentials.key','/belive/credentials.py']:
            self.assertEqual(self.request(path)[0],404)
    def test_support_cannot_read_or_change_connection_settings(self):
        user={'username':'credential-support','name':'Support QA','password':secrets.token_urlsafe(24),'role':'SUPPORT'}
        self.assertEqual(self.request('/api/users',user,self.headers())[0],200)
        self.assertEqual(self.request('/api/login',{'username':user['username'],'password':user['password']},self.headers())[0],200)
        self.assertEqual(self.request('/api/credential-settings',headers=self.headers())[0],403)
        self.assertEqual(self.request('/api/credential-settings',{'version':0,'values':{'BELIVE_AI_KEY':secrets.token_urlsafe(24)}},self.headers())[0],403)
        self.assertEqual(c.load(self.s.store.path)['version'],0)
    def test_saved_platform_read_occurs_in_http_database_scope(self):
        secret=secrets.token_urlsafe(40)
        payload={'version':0,'values':{'BELIVE_WHATSAPP_ACCESS_TOKEN':secret,'BELIVE_WHATSAPP_APP_SECRET':secrets.token_urlsafe(24),
            'BELIVE_WHATSAPP_VERIFY_TOKEN':secrets.token_urlsafe(24),'BELIVE_WHATSAPP_PHONE_NUMBER_ID':'123456789',
            'BELIVE_WHATSAPP_GRAPH_VERSION':'v24.0','BELIVE_WHATSAPP_WEBHOOK_HOST':'hooks.example.test'}}
        self.assertEqual(self.request('/api/credential-settings',payload,self.headers())[0],200)
        status=json.loads(self.request('/api/status',headers=self.headers())[1])
        self.assertTrue(status['whatsapp']['configured']);self.assertNotIn(secret,json.dumps(status))
        self.assertFalse(status['whatsapp']['connection_status']['automatic_reply_observed'])
    def test_changes_wait_for_active_background_work(self):
        import re,threading
        from urllib.request import urlopen
        from server import Tasks,make_handler
        tasks=Tasks(self.s);self.server.RequestHandlerClass=make_handler(self.s,tasks)
        self.csrf=re.search('name="csrf-token" content="([^"]+)"',urlopen(self.url).read().decode())[1]
        release=threading.Event();finished=threading.Event()
        def background():
            try:release.wait(5)
            finally:finished.set()
        tasks.start('credential-idle-fixture',background)
        try:
            code,body=self.request('/api/credential-settings',{'version':0,'values':{'BELIVE_AI_MODEL':'fixture-model'}},self.headers())
            self.assertEqual(code,400);self.assertIn('Wait for active',body.decode());self.assertEqual(c.load(self.s.store.path)['version'],0)
        finally:release.set();finished.wait(5)

    def test_environment_fallback_action_is_explicit(self):
        original=secrets.token_urlsafe(24);saved=secrets.token_urlsafe(24)
        with patch.dict('os.environ',{'BELIVE_AI_KEY':original}):
            self.assertEqual(self.request('/api/credential-settings',{'version':0,'values':{'BELIVE_AI_KEY':saved}},self.headers())[0],200)
            code,body=self.request('/api/credential-settings',{'version':1,'values':{},'remove':['BELIVE_AI_KEY']},self.headers())
            self.assertEqual(code,200);field=next(x for x in json.loads(body)['fields'] if x['name']=='BELIVE_AI_KEY')
            self.assertEqual(field['source'],'environment');self.assertNotIn(original,body.decode())

if __name__=='__main__':unittest.main()
