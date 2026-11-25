"""Local approved learning is revalidated before WhatsApp generation commit and delivery."""
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive import whatsapp as wa
from test_backend import FakeAI
from test_whatsapp import fixture_assessment, plan


class WhatsAppLearningRevalidationTests(unittest.TestCase):
    question='What details should I include when reporting the shared washing machine?'

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'case.db',FakeAI())
        self.patches=[patch('belive.whatsapp_ai.reply',return_value=plan()),patch('belive.whatsapp_ai.review',return_value=True),
            patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment),
            patch('belive.whatsapp.request_json',side_effect=AssertionError('No external sends'))]
        self.reply,self.review,self.assessor,self.net=[p.start() for p in self.patches]

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def command(self,name,**payload):return self.s.command(name,payload,secrets.token_hex(16))

    def rows(self,kind):
        with self.s.store.connect() as db:return self.s.store.all(db,kind)

    def tip(self):
        case=self.command('intake',title='[TEST] Washer writing lesson',description='Fictional reviewed writing example: '+self.question)
        item=dict(id='RLF-local-washer',case_id=case['id'],question=self.question,tip='Acknowledge the washer concern and ask for the exact error display.',
                  category='MAINTENANCE',scope_condo=None,revision=1,approved=True,status='APPROVED')
        with self.s.store.connect() as db:self.s.store.put(db,'reply_learning',item)
        return item

    def experience(self):
        case=self.command('intake',title='[TEST] Washer reporting',description='Fictional reviewed reporting example: '+self.question)
        self.command('case_action',id=case['id'],revision=case['revision'],action='acknowledge',owner='QA staff')
        with self.s.store.connect() as db:case=self.s.store.get(db,'case',case['id'])
        self.command('case_action',id=case['id'],revision=case['revision'],action='verify_staff_close',
                     note='Staff verified this fictional reporting outcome.',confirmed=True)
        return self.correct(case['id'],'Tell us which shared washer is affected and what its display shows.')

    def correct(self,cid,answer):
        return self.command('feedback',id=cid,verdict='CORRECTED',text=answer,public_question=self.question,publish_public=True)

    def queue(self,text=None):
        intake=self.command('wa_simulate',customer='local-learning-qa',text=text or self.question)
        with patch('belive.whatsapp.deliver'):wa.process_thread(self.s,intake['thread_id'])
        return intake,self.rows('wa_outgoing')[0]

    def assert_stale(self,out):
        result=wa.deliver(self.s,out['id'])
        self.assertEqual(result['status'],'SUPERSEDED')
        self.assertTrue(any(t['status']=='PENDING' for t in self.rows('wa_turn')))
        self.assertFalse(any(m['direction']=='AI' for m in self.rows('wa_message')))
        self.net.assert_not_called()

    def test_revoked_local_tip_supersedes_queue_and_reprocesses_without_it(self):
        tip=self.tip();intake,out=self.queue()
        self.assertIn('tip:'+tip['id'],out['local_learning_versions'])
        self.assertEqual(self.reply.call_args.args[1]['reviewed_writing_tips'][0]['id'],tip['id'])
        self.command('reply_learning_action',id=tip['id'],revision=tip['revision'],action='revoke')
        self.assert_stale(out)
        wa.process_thread(self.s,intake['thread_id'])
        self.assertEqual(self.rows('wa_outgoing')[0]['status'],'SIMULATED')
        self.assertEqual(self.reply.call_args.args[1]['reviewed_writing_tips'],[])
        self.assertEqual(self.rows('wa_outgoing')[0]['local_learning_versions'],{})

    def test_corrected_local_tip_cannot_send_the_previous_queue(self):
        tip=self.tip();_,out=self.queue()
        with self.s.store.connect() as db:
            tip.update(tip='Ask for the washer display without assuming tenant fault.',revision=2)
            self.s.store.put(db,'reply_learning',tip)
        self.assert_stale(out)

    def test_rejected_approved_experience_cannot_send_the_previous_queue(self):
        lesson=self.experience();_,out=self.queue()
        self.assertIn('experience:'+lesson['id'],out['local_learning_versions'])
        self.assertEqual(self.reply.call_args.args[1]['approved_experiences'][0]['id'],lesson['id'])
        self.command('feedback',id=lesson['case_id'],verdict='REJECTED')
        self.assert_stale(out)

    def test_corrected_approved_experience_supersedes_old_queue_and_uses_new_answer(self):
        lesson=self.experience();intake,out=self.queue()
        corrected=self.correct(lesson['case_id'],'Report the washer label and display text; do not attempt a repair.')
        self.assert_stale(out)
        wa.process_thread(self.s,intake['thread_id'])
        latest=self.rows('wa_outgoing')[0]
        self.assertEqual(latest['status'],'SIMULATED')
        supplied=self.reply.call_args.args[1]['approved_experiences']
        self.assertEqual([x['id'] for x in supplied],[corrected['id']])
        self.assertEqual(supplied[0]['answer'],corrected['text'])
        self.assertNotIn('experience:'+lesson['id'],latest['local_learning_versions'])

    def test_unchanged_local_tip_and_experience_permit_simulated_delivery(self):
        tip=self.tip();lesson=self.experience();_,out=self.queue()
        self.assertEqual(set(out['local_learning_versions']),{'tip:'+tip['id'],'experience:'+lesson['id']})
        self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SIMULATED')
        self.assertEqual(len([m for m in self.rows('wa_message') if m['direction']=='AI']),1)
        self.net.assert_not_called()

    def test_tip_revoked_during_generation_discards_draft_before_commit(self):
        tip=self.tip();contexts=[]
        def generate(service,context):
            contexts.append(context)
            if len(contexts)==1:
                self.command('reply_learning_action',id=tip['id'],revision=tip['revision'],action='revoke')
                return {**plan(),'reply':'This obsolete first draft must not be committed.'}
            return {**plan(),'reply':'Please describe the washer display.'}
        self.reply.side_effect=generate
        _,out=self.queue()
        self.assertEqual(len(contexts),2);self.assertTrue(contexts[0]['reviewed_writing_tips'])
        self.assertEqual(contexts[1]['reviewed_writing_tips'],[])
        self.assertEqual(out['text'],'Please describe the washer display.')
        self.assertEqual(len(self.rows('wa_outgoing')),1)
        self.assertTrue(any(t['status']=='SUPERSEDED' for t in self.rows('wa_turn')))

    def test_experience_corrected_during_generation_uses_only_current_approved_answer(self):
        lesson=self.experience();contexts=[];replacement=[]
        def generate(service,context):
            contexts.append(context)
            if len(contexts)==1:
                replacement.append(self.correct(lesson['case_id'],'Describe the display and wait for staff before repair.'))
                return {**plan(),'reply':'This draft used the old experience.'}
            return {**plan(),'reply':'Please describe the washer display and avoid repairs.'}
        self.reply.side_effect=generate
        _,out=self.queue()
        self.assertEqual(len(contexts),2)
        self.assertEqual(contexts[1]['approved_experiences'][0]['id'],replacement[0]['id'])
        self.assertNotIn('experience:'+lesson['id'],out['local_learning_versions'])
        self.assertEqual(len(self.rows('wa_outgoing')),1)

    def test_staff_priority_edit_still_wins_over_local_learning_reprocess(self):
        tip=self.tip();intake,out=self.queue()
        with self.s.store.connect() as db:case=self.s.store.get(db,'case',intake['case_id'])
        self.command('case_action',id=case['id'],revision=case['revision'],action='assess',category='MAINTENANCE',severity='HIGH',
                     note='Staff confirmed serious impact requiring immediate investigation.')
        self.command('reply_learning_action',id=tip['id'],revision=tip['revision'],action='revoke')
        self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SUPERSEDED')
        self.assertFalse(any(t['status']=='PENDING' for t in self.rows('wa_turn')))
        self.net.assert_not_called()

    def test_urgent_acknowledgement_never_depends_on_local_learning(self):
        self.tip();self.experience()
        with patch('belive.whatsapp._local_learning_versions',side_effect=AssertionError('No urgent learning snapshot')) as snapshot, \
             patch('belive.whatsapp._local_learning_stale',side_effect=AssertionError('No urgent learning revalidation')) as validate, \
             patch('belive.experience_learning.experiences',side_effect=AssertionError('No urgent experience retrieval')) as lessons:
            _,out=self.queue('Smoke and sparks are coming from the washer.')
            self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SIMULATED')
        self.assertEqual(out['local_learning_versions'],{})
        snapshot.assert_not_called();validate.assert_not_called();lessons.assert_not_called()
        self.reply.assert_not_called();self.net.assert_not_called()


if __name__=='__main__':unittest.main()
