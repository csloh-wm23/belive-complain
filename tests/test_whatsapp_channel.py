"""Tenant Report entry, observed delivery and mobile-app coexistence context."""
import json,os,secrets,unittest
from unittest.mock import patch
import test_whatsapp,test_http
from belive import whatsapp_channel as channel,whatsapp as wa


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_whatsapp.WhatsAppTests();self.fixture.setUp();self.s=self.fixture.s
        self.number='60'+'1'+'0'*8
        self.host=patch.dict(os.environ,{'BELIVE_WHATSAPP_WEBHOOK_HOST':'hooks.example.test'});self.host.start()
        self.fixture.cmd('wa_channel',public_number=self.number,confirmed=True)
    def tearDown(self):self.host.stop();self.fixture.tearDown()
    def status(self):
        with self.s.store.connect() as db:return channel.observed(self.s,db)
    def inbound(self,mid=None):
        p=self.fixture.payload(mid or 'wamid.'+secrets.token_hex(12));p['entry'][0]['changes'][0]['value']['metadata']['display_phone_number']='+'+self.number
        return self.fixture.signed(p)
    def test_local_malaysian_number_normalizes_without_double_country_code(self):
        local='0'+'1'+'0'*8;self.assertEqual(channel.phone(local),self.number);self.assertEqual(channel.phone('+'+self.number),self.number)
        for bad in ['https://evil.test','+60<script>','123','++']:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):channel.phone(bad)
    def test_link_and_simulations_do_not_claim_live_connection(self):
        with self.s.store.connect() as db:public=channel.public(self.s,db)
        self.assertTrue(public['chat_url'].startswith('https://wa.me/'+self.number+'?text='));self.assertFalse(public['automatic_replies_verified'])
        r=self.fixture.incoming();self.fixture.process(r);self.assertFalse(self.status()['automatic_reply_observed']);self.fixture.net.assert_not_called()
    def test_only_matching_real_message_and_receipt_confirm_automatic_delivery(self):
        self.fixture.net.side_effect=None;external='wamid.'+secrets.token_hex(14);self.fixture.net.return_value={'messages':[{'id':external}]}
        ids=self.inbound();self.assertEqual(self.status()['state'],'CUSTOMER_MESSAGE_RECEIVED');wa.process_thread(self.s,ids[0]);self.assertEqual(self.status()['state'],'REPLY_ACCEPTED');self.assertFalse(self.status()['automatic_reply_observed'])
        receipt={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{'metadata':{'phone_number_id':self.fixture.mock_phone_id,'display_phone_number':self.number},'statuses':[{'id':external,'status':'delivered'}]}}]}]}
        self.fixture.signed(receipt);self.assertTrue(self.status()['automatic_reply_observed'])
        self.fixture.cmd('wa_channel',public_number='60'+'2'+'0'*8,confirmed=True);self.assertFalse(self.status()['automatic_reply_observed'])
    def test_mobile_reply_is_context_not_a_new_customer_request_or_ai_send(self):
        ids=self.inbound();before=len(self.fixture.rows('wa_outgoing'));echo={'to':self.fixture.mock_sender,'id':'wamid.'+secrets.token_hex(12),'type':'text','text':{'body':'I have already explained the next step from the phone.'}}
        p={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'smb_message_echoes','value':{'metadata':{'phone_number_id':self.fixture.mock_phone_id},'message_echoes':[echo]}}]}]}
        self.fixture.signed(p);self.fixture.signed(p);wa.process_thread(self.s,ids[0])
        self.assertEqual(len(self.fixture.rows('case')),1);self.assertEqual(sum(x['direction']=='STAFF_MOBILE' for x in self.fixture.rows('wa_message')),1);self.assertEqual(len(self.fixture.rows('wa_outgoing')),before)
        ids=self.inbound();wa.process_thread(self.s,ids[0]);conversation=self.fixture.reply.call_args.args[1]['conversation'];self.assertTrue(any(x['role']=='STAFF_MOBILE' for x in conversation))
    def test_ai_delivery_echo_does_not_duplicate_messages(self):
        self.fixture.net.side_effect=None;external='wamid.'+secrets.token_hex(14);self.fixture.net.return_value={'messages':[{'id':external}]}
        ids=self.inbound();wa.process_thread(self.s,ids[0]);n=len(self.fixture.rows('wa_message'))
        p={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'smb_message_echoes','value':{'metadata':{'phone_number_id':self.fixture.mock_phone_id},'message_echoes':[{'id':external,'to':self.fixture.mock_sender,'type':'text','text':{'body':'Echo of sent AI reply'}}]}}]}]}
        self.fixture.signed(p);self.assertEqual(len(self.fixture.rows('wa_message')),n)
    def test_history_import_does_not_start_customer_complaints_or_replies(self):
        p=self.fixture.payload();p['entry'][0]['changes'][0]['field']='history';self.assertEqual(self.fixture.signed(p),[]);self.assertEqual(self.fixture.rows('case'),[])


class ChannelHttpTests(unittest.TestCase):
    setUp=test_http.HttpTests.setUp
    tearDown=test_http.HttpTests.tearDown
    request=test_http.HttpTests.request
    def test_pending_photo_preview_returns_controlled_not_available_response(self):
        with self.s.store.connect() as db:self.s.store.put(db,'wa_message',{'id':'WAM-pending-photo','kind':'image','media':None})
        code,body=self.request('/api/wa-photo/WAM-pending-photo',headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(code,404);self.assertEqual(json.loads(body)['error'],'Photo not available')
        self.assertEqual(self.request('/api/wa-photo/WAM-pending-photo',headers={'Cookie':'','X-CSRF-Token':self.csrf})[0],401)
    def test_whatsapp_redirect_uses_only_the_configured_company_number(self):
        from http.client import HTTPConnection
        self.s.command('wa_channel',{'public_number':'60'+'1'+'0'*8,'confirmed':True},secrets.token_hex(16))
        connection=HTTPConnection('127.0.0.1',self.server.server_port);connection.request('GET','/support/whatsapp');response=connection.getresponse();self.assertEqual(response.status,302);self.assertTrue(response.getheader('Location').startswith('https://wa.me/60100000000?text='));response.read();connection.close()
    def test_public_contact_is_safe_and_does_not_require_tenant_verification(self):
        self.s.command('wa_channel',{'public_number':'60'+'1'+'0'*8,'confirmed':True},secrets.token_hex(16))
        code,body=self.request('/api/support-channel',headers={'Cookie':''});self.assertEqual(code,200);value=json.loads(body);self.assertTrue(value['available']);self.assertFalse(value['automatic_replies_verified']);self.assertNotIn('token',body.decode());self.assertNotIn('phone_number_id',body.decode())
    def test_contact_number_change_requires_operator_login_and_admin(self):
        payload={'public_number':'60'+'1'+'0'*8,'confirmed':True};headers={'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16),'Cookie':''}
        self.assertEqual(self.request('/api/wa_channel',payload,headers)[0],401)
        headers.pop('Cookie');self.assertEqual(self.request('/api/wa_channel',payload,headers)[0],200)
        password=secrets.token_urlsafe(24);self.request('/api/users',{'username':'channel-reader','name':'QA','password':password,'role':'SUPPORT'},{'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})
        self.request('/api/login',{'username':'channel-reader','password':password},{'X-CSRF-Token':self.csrf})
        self.assertEqual(self.request('/api/wa_channel',payload,{'X-CSRF-Token':self.csrf,'Idempotency-Key':secrets.token_hex(16)})[0],403)

if __name__=='__main__':unittest.main()
