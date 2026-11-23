"""WhatsApp-specific HTTP boundaries on an isolated localhost server."""
import base64,json,os,secrets,unittest
from unittest.mock import patch
import test_http

class WhatsAppHttpTests(unittest.TestCase):
    setUp=test_http.HttpTests.setUp
    tearDown=test_http.HttpTests.tearDown
    request=test_http.HttpTests.request
    def headers(self):return {'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)}
    def test_source_pdf_is_private_and_document_changes_are_admin_only(self):
        from belive.company_sop import import_reviewed
        from pathlib import Path
        pdf=Path(self.tmp.name)/'fixture.pdf';pdf.write_bytes(b'%PDF-1.7\nSynthetic source')
        r=import_reviewed(self.s,pdf,['Fictional general support rule.'],[{'key':'rule','title':'Fixture support rule','policy':'GENERAL_GUIDANCE','topics':['support'],'clauses':'Fixture 1','guidance':'A fictional general rule for this isolated permission test.','quotes':[{'page':1,'text':'Fictional general support rule.'}]}],[],confirmed=True)
        route='/api/wa-document/'+r['document_id']
        self.assertEqual(self.request(route)[0],403)
        self.assertEqual(self.request(route,headers={'Cookie':'','X-CSRF-Token':self.csrf})[0],401)
        code,content=self.request(route,headers=self.headers());self.assertEqual(code,200);self.assertEqual(content,pdf.read_bytes())
        self.assertEqual(self.request('/data/company_documents/fixture.pdf')[0],404)
        d=self.s.snapshot()['whatsapp']['documents'][0]
        self.assertEqual(self.request('/api/wa_document_action',{'id':d['id'],'revision':d['revision'],'active':False},self.headers())[0],200)
        p=dict(username='sop-reader',name='Support QA',password=secrets.token_urlsafe(24),role='SUPPORT')
        self.assertEqual(self.request('/api/users',p,self.headers())[0],200)
        self.assertEqual(self.request('/api/login',dict(username=p['username'],password=p['password']),self.headers())[0],200)
        self.assertEqual(self.request('/api/wa_document_action',{'id':d['id'],'revision':2,'active':True},self.headers())[0],403)
    def test_photos_require_staff_session_and_csrf(self):
        image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
        r=self.s.command('wa_simulate',dict(customer='alice',text='Photo',image=image),secrets.token_hex(16))
        with self.s.store.connect() as db:mid=self.s.store.all(db,'wa_message')[0]['id']
        route='/api/wa-photo/'+mid
        self.assertEqual(self.request(route)[0],403)
        self.assertEqual(self.request(route,headers={'Cookie':'','X-CSRF-Token':self.csrf})[0],401)
        code,body=self.request(route,headers=self.headers());self.assertEqual(code,200);self.assertTrue(body.startswith(b'\x89PNG'))
    def test_only_webhook_accepts_configured_public_host(self):
        mock_verify=secrets.token_urlsafe(24)
        with patch.dict(os.environ,{'BELIVE_WHATSAPP_WEBHOOK_HOST':'hooks.example.test','BELIVE_WHATSAPP_VERIFY_TOKEN':mock_verify}):
            host={'Host':'hooks.example.test'}
            code,body=self.request('/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token='+mock_verify+'&hub.challenge=123',headers=host)
            self.assertEqual((code,body),(200,b'123'))
            self.assertEqual(self.request('/api/status',headers={**self.headers(),**host})[0],403)
            self.assertEqual(self.request('/',headers=host)[0],403)
            self.assertEqual(self.request('/webhooks/whatsapp',{},host)[0],403)
    def test_company_sop_cannot_be_approved_by_support_role(self):
        p=dict(username='wa-support',name='Support QA',password=secrets.token_urlsafe(24),role='SUPPORT')
        self.assertEqual(self.request('/api/users',p,self.headers())[0],200)
        self.assertEqual(self.request('/api/login',dict(username=p['username'],password=p['password']),self.headers())[0],200)
        sop=dict(title='Company SOP',text='This must be approved by an administrator.',source='Company fixture',confirmed=True)
        self.assertEqual(self.request('/api/wa_knowledge',sop,self.headers())[0],403)

if __name__=='__main__':unittest.main()
