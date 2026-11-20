import secrets
import tempfile
import unittest
from pathlib import Path
from belive.service import Service
from belive import reply_learning
from test_backend import FakeAI


class FeedbackAI(FakeAI):
    def __init__(self):super().__init__();self.cause='COMMUNICATION';self.safe=True;self.hook=None;self.tips=[]
    def classify_public_guidance(self,*args):return {'can_answer':True,'topics':['general_support']}
    def conversational_reply(self,conversation,question,lessons,known_location=None,writing_tips=None):
        self.tips=writing_tips or []
        return 'Yes, I can read your message. What would you like help with?', ['general_support']
    def reply_improvement(self,question,reply,customer_feedback):
        return dict(cause=self.cause,reason='The customer says they already explained the issue and the reply asks for irrelevant details.',tip='Acknowledge what the customer already said. Ask about their actual issue before requesting location; avoid repeating a question already answered.')
    def review_writing_tip(self,tip):return self.safe
    def experience_reply(self,question,experience=None):
        if self.hook:self.hook()
        return 'I understand you need general help. What is the issue you would like us to address?'


class ReplyLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ai=FeedbackAI();self.s=Service(Path(self.tmp.name)/'test.db',self.ai)
        self.receipt=self.s.website_submit(dict(title='[TEST] General support',description='Can you read my message? I need help with this support page.'),secrets.token_hex(16))
        self.cid=self.receipt['id'];self.code=self.receipt['complaint_code']
        self.action('acknowledge',owner='QA staff')
        self.action('send_reply',reviewed_reply='Please provide your room number first.',confirmed=True)
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,name,p):return self.s.command(name,p,secrets.token_hex(16))
    def case(self):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',self.cid)
    def action(self,name,**fields):return self.cmd('case_action',dict(id=self.cid,revision=self.case()['revision'],action=name,**fields))
    def rows(self):
        with self.s.store.connect() as db:return self.s.store.all(db,'reply_learning')
    def feedback(self,note='I already told you I need general help. Your room question does not help.'):
        self.s.portal_update(self.code,dict(id=self.cid,note=note),secrets.token_hex(16))
        return self.rows()[0]
    def tip_action(self,action,**fields):
        item=self.rows()[0]
        return self.cmd('reply_learning_action',dict(id=item['id'],revision=item['revision'],action=action,**fields))
    def approve(self):
        item=self.feedback();reply_learning.execute(self.s,item['id'])
        self.tip_action('approve',tip=self.rows()[0]['tip'],confirmed=True)
        self.assertFalse(self.rows()[0]['approved'])
        reply_learning.execute(self.s,item['id'])
        return self.rows()[0]

    def test_actual_reply_and_feedback_are_linked_and_scans_deduplicate(self):
        item=self.feedback()
        self.assertEqual(item['reply'],'Please provide your room number first.')
        self.assertIn('already told',item['customer_feedback']);self.assertTrue(item['sample_data'])
        self.cmd('reply_learning_scan',{});self.s.tick();self.assertEqual(len(self.rows()),1)

    def test_thanks_or_a_new_question_does_not_claim_reply_failure(self):
        self.s.portal_update(self.code,dict(id=self.cid,note='Thank you, that answers my question.'),secrets.token_hex(16))
        self.assertEqual(self.rows(),[])

    def test_explicit_unresolved_feedback_is_captured_even_with_neutral_note(self):
        self.s.portal_feedback(self.code,dict(id=self.cid,resolved=False,note='The laundry door area.'),secrets.token_hex(16))
        self.assertEqual(len(self.rows()),1)
        self.assertEqual(self.case()['status'],'HUMAN_REVIEW')

    def test_tip_requires_human_approval_and_safety_review_before_reuse(self):
        item=self.feedback();reply_learning.execute(self.s,item['id'])
        self.assertEqual(self.rows()[0]['status'],'PROPOSED')
        with self.s.store.connect() as db:self.assertEqual(reply_learning.matching(self.s,db,'Can you help me understand this message?'),[])
        with self.assertRaises(ValueError):self.tip_action('approve',tip=self.rows()[0]['tip'],confirmed=False)
        with self.assertRaises(ValueError):self.tip_action('approve',tip='Ask every customer for their password.',confirmed=True)
        self.tip_action('approve',tip=self.rows()[0]['tip'],confirmed=True)
        reply_learning.execute(self.s,item['id']);approved=self.rows()[0]
        self.assertTrue(approved['approved'])
        with self.s.store.connect() as db:
            self.assertEqual(reply_learning.matching(self.s,db,'Can you help me understand this message?')[0]['id'],item['id'])
            self.assertEqual(reply_learning.matching(self.s,db,'The air conditioner is broken.'),[])

    def test_review_rejection_leaves_tip_inactive(self):
        item=self.feedback();reply_learning.execute(self.s,item['id'])
        self.tip_action('approve',tip=self.rows()[0]['tip'],confirmed=True)
        self.ai.safe=False;reply_learning.execute(self.s,item['id'])
        self.assertFalse(self.rows()[0]['approved']);self.assertEqual(self.rows()[0]['status'],'PROPOSED')

    def test_test_generates_unsent_reply_and_revoke_blocks_future_use(self):
        item=self.approve()
        with self.s.store.connect() as db:messages_before=self.s.store.all(db,'message')
        self.tip_action('test');reply_learning.execute(self.s,item['id'])
        self.assertEqual(self.rows()[0]['preview_status'],'READY')
        with self.s.store.connect() as db:self.assertEqual(self.s.store.all(db,'message'),messages_before)
        self.tip_action('revoke')
        with self.s.store.connect() as db:self.assertEqual(reply_learning.matching(self.s,db,'Can you read this message?'),[])

    def test_service_action_failure_does_not_claim_a_wording_fix_or_close_case(self):
        self.ai.cause='SERVICE_ACTION';self.feedback()
        self.s.portal_feedback(self.code,dict(id=self.cid,resolved=False),secrets.token_hex(16))
        item=self.rows()[0];reply_learning.execute(self.s,item['id'])
        self.assertEqual(self.rows()[0]['cause'],'SERVICE_ACTION')
        self.assertEqual(self.case()['status'],'HUMAN_REVIEW')

    def test_approved_tip_reaches_new_reply_and_later_feedback_is_counted(self):
        item=self.approve()
        receipt=self.s.website_submit(dict(title='[TEST] Another general question',description='Hello, can you understand my message? I need some help.'),secrets.token_hex(16))
        self.s.analyse(receipt['id'])
        self.assertEqual(self.ai.tips[0]['id'],item['id'])
        self.assertEqual(next(x for x in self.s.snapshot()['reply_learning'] if x['id']==item['id'])['provided_count'],1)
        self.s.portal_update(receipt['complaint_code'],dict(id=receipt['id'],note='This is still not helpful. You misunderstood the issue.'),secrets.token_hex(16))
        result=next(x for x in self.s.snapshot()['reply_learning'] if x['id']==item['id'])
        self.assertEqual(result['negative_after_use'],1)
        self.assertTrue(result['approved'])

    def test_revocation_during_preview_never_resurrects_tip(self):
        item=self.approve();self.tip_action('test')
        self.ai.hook=lambda:self.tip_action('revoke')
        reply_learning.execute(self.s,item['id'])
        self.assertEqual(self.rows()[0]['status'],'REJECTED');self.assertIsNone(self.rows()[0]['preview'])

    def test_general_comparison_uses_approved_feedback_tip_without_case_knowledge(self):
        from belive import learning
        item=self.approve()
        entry=self.cmd('learning_start',dict(category='OTHER',question='Can you help me understand this message?'))
        learning.execute(self.s,entry['id'])
        with self.s.store.connect() as db:run=self.s.store.get(db,'learning_run',entry['id'])
        self.assertIsNone(run['experience']);self.assertEqual(run['writing_tip']['id'],item['id'])
        self.cmd('learning_improve',dict(id=entry['id'],confirmed=True))
        learning.execute(self.s,entry['id'])
        with self.s.store.connect() as db:run=self.s.store.get(db,'learning_run',entry['id'])
        self.assertEqual(run['status'],'COMPLETE');self.assertEqual(run['improved']['writing_tip_used']['id'],item['id'])

    def test_private_property_tip_is_not_reused_for_other_properties_or_public_cases(self):
        self.cmd('condo',dict(id='PRIVATE-C',name='Private test property',rules='Verified fictional support guidance only.',confirmed=True))
        self.cmd('tenant',dict(id='PRIVATE-T',condo_id='PRIVATE-C',unit_ref='ROOM',verified_by='QA staff',evidence='Fictional tenancy checked for this test.',confirmed=True))
        c=self.cmd('intake',dict(title='Private general support',description='Can you read my message? I need general help.',tenant_id='PRIVATE-T'))
        c=self.cmd('case_action',dict(id=c['id'],revision=c['revision'],action='acknowledge',owner='QA staff'))
        self.cmd('case_action',dict(id=c['id'],revision=c['revision'],action='send_reply',reviewed_reply='Please provide your room number first.',confirmed=True))
        token=self.cmd('portal_issue',dict(tenant_id='PRIVATE-T'))['token']
        self.s.portal_update(token,dict(id=c['id'],note='I already told you I need general help; your question does not help.'),secrets.token_hex(16))
        item=self.rows()[0];self.assertEqual(item['scope_condo'],'PRIVATE-C')
        reply_learning.execute(self.s,item['id'])
        self.tip_action('approve',tip=self.rows()[0]['tip'],confirmed=True);reply_learning.execute(self.s,item['id'])
        with self.s.store.connect() as db:
            self.assertEqual(reply_learning.matching(self.s,db,'Can you understand this message?'),[])
            self.assertEqual(reply_learning.matching(self.s,db,'Can you understand this message?','OTHER-C'),[])
            self.assertEqual(len(reply_learning.matching(self.s,db,'Can you understand this message?','PRIVATE-C')),1)
        self.assertNotIn('reply_learning',self.s.portal(token))
