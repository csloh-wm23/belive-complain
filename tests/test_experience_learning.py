import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive.ai import SupportAI
from belive.settings import Settings
from belive import learning,relevance
from test_backend import FakeAI


class ExperienceAI(FakeAI):
    def __init__(self):super().__init__();self.seen=[];self.hook=None
    def experience_reply(self,question,experience=None):
        self.seen.append((question,experience))
        if self.hook:self.hook()
        return experience['answer'] if experience else 'Yes, I can read your message. What would you like help with?'


class ExperienceLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ai=ExperienceAI()
        self.s=Service(Path(self.tmp.name)/'test.db',self.ai)
        self.wifi=self.approve('[TEST] Wi-Fi reporting','What details should I include when reporting Wi-Fi trouble?','Tell us which devices disconnect and when the connection drops.')
        self.water=self.approve('[TEST] Water pressure reporting','What information helps report low water pressure?','Tell us which taps are affected and when the water pressure drops.')
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,name,p):return self.s.command(name,p,secrets.token_hex(16))
    def case(self,cid):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',cid)
    def saved_run(self,run_id):
        with self.s.store.connect() as db:return self.s.store.get(db,'learning_run',run_id)
    def act(self,cid,name,**fields):return self.cmd('case_action',dict(id=cid,revision=self.case(cid)['revision'],action=name,**fields))
    def approve(self,title,question,answer):
        case=self.cmd('intake',dict(title=title,description='Fictional reporting example: '+question))
        self.act(case['id'],'acknowledge',owner='QA staff')
        self.act(case['id'],'verify_staff_close',note='Staff checked this fictional handling outcome.',confirmed=True)
        feedback=self.cmd('feedback',dict(id=case['id'],verdict='CORRECTED',text=answer,public_question=question,publish_public=True))
        return feedback

    def test_general_support_does_not_match_specific_lessons_or_get_default_tip(self):
        entry=self.cmd('learning_start',dict(category='OTHER',question='Can you read my message? I have an issue and do not know what to include.'))
        learning.execute(self.s,entry['id']);run=self.saved_run(entry['id'])
        self.assertEqual(run['mode'],'experience');self.assertIsNone(run['experience'])
        self.assertEqual(self.ai.seen[-1][1],None)
        self.assertEqual(self.s.snapshot()['learning_lesson'],'')
        with self.assertRaisesRegex(ValueError,'No relevant approved'):self.cmd('learning_improve',dict(id=entry['id'],confirmed=True))
        self.assertNotIn('room',run['baseline']['response'])

    def test_paraphrase_uses_only_matching_approved_experience_and_labels_sample(self):
        entry=self.cmd('learning_start',dict(category='WIFI',question='What should I tell you about my phone losing Wi-Fi every evening?'))
        learning.execute(self.s,entry['id']);run=self.saved_run(entry['id'])
        self.assertEqual(run['experience']['id'],self.wifi['id']);self.assertTrue(run['experience']['sample_data'])
        self.assertIn('Sample',run['experience']['provenance'])
        with self.assertRaises(ValueError):self.cmd('learning_improve',dict(id=entry['id'],confirmed=False))
        with self.assertRaisesRegex(ValueError,'as saved'):self.cmd('learning_improve',dict(id=entry['id'],confirmed=True,lesson='A new unapproved answer.'))
        self.cmd('learning_improve',dict(id=entry['id'],confirmed=True));learning.execute(self.s,entry['id'])
        final=self.saved_run(entry['id']);self.assertEqual(final['status'],'COMPLETE')
        self.assertEqual(final['improved']['experience_id'],self.wifi['id'])
        self.assertNotIn('score',final['improved']);self.assertNotIn('adopted_lesson_id',final)
        self.assertEqual(len(self.s.snapshot()['examples']),2)

    def test_unrelated_selected_experience_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'does not match'):
            self.cmd('learning_start',dict(question='How should I describe my Wi-Fi connection issue?',experience_id=self.water['id']))

    def test_revoked_experience_cannot_be_used_for_second_reply(self):
        entry=self.cmd('learning_start',dict(question='What details help report Wi-Fi trouble?'))
        learning.execute(self.s,entry['id'])
        self.cmd('feedback',dict(id=self.wifi['case_id'],verdict='REJECTED'))
        with self.assertRaisesRegex(ValueError,'revoked'):self.cmd('learning_improve',dict(id=entry['id'],confirmed=True))

    def test_revocation_during_generation_discards_stale_reply(self):
        entry=self.cmd('learning_start',dict(question='What details help report Wi-Fi trouble?'))
        self.ai.hook=lambda:self.cmd('feedback',dict(id=self.wifi['case_id'],verdict='REJECTED'))
        learning.execute(self.s,entry['id'])
        self.assertEqual(self.saved_run(entry['id'])['status'],'STALE');self.assertIsNone(self.saved_run(entry['id'])['baseline'])

    def test_general_submission_without_location_succeeds(self):
        receipt=self.s.website_submit(dict(title='General help question',description='Can you read my message? I need help understanding this page.',rental_property='',rental_unit=''),secrets.token_hex(16))
        self.assertFalse(self.case(receipt['id']).get('reported_location'))

    def test_operational_retrieval_does_not_mix_up_other_category_samples(self):
        with self.s.store.connect() as db:lessons=self.s.public_lessons(db)
        self.assertEqual(relevance.select('I have an issue and do not know what to include.',lessons),{})
        self.assertEqual(set(relevance.select('My Wi-Fi drops each night. What information helps?',lessons)),{self.wifi['id']})


