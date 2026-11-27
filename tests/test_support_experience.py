"""Internal work stages, observed progress, quote-aware learning and typing safety."""
import time,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from belive import whatsapp as wa,maintenance_queue as queue,support_progress,whatsapp_presence,reply_learning
from belive.store import digest
import test_whatsapp as fixtures

class ExperienceTests(unittest.TestCase):
    setUp=fixtures.WhatsAppTests.setUp;tearDown=fixtures.WhatsAppTests.tearDown
    rows=fixtures.WhatsAppTests.rows;cmd=fixtures.WhatsAppTests.cmd;incoming=fixtures.WhatsAppTests.incoming;process=fixtures.WhatsAppTests.process
    signed=fixtures.WhatsAppTests.signed;payload=fixtures.WhatsAppTests.payload
    def maintenance(self,complete=True):
        self.reply.return_value={**fixtures.plan(),'needs_staff':True,'needs_maintenance':True,'staff_question':'Please inspect the reported handle.',
            'maintenance_property':'QA-HOUSE' if complete else '','maintenance_unit':'QA-ROOM' if complete else '','maintenance_location_complete':complete}
        self.process(self.incoming('The door handle is detached at QA-HOUSE / QA-ROOM.'))
        return self.rows('wa_staff')[0]
    def stage(self,state):
        r=self.rows('wa_staff')[0];return self.cmd('maintenance_progress',request_id=r['id'],request_revision=r['revision'],state=state,note='Fictional checked progress; no real work.',confirmed=True)
    def test_work_stages_never_dispatch_message_or_close_support(self):
        self.maintenance();before=len(self.rows('wa_outgoing'));notices=len(self.rows('outbox'))
        for stage in ['ACCEPTED','IN_PROGRESS','BLOCKED','IN_PROGRESS','WORK_DONE']:self.stage(stage)
        r=self.rows('wa_staff')[0];self.assertEqual(r['maintenance_progress']['state'],'WORK_DONE')
        self.assertNotEqual(r['status'],'CLOSED');self.assertTrue(queue.view(r)['customer_confirmation_pending'])
        self.assertEqual(len(self.rows('wa_outgoing')),before);self.assertEqual(len(self.rows('outbox')),notices);self.net.assert_not_called()
    def test_invalid_stale_and_missing_location_updates_are_rejected(self):
        r=self.maintenance(False)
        with self.assertRaisesRegex(ValueError,'location'):self.stage('ACCEPTED')
        with self.assertRaisesRegex(ValueError,'valid work'):self.stage('WORK_DONE')
        with self.s.store.connect() as db:
            r['location_complete']=True;self.s.store.put(db,'wa_staff',r)
        self.stage('ACCEPTED')
        with self.assertRaisesRegex(ValueError,'changed'):self.cmd('maintenance_progress',request_id=r['id'],request_revision=r['revision'],state='IN_PROGRESS',note='Checked fictional progress',confirmed=True)
    def test_reminders_are_internal_and_stop_after_work_done(self):
        r=self.maintenance();r['at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        self.assertTrue(queue.view(r)['overdue'])
        r['maintenance_progress']={'state':'WORK_DONE','updated_at':r['at']}
        self.assertFalse(queue.view(r)['overdue']);self.assertTrue(queue.view(r)['internal_only'])
    def test_quoted_feedback_targets_wifi_not_newer_washer_reply(self):
        self.reply.return_value={**fixtures.plan(),'reply':'Fictional Wi-Fi reply.'};self.process(self.incoming('My phone cannot connect to Wi-Fi.'))
        wifi=self.rows('wa_outgoing')[0];wifi_id='WAM-'+digest(wifi['id'])[:24]
        with self.s.store.connect() as db:
            m=self.s.store.get(db,'wa_message',wifi_id);m['external_id']='wamid.qa-wifi';self.s.store.put(db,'wa_message',m)
        self.reply.return_value={**fixtures.plan(),'reply':'Fictional washing machine reply.'};self.process(self.incoming('The washing machine stopped.'))
        with self.s.store.connect() as db:
            wa._ingest(self.s,db,'alice','qa-quoted-feedback','That Wi-Fi advice did not help; still not working.','text',time.time(),simulated=True,reply_to_external_id='wamid.qa-wifi')
            reply_learning.discover(self.s,db,self.rows('case')[0]['id'])
        items=self.rows('reply_learning');self.assertEqual(len(items),1)
        self.assertEqual(items[0]['reply'],'Fictional Wi-Fi reply.');self.assertEqual(items[0]['question'],'My phone cannot connect to Wi-Fi.')
        self.assertEqual(items[0]['feedback_attribution'],'EXPLICIT_WHATSAPP_QUOTE');self.assertFalse(items[0]['approved'])
    def test_typing_is_best_effort_and_simulations_never_call_meta(self):
        r=self.incoming()
        with patch('belive.whatsapp_presence.send') as send:
            self.assertFalse(whatsapp_presence.pulse(self.s,r['thread_id']));send.assert_not_called()
        self.signed(self.payload());t=next(t for t in self.rows('wa_thread') if not t['simulated'])
        with patch('belive.whatsapp_presence.send',return_value=True) as send:
            self.assertTrue(whatsapp_presence.pulse(self.s,t['id']));self.assertEqual(send.call_args.args[1],'wamid.test')
        with patch('belive.whatsapp_presence.send',side_effect=RuntimeError('Fictional failure')):
            self.assertTrue(whatsapp_presence.pulse(self.s,t['id']))
        self.assertEqual(self.rows('wa_presence')[0]['status'],'UNAVAILABLE');self.assertEqual(self.rows('wa_staff'),[])
    def test_unmatched_quote_is_not_learned_against_an_unrelated_reply(self):
        self.process(self.incoming('My phone cannot connect.'))
        with self.s.store.connect() as db:
            wa._ingest(self.s,db,'alice','qa-unknown-quote','That did not help, still not working.','text',time.time(),simulated=True,reply_to_external_id='wamid.unavailable-old-case')
        self.assertEqual(self.rows('reply_learning'),[])
    def test_automatic_learning_waits_for_active_customer_replies(self):
        from server import Tasks
        self.incoming('A customer question is waiting.')
        self.s.ai.reply_improvement=lambda *args:None
        with self.s.store.connect() as db:self.s.store.put(db,'reply_learning',{'id':'feedback-qa','case_id':self.rows('case')[0]['id'],'status':'PENDING'})
        tasks=Tasks(self.s)
        with patch.object(tasks,'reply_feedback') as run:
            tasks.pending_reply_feedback();run.assert_not_called()
            with self.s.store.connect() as db:
                for t in self.s.store.all(db,'wa_turn'):t['status']='COMPLETE';self.s.store.put(db,'wa_turn',t)
            tasks.pending_reply_feedback();run.assert_called_once_with('feedback-qa')
    def test_connection_proof_requires_same_start_customer_and_native_reply(self):
        start='2026-11-27T01:00:00+00:00';tid='WA-'+digest('phone:sender')[:20]
        threads=[{'id':tid,'recipient':'sender','simulated':False}]
        messages=[{'id':'old','thread_id':tid,'case_id':'case','direction':'CUSTOMER','at':'2026-11-26T01:00:00+00:00'}]
        out=[{'id':'o','thread_id':tid,'case_id':'case','reply_to_message_id':'old','at':'2026-11-27T01:02:00+00:00','status':'READ','native_reply_verified':True}]
        self.assertFalse(support_progress.delivery_health(threads,messages,out,[],start,'phone')['correlated_delivery_this_start'])
        messages[0]['at']='2026-11-27T01:01:00+00:00'
        self.assertTrue(support_progress.delivery_health(threads,messages,out,[],start,'phone')['correlated_delivery_this_start'])
        out[0]['native_reply_verified']=False
        self.assertFalse(support_progress.delivery_health(threads,messages,out,[],start,'phone')['correlated_delivery_this_start'])

    def test_answered_question_and_fault_waiting_for_customer_are_distinct(self):
        thread={'id':'t','case_id':'c'}
        messages=[{'id':'info','thread_id':'t','case_id':'c','direction':'CUSTOMER','text':'How do I report a problem?','at':'2026-11-27T01:00:00+00:00'},
            {'id':'fault','thread_id':'t','case_id':'c','direction':'CUSTOMER','text':'My Wi-Fi is broken.','at':'2026-11-27T01:01:00+00:00'}]
        outs=[{'id':'o2','thread_id':'t','case_id':'c','reply_to_message_id':'fault','at':'2026-11-27T01:02:00+00:00','status':'READ','handling':'ANSWER','assessment':{'report_type':'COMPLAINT'}},
            {'id':'o1','thread_id':'t','case_id':'c','reply_to_message_id':'info','at':'2026-11-27T01:00:10+00:00','status':'DELIVERED','handling':'ANSWER','assessment':{'report_type':'ENQUIRY'}}]
        states={x['message_id']:x['state'] for x in support_progress.snapshot(thread,messages,[],outs,[])['questions']}
        self.assertEqual(states,{'info':'ANSWERED','fault':'WAITING_CUSTOMER'})
        outs[1]['status']='ACCEPTED'
        states={x['message_id']:x['state'] for x in support_progress.snapshot(thread,messages,[],outs,[])['questions']}
        self.assertEqual(states['info'],'WAITING_DELIVERY')

if __name__=='__main__':unittest.main()
