"""Independent staff issues, quoted replies and concurrent customer questions."""
import json
import secrets
import unittest
from unittest.mock import patch
from belive import whatsapp as wa
from belive.whatsapp_language import hints
from test_whatsapp import plan,fixture_assessment
import test_whatsapp as fixtures

class IssueTests(unittest.TestCase):
    setUp=fixtures.WhatsAppTests.setUp;tearDown=fixtures.WhatsAppTests.tearDown
    rows=fixtures.WhatsAppTests.rows;cmd=fixtures.WhatsAppTests.cmd;incoming=fixtures.WhatsAppTests.incoming
    process=fixtures.WhatsAppTests.process;signed=fixtures.WhatsAppTests.signed;payload=fixtures.WhatsAppTests.payload
    def waiting(self,text='Can you approve my visitor staying overnight?',question='Confirm the visitor approval conditions.'):
        self.reply.return_value={**plan(),'needs_staff':True,'staff_question':question}
        r=self.incoming(text);self.process(r)
        return r,self.rows('wa_staff')[0]
    def guidance(self,request,text='Ask for the visitor date first; staff will then confirm permission.'):
        return self.cmd('wa_staff_reply',thread_id=request['thread_id'],request_id=request['id'],request_revision=request.get('revision',0),guidance=text,confirmed=True)
    def test_two_issues_keep_separate_original_messages(self):
        _,a=self.waiting();_,b=self.waiting('The washer requires a technician.','Confirm the washer inspection arrangements.')
        self.assertEqual(len(self.rows('wa_staff')),2);self.assertNotEqual(a['origin_message_id'],b['origin_message_id'])
        self.assertEqual(next(x for x in self.rows('wa_staff') if x['id']==a['id'])['question'],a['question'])
    def test_new_safe_question_is_answered_while_old_high_issue_keeps_priority(self):
        def high(s,c):
            result=fixture_assessment(s,c);result.update(severity='HIGH',requires_human=True);return result
        self.assessment.side_effect=high;self.waiting()
        self.assessment.side_effect=fixture_assessment
        self.reply.return_value={**plan(),'reply':'You can turn Wi-Fi off and on on your own phone.'}
        self.process(self.incoming('Can I reconnect Wi-Fi on my own phone?'))
        out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['status'],'SIMULATED');self.assertIn('own phone',out['text'])
        self.assertEqual(self.rows('case')[0]['severity'],'HIGH');self.assertEqual(len(self.rows('wa_staff')),1)
    def test_customer_question_does_not_erase_queued_staff_solution(self):
        r,a=self.waiting();self.guidance(a)
        customer=self.incoming('Before that, how do I toggle Wi-Fi on my phone?')
        def reply(s,c):
            if c.get('target_request'):return {**plan(),'reply':'What date would your visitor stay?','sources_used':[a['id']]}
            return {**plan(),'reply':'Turn Wi-Fi off and on in your phone settings.'}
        self.reply.side_effect=reply;self.process(customer)
        outputs=self.rows('wa_outgoing')[:2]
        self.assertEqual([o['status'] for o in outputs],['SIMULATED','SIMULATED'])
        self.assertEqual(outputs[0]['request_id'],a['id']);self.assertEqual(outputs[0]['reply_to_message_id'],a['origin_message_id'])
        self.assertIsNone(outputs[1]['request_id']);self.assertIn('phone settings',outputs[1]['text'])
        self.assertEqual(self.rows('wa_staff')[0]['progress'],'WAITING_CUSTOMER')
    def test_staff_solution_quotes_original_in_actual_meta_payload(self):
        self.reply.return_value={**plan(),'needs_staff':True,'staff_question':'Confirm visitor approval conditions.'}
        self.net.side_effect=None;self.net.return_value={'messages':[{'id':'wamid.fixture-response'}]}
        payload=self.payload(mid='wamid.original-visitor');payload['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']='Can my visitor stay overnight?'
        tid=self.signed(payload)[0];wa.process_thread(self.s,tid)
        request=self.rows('wa_staff')[0];self.guidance(request)
        self.reply.return_value={**plan(),'reply':'What date would your visitor stay?','sources_used':[request['id']]}
        wa.process_thread(self.s,tid)
        self.assertEqual(self.net.call_args.kwargs['payload']['context'],{'message_id':'wamid.original-visitor'})
        self.assertNotEqual(self.net.call_args.kwargs['payload']['text']['body'],request.get('guidance'))
    def test_staff_instruction_cannot_target_a_different_customer(self):
        _,a=self.waiting();r=self.incoming('A different customer question.',customer='someone-else');self.process(r)
        with self.assertRaisesRegex(ValueError,'this conversation'):
            self.cmd('wa_staff_reply',thread_id=r['thread_id'],request_id=a['id'],request_revision=a['revision'],guidance='Confirmed fictional next steps.',confirmed=True)
    def test_missing_original_does_not_fall_back_to_an_unquoted_staff_reply(self):
        _,a=self.waiting()
        with self.s.store.connect() as db:
            row=self.s.store.get(db,'wa_staff',a['id']);row.pop('origin_message_id');self.s.store.put(db,'wa_staff',row)
        with self.assertRaisesRegex(ValueError,'original customer message'):self.guidance(a)
    def test_old_staff_guidance_revision_is_rejected(self):
        _,a=self.waiting();self.guidance(a)
        with self.assertRaisesRegex(ValueError,'issue changed'):self.guidance(a,'Use a different unverified sequence of steps.')
    def test_ready_evidence_can_resume_an_old_issue_with_a_quote(self):
        _,a=self.waiting('How do I reconnect Wi-Fi?','Confirm the approved phone-side checks.')
        self.reply.return_value={**plan(),'reply':'For the earlier Wi-Fi question, turn Wi-Fi off and on on your own phone.','related_request_id':a['id']}
        self.process(self.incoming('I am using my own phone.'))
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['status'],'SIMULATED')
        self.assertEqual(out['reply_to_message_id'],a['origin_message_id']);self.assertEqual(self.rows('wa_staff')[0]['progress'],'WAITING_CUSTOMER')
        self.assertNotEqual(self.rows('case')[0]['status'],'CLOSED')
    def test_xpe_does_not_close_waiting_issue(self):
        self.waiting();self.reply.return_value={**plan(),'reply':'Baik, beritahu saya jika ada soalan lain.'}
        self.process(self.incoming('xpe, tq'))
        self.assertEqual(self.rows('wa_staff')[0]['status'],'OPEN');self.assertNotEqual(self.rows('case')[0]['status'],'CLOSED')
    def test_unrelated_customer_message_does_not_invalidate_selected_staff_issue(self):
        _,a=self.waiting();self.incoming('One more question about my phone.')
        self.guidance(a);self.assertEqual(self.rows('wa_staff')[0]['progress'],'GUIDANCE_READY')
    def test_language_hints_preserve_negative_and_ambiguous_meanings(self):
        original='sy xde wifi skrg, u blh help? xpe ur choice'
        conversation=[{'role':'CUSTOMER','text':original}];result=hints(conversation)
        self.assertIn('tak ada',result['xde']);self.assertIn('tak apa',result['xpe']);self.assertIn('you',result['u'])
        self.assertIn('your or you are',result['ur']);self.assertEqual(conversation[0]['text'],original)
    def test_expired_window_keeps_guidance_then_reopens_after_new_customer_message(self):
        r,a=self.waiting();self.guidance(a)
        with self.s.store.connect() as db:
            thread=self.s.store.get(db,'wa_thread',r['thread_id']);thread['last_customer_at']=1;self.s.store.put(db,'wa_thread',thread)
        self.reply.return_value={**plan(),'reply':'What date would your visitor stay?','sources_used':[a['id']]};self.process(r)
        self.assertEqual(self.rows('wa_outgoing')[0]['status'],'NEEDS_TEMPLATE')
        fresh=self.incoming('While I wait, how can I toggle phone Wi-Fi?')
        with self.s.store.connect() as db:pending=[t for t in self.s.store.all(db,'wa_turn') if t['status']=='PENDING']
        self.assertEqual(len(pending),2);self.assertTrue(any(t.get('request_id')==a['id'] for t in pending))
        def reply(s,c):return {**plan(),'reply':'What date would your visitor stay?','sources_used':[a['id']]} if c.get('target_request') else {**plan(),'reply':'Toggle Wi-Fi in your phone settings.'}
        self.reply.side_effect=reply;self.process(fresh)
        self.assertEqual(self.rows('wa_outgoing')[0]['status'],'SIMULATED');self.assertEqual(self.rows('wa_outgoing')[0]['request_id'],a['id'])
    def test_unknown_send_is_not_automatically_retried_or_overwritten(self):
        r,a=self.waiting();self.guidance(a)
        with self.s.store.connect() as db:
            request=self.s.store.get(db,'wa_staff',a['id'])
            self.s.store.put(db,'wa_outgoing',{'id':'WAO-uncertain','thread_id':r['thread_id'],'request_id':a['id'],'status':'UNKNOWN'})
            for t in self.s.store.all(db,'wa_turn'):
                if t.get('request_id')==a['id']:t['status']='COMPLETE';self.s.store.put(db,'wa_turn',t)
            wa._queue_guidance(self.s,db,request)
            self.assertFalse(any(t.get('request_id')==a['id'] and t['status']=='PENDING' for t in self.s.store.all(db,'wa_turn')))
        with self.assertRaisesRegex(ValueError,'unconfirmed'):self.guidance(request)
    def test_unbound_legacy_issue_does_not_block_or_absorb_current_reply(self):
        _,a=self.waiting()
        with self.s.store.connect() as db:
            legacy=self.s.store.get(db,'wa_staff',a['id']);legacy.pop('origin_message_id');self.s.store.put(db,'wa_staff',legacy)
        self.reply.return_value={**plan(),'reply':'Does another device stay connected to the same Wi-Fi?','related_request_id':a['id']}
        self.process(self.incoming("I've already tried the toggles. What else can I check?"))
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['status'],'SIMULATED');self.assertIsNone(out['request_id'])
        self.assertIsNotNone(out['reply_to_message_id']);self.assertEqual(self.rows('wa_staff')[0]['status'],'OPEN')
        self.assertNotIn(a['id'],[r['id'] for r in self.reply.call_args.args[1]['support_requests']])