class LocationPolicyTests(unittest.TestCase):
    def test_location_is_relevant_only_for_the_current_issue(self):
        self.assertEqual(relevance.location_scope('Can you read my message? I need help.'),'NONE')
        self.assertEqual(relevance.location_scope('What can I check on my phone for Wi-Fi?'),'NONE')
        self.assertEqual(relevance.location_scope('Are pets allowed in my building?'),'PROPERTY')
        self.assertEqual(relevance.location_scope('The air conditioner in my room stopped cooling.'),'AFFECTED_AREA')
        self.assertTrue(relevance.unnecessary_location('Which room are you staying in?','Are pets allowed in my building?'))
        self.assertFalse(relevance.unnecessary_location('Which property is this about?','Are pets allowed in my building?'))
        self.assertFalse(relevance.unnecessary_location('Which room has the air conditioner fault?','The air conditioner in my room stopped cooling.'))
        self.assertTrue(relevance.unnecessary_location('Please provide your room number.','Can you read my message?'))
        self.assertFalse(relevance.unnecessary_location('You do not need to provide your room number.','Can you read my message?'))
        self.assertTrue(relevance.unnecessary_location('If this happens in a specific room or shared area, mention that too, but we do not need a room number for shared issues.','My phone loses Wi-Fi in the evening. What should I record?'))
        self.assertTrue(relevance.unnecessary_location("We don't need your room number—just describe the location.",'My phone loses Wi-Fi in the evening. What should I record?'))
        self.assertTrue(relevance.unnecessary_location('Please provide your room number.','The shared washing machine stopped working.'))
        self.assertFalse(relevance.unnecessary_location('Which shared laundry area is affected?','The shared washing machine stopped working.'))

    def test_experience_agent_retries_an_unnecessary_location_request(self):
        ai=SupportAI(Settings(),Path('unused-test-memory'))
        good='Yes, I can read your message. What would you like help with?'
        review=dict(grounded=True,safe=True,uncertainty=False,unsupported_claims=[])
        with patch.object(ai,'generate',side_effect=[{'reply':'What is your room number?'},{'reply':good},review]) as generate:
            self.assertEqual(ai.experience_reply('Can you read my message?'),good)
            self.assertEqual(generate.call_count,3)

    def test_experience_agent_repairs_rejected_content_without_weakening_review(self):
        ai=SupportAI(Settings(),Path('unused-test-memory'))
        bad='We have repaired the washing machine.'
        good='Tell us the machine label, what happened and any error message.'
        rejected=dict(grounded=False,safe=True,uncertainty=False,unsupported_claims=['Unsupported exception'])
        accepted=dict(grounded=True,safe=True,uncertainty=False,unsupported_claims=[])
        with patch.object(ai,'generate',side_effect=[{'reply':bad},rejected,{'reply':good},accepted]):
            self.assertEqual(ai.experience_reply('What details should I include about a shared washing machine?'),good)

    def test_conversation_agent_retries_an_unnecessary_location_request(self):
        ai=SupportAI(Settings(),Path('unused-test-memory'))
        good='Yes, I can read it. What happened?'
        review=dict(grounded=True,safe=True,uncertainty=False,unsupported_claims=[])
        with patch.object(ai,'generate',side_effect=[dict(response='Which building and room are you in?',needs_staff=False,topics=['general_support']),dict(response=good,needs_staff=False,topics=['general_support']),review]):
            answer,topics=ai.conversational_reply([], 'Can you read my message?',{})
            self.assertEqual(answer,good);self.assertEqual(topics,['general_support'])
