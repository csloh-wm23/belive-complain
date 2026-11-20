"""WhatsApp-specific HTTP boundaries on an isolated localhost server."""
import base64,json,os,secrets,unittest
from unittest.mock import patch
import test_http

class WhatsAppHttpTests(unittest.TestCase):
    setUp=test_http.HttpTests.setUp
    tearDown=test_http.HttpTests.tearDown
    request=test_http.HttpTests.request
    def headers(self):return {'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
    def test_photos_require_staff_session_and_csrf(self):
        image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
        r=self.s.command('wa_simulate',dict(customer='alice',text='Photo',image=image),secrets.token_hex(16))
        with self.s.store.connect() as db:mid=self.s.store.all(db,'wa_message')[0]['id']
        route='/api/wa-photo/'+mid
        self.assertEqual(self.request(route)[0],403)
        self.assertEqual(self.request(route,headers={'Cookie':'','X-CSRF-Token':self.csrf})[0],401)
        code,body=self.request(route,headers=self.headers());self.assertEqual(code,200);self.assertTrue(body.startswith(b'\x89PNG'))
    def test_only_webhook_accepts_configured_public_host(self):
        with patch.dict(os.environ,{'BELIVE_WHATSAPP_WEBHOOK_HOST':'hooks.example.test','BELIVE_WHATSAPP_VERIFY_TOKEN':'test-verify'}):
            host={'Host':'hooks.example.test'}
            code,body=self.request('/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=test-verify&hub.challenge=123',headers=host)
            self.assertEqual((code,body),(200,b'123'))
            self.assertEqual(self.request('/api/status',headers={**self.headers(),**host})[0],403)
            self.assertEqual(self.request('/',headers=host)[0],403)
            self.assertEqual(self.request('/webhooks/whatsapp',{},host)[0],403)
    def test_company_sop_cannot_be_approved_by_support_role(self):
        p=dict(username='wa-support',name='Support QA',password='Support-test-password-123',role='SUPPORT')
        self.assertEqual(self.request('/api/users',p,self.headers())[0],200)
        self.assertEqual(self.request('/api/login',dict(username=p['username'],password=p['password']),self.headers())[0],200)
        sop=dict(title='Company SOP',text='This must be approved by an administrator.',source='Company fixture',confirmed=True)
        self.assertEqual(self.request('/api/wa_knowledge',sop,self.headers())[0],403)

if __name__=='__main__':unittest.main()
