"""Isolated WhatsApp acceptance tests. No company messages or external requests."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive import whatsapp as wa
from test_backend import FakeAI

def plan(**extra):
    return dict(reply='Bro, does this affect only your phone or other devices too?',needs_staff=False,staff_question='',needs_maintenance=False,research='NONE',search_query='',sources_used=[],**extra)

class WhatsAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'test.db',FakeAI())
        self.env=patch.dict(os.environ,{'BELIVE_WHATSAPP_ACCESS_TOKEN':'test-only','BELIVE_WHATSAPP_APP_SECRET':'test-secret','BELIVE_WHATSAPP_VERIFY_TOKEN':'verify-test','BELIVE_WHATSAPP_PHONE_NUMBER_ID':'123456','BELIVE_WHATSAPP_GRAPH_VERSION':'v99.0'});self.env.start()
        self.reply=patch('belive.whatsapp_ai.reply',return_value=plan()).start();self.review=patch('belive.whatsapp_ai.review',return_value=True).start()
        self.net=patch('belive.whatsapp.request_json',side_effect=AssertionError('Unmocked external request')).start()
    def tearDown(self):patch.stopall();self.env.stop();self.tmp.cleanup()
    def rows(self,kind):
        with self.s.store.connect() as db:return self.s.store.all(db,kind)
    def cmd(self,name,**p):return self.s.command(name,p,secrets.token_hex(16))
    def incoming(self,text='bro the wifi so suck',customer='alice',**extra):return self.cmd('wa_simulate',customer=customer,text=text,**extra)
    def process(self,r):wa.process_thread(self.s,r['thread_id'])
    def signed(self,payload):
        raw=json.dumps(payload).encode();return wa.webhook(self.s,raw,'sha256='+hmac.new(b'test-secret',raw,hashlib.sha256).hexdigest())
    def payload(self,mid='wamid.test',sender='60123456789',timestamp=None):return {'object':'whatsapp_business_account','entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'123456'},'messages':[{'from':sender,'id':mid,'timestamp':str(timestamp or int(datetime.now(timezone.utc).timestamp())),'type':'text','text':{'body':'hello'}}]}}]}]}
    def test_short_greeting_and_simulation_never_sends_even_with_credentials(self):
        r=self.incoming('hi');self.process(r);self.assertEqual(self.rows('wa_outgoing')[0]['status'],'SIMULATED');self.net.assert_not_called()
    def test_duplicates_and_two_customers_are_isolated(self):
        a=self.incoming(message_id='same');self.assertTrue(self.incoming(message_id='same')['duplicate']);b=self.incoming(customer='bob');self.assertNotEqual(a['case_id'],b['case_id']);self.process(a);self.process(b)
        self.assertEqual(len(self.rows('wa_outgoing')),2);self.assertEqual(len(self.rows('wa_turn')),2)
        self.assertEqual(len(self.reply.call_args.args[1]['conversation']),1)
    def test_burst_of_messages_gets_one_contextual_response(self):
        r=self.incoming('hi');self.incoming('The shared Wi-Fi is dropping');self.incoming('Only my phone is affected');self.process(r)
        self.assertEqual(len(self.rows('wa_outgoing')),1);self.assertEqual(len(self.reply.call_args.args[1]['conversation']),3)
    def test_signed_intake_pinned_business_and_bad_signature(self):
        p=self.payload('wamid.HBgL+test/123==');a=self.signed(p);self.assertEqual(len(a),1);self.assertEqual(self.signed(p),[])
        with self.assertRaises(PermissionError):wa.webhook(self.s,b'{}','sha256=bad')
        p=self.payload('other');p['entry'][0]['changes'][0]['value']['metadata']['phone_number_id']='other';self.assertEqual(self.signed(p),[])
        self.assertEqual(wa.challenge('hub.mode=subscribe&hub.verify_token=verify-test&hub.challenge=123'),'123')
    def test_invalid_timestamp_cannot_bypass_window(self):
        with self.assertRaises(ValueError):self.signed(self.payload(timestamp='nan'))
        self.assertEqual(self.rows('wa_thread'),[])
    def test_staff_guidance_is_internal_ai_relays_and_keeps_replying(self):
        draft=plan();draft.update(needs_staff=True,staff_question='Who can repair the router?',needs_maintenance=True);self.reply.return_value=draft
        r=self.incoming();self.process(r);self.assertEqual(self.rows('wa_thread')[0]['state'],'WAITING_STAFF');self.assertEqual(len(self.rows('wa_staff')),1)
        self.process(self.incoming('Any update?'));self.assertEqual(len(self.rows('wa_staff')),1);self.assertEqual(len(self.rows('wa_outgoing')),2)
        self.assertTrue(any(x['kind']=='STAFF_WORK_ORDER' for x in self.rows('outbox')))
        t=self.rows('wa_thread')[0];self.cmd('wa_staff_reply',thread_id=t['id'],revision=t['revision'],guidance='Confirmed: technician will inspect the router tomorrow at 10 am.',confirmed=True)
        self.assertEqual(len(self.rows('wa_outgoing')),2)
        self.reply.return_value=plan();self.process(r);ctx=self.reply.call_args.args[1]
        self.assertIn('10 am',ctx['staff_guidance'][0]['verified_solution']);self.assertEqual(self.rows('wa_outgoing')[0]['status'],'SIMULATED')
        self.assertEqual(self.rows('wa_message')[1]['direction'],'STAFF_INTERNAL')
    def test_sop_property_scope_and_relevant_research(self):
        self.cmd('wa_knowledge',title='General SOP',text='Use the support chat for help.',source='Company approved fixture',confirmed=True)
        self.cmd('wa_knowledge',title='Only building A',text='Building A has a staffed front desk.',source='Company approved fixture',property_ref='A',confirmed=True)
        r=self.incoming();self.process(r);self.assertEqual(len(self.reply.call_args.args[1]['sop']),1)
        t=self.rows('wa_thread')[0];self.cmd('wa_property',thread_id=t['id'],revision=t['revision'],property_ref='A');self.process(self.incoming('What about reception?'));self.assertEqual(len(self.reply.call_args.args[1]['sop']),2)
        first=plan();first.update(research='TECHNICAL',search_query='Samsung washer error code 4C')
        self.reply.side_effect=[first,plan()]
        with patch('belive.whatsapp_ai.research',return_value={'summary':'Manufacturer guidance','sources':[{'id':'WEB-1','url':'https://www.samsung.com/support/','title':'Official','kind':'TECHNICAL'}]}) as research:
            self.process(self.incoming('My Samsung washer shows 4C'));research.assert_called_once();self.assertTrue(self.reply.call_args.args[1]['research_attempted'])
    def test_photo_observations_and_invalid_photo(self):
        image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
        with patch('belive.whatsapp_ai.read_photo',return_value={'observations':'Display says 4C','brand':'Samsung','model':'','error_code':'4C','uncertain':True}):
            self.process(self.incoming('What does this mean?',image=image))
        self.assertEqual(self.rows('wa_message')[1]['vision']['error_code'],'4C')
        with self.assertRaises(ValueError):self.incoming(image='data:image/png;base64,YmFk')
    def test_ai_failure_still_acknowledges_and_opens_staff_request(self):
        self.reply.side_effect=ValueError('AI unavailable');self.process(self.incoming());self.assertEqual(len(self.rows('wa_staff')),1);self.assertIn('asking our team',self.rows('wa_outgoing')[0]['text'])
    def test_photo_code_requires_confirmation_not_staff_or_unverified_research(self):
        image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
        draft=plan();draft.update(research='TECHNICAL',search_query='Samsung 4E error');self.reply.return_value=draft
        with patch('belive.whatsapp_ai.read_photo',return_value={'observations':'Possible 4E','brand':'','model':'','error_code':'4E','uncertain':True}),patch('belive.whatsapp_ai.research') as research:
            self.process(self.incoming('What is this code?',image=image));research.assert_not_called()
        self.assertEqual(self.rows('wa_staff'),[]);self.assertIn('exact code',self.rows('wa_outgoing')[0]['text'])
    def test_customer_dissatisfaction_is_linked_to_actual_reply_for_learning(self):
        r=self.incoming();self.process(r);self.incoming('I already tried that. You keep repeating the same answer.')
        lessons=self.rows('reply_learning');self.assertEqual(len(lessons),1);self.assertEqual(lessons[0]['reply'],plan()['reply']);self.assertTrue(lessons[0]['sample_data'])
    def test_danger_is_immediate_even_when_model_is_down(self):
        self.reply.side_effect=ValueError('AI unavailable');self.process(self.incoming('There are sparks and smoke from the washer'));self.reply.assert_not_called();self.assertIn('move away',self.rows('wa_outgoing')[0]['text']);self.assertTrue(self.rows('wa_staff')[0]['maintenance'])
    def test_verified_staff_guidance_can_follow_an_urgent_acknowledgement(self):
        r=self.incoming('There is smoke from the washer');self.process(r)
        t=self.rows('wa_thread')[0];self.cmd('wa_staff_reply',thread_id=t['id'],revision=t['revision'],guidance='Confirmed: the area is secured and a qualified technician is on site. Keep away until the team confirms it is safe.',confirmed=True)
        self.process(r);self.reply.assert_called_once();self.assertTrue(self.reply.call_args.args[1]['staff_guidance'])
    def test_expired_window_and_unknown_delivery_are_not_retried(self):
        ids=self.signed(self.payload());self.net.side_effect=TimeoutError('timeout');wa.process_thread(self.s,ids[0]);out=self.rows('wa_outgoing')[0];self.assertEqual(out['status'],'UNKNOWN');wa.deliver(self.s,out['id']);self.assertEqual(self.net.call_count,1)
        ids=self.signed(self.payload('old',sender='60987654321',timestamp=1));wa.process_thread(self.s,ids[0]);self.assertEqual(self.rows('wa_outgoing')[0]['status'],'NEEDS_TEMPLATE');self.assertEqual(self.net.call_count,1)
    def test_new_message_during_generation_supersedes_stale_reply(self):
        def generate(s,ctx):
            self.reply.side_effect=None;self.incoming('Actually it works now, thanks');return plan()
        self.reply.side_effect=generate;self.process(self.incoming());self.assertEqual(len(self.rows('wa_outgoing')),1);self.assertTrue(any(x['status']=='SUPERSEDED' for x in self.rows('wa_turn')))
    def test_snapshot_never_exposes_token_or_full_phone(self):
        self.signed(self.payload());snapshot=self.s.snapshot()['whatsapp'];encoded=json.dumps(snapshot);self.assertNotIn('60123456789',encoded);self.assertNotIn('test-secret',encoded);self.assertNotIn('test-only',encoded)

if __name__=='__main__':unittest.main()
