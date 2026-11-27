"""Per-topic closure, delivery races and chat continuity; no real external sends."""
import unittest
from belive import whatsapp as wa
from test_whatsapp import plan
import test_whatsapp_issues as fixtures

class CompletionTests(unittest.TestCase):
    setUp=fixtures.IssueTests.setUp;tearDown=fixtures.IssueTests.tearDown
    rows=fixtures.IssueTests.rows;cmd=fixtures.IssueTests.cmd;incoming=fixtures.IssueTests.incoming;process=fixtures.IssueTests.process
    waiting=fixtures.IssueTests.waiting;guidance=fixtures.IssueTests.guidance
    def finish(self,r,**extra):
        return self.cmd('wa_staff_complete',thread_id=r['thread_id'],request_id=r['id'],request_revision=r['revision'],outcome='TEST_COMPLETED',note='Authorised fictional test completed; no actual repair occurred.',confirmed=True,**extra)
    def test_finishes_only_selected_issue_and_cancels_its_unsent_notice(self):
        _,a=self.waiting();_,b=self.waiting('The shared washer needs inspection.','Confirm inspection arrangements.')
        before={k:len(self.rows(k)) for k in ('feedback','reply_learning')}
        self.finish(a)
        current={r['id']:r for r in self.rows('wa_staff')}
        self.assertEqual(current[a['id']]['status'],'CLOSED');self.assertEqual(current[b['id']]['status'],'OPEN')
        self.assertFalse(current[a['id']]['resolution_confirmed'])
        notices={n['id']:n for n in self.rows('outbox')}
        self.assertEqual(notices[current[a['id']]['notification_id']]['status'],'CANCELLED')
        self.assertEqual(notices[current[b['id']]['notification_id']]['status'],'PENDING_APPROVAL')
        self.assertEqual(before,{k:len(self.rows(k)) for k in before})
        self.assertNotEqual(self.rows('case')[0]['status'],'CLOSED')
    def test_closing_cancels_queued_guidance_and_rejects_old_staff_form(self):
        _,r=self.waiting();self.guidance(r);r=self.rows('wa_staff')[0]
        self.finish(r);wa.process_thread(self.s,r['thread_id'])
        self.assertFalse(any(t['status']=='PENDING' for t in self.rows('wa_turn')))
        self.assertEqual(len(self.rows('wa_outgoing')),1)
        with self.assertRaises(ValueError):self.guidance(r)
    def test_unconfirmed_send_blocks_closure(self):
        _,r=self.waiting()
        with self.s.store.connect() as db:
            o=self.s.store.all(db,'wa_outgoing')[0];o.update(request_id=r['id'],status='UNKNOWN');self.s.store.put(db,'wa_outgoing',o)
        with self.assertRaises(ValueError):self.finish(r)
        self.assertEqual(self.rows('wa_staff')[0]['status'],'OPEN')
    def test_new_customer_question_still_receives_independent_reply(self):
        _,r=self.waiting();self.finish(r)
        self.reply.return_value={**plan(),'reply':'What would you like help with next?'}
        self.process(self.incoming('I have a different question.'))
        self.assertEqual(self.rows('wa_outgoing')[0]['status'],'SIMULATED')
        self.assertEqual(self.rows('wa_staff')[0]['status'],'CLOSED')
    def test_unconfirmed_initial_ack_without_request_id_also_blocks_closure(self):
        _,r=self.waiting()
        with self.s.store.connect() as db:
            o=self.s.store.all(db,'wa_outgoing')[0];o.update(request_id=None,status='UNKNOWN');self.s.store.put(db,'wa_outgoing',o)
        with self.assertRaises(ValueError):self.finish(r)
    def test_customer_can_reopen_same_issue_without_old_guidance_becoming_current(self):
        _,r=self.waiting();self.finish(r)
        self.reply.return_value={**plan(),'needs_staff':True,'related_request_id':r['id'],'staff_question':'The customer reports the same issue is still unresolved.'}
        self.process(self.incoming('That same problem is still unresolved.'))
        self.assertEqual(self.rows('wa_staff')[0]['id'],r['id']);self.assertEqual(self.rows('wa_staff')[0]['status'],'OPEN')

if __name__=='__main__':unittest.main()
