"""Information-only automation: publication, grounding, revocation and exception boundaries."""
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive.ai import SupportAI
from belive.settings import Settings
from test_backend import FakeAI


class RoutineAI(FakeAI):
    def analyse(self,context,examples):
        result=super().analyse(context,examples)
        answers=context.get('approved_answers',[])
        return {**result,'approved_answer_id':answers[0]['id'] if answers else '',
                'match_confidence':0.99 if answers else 0,'request_language':'en'}


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ai=RoutineAI()
        self.s=Service(Path(self.tmp.name)/'test.db',self.ai)
        for prop,tenant in [('A','T'),('B','OTHER')]:
            self.cmd('condo',dict(id=prop,name='Fictional '+prop,rules='Fictional support guidance only.',confirmed=True))
            self.cmd('tenant',dict(id=tenant,condo_id=prop,unit_ref='ROOM',verified_by='QA staff',evidence='Fictional checked tenancy.',confirmed=True))
        self.token=self.cmd('portal_issue',{'tenant_id':'T'})['token']
        self.answer=self.faq()
        self.cmd('automation_settings',{'enabled':True})
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,name,p,key=None):return self.s.command(name,p,key or secrets.token_hex(12))
    def faq(self,**extra):
        return self.cmd('answer',dict(condo_id='A',question='How do I report a Wi-Fi connection problem?',
            answer='Use this conversation to tell support which devices are affected and when the Wi-Fi disconnects.',
            source='Fictional support handbook, approved by QA.',category='WIFI',language='en',confirmed=True,**extra))
    def intake(self,**extra):return self.s.portal_submit(self.token,{'title':'Wi-Fi question','description':'How do I report a Wi-Fi connection problem? Test '+secrets.token_hex(3),**extra},secrets.token_hex(12))
    def case(self,c):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',c['id'])
    def messages(self,c):return self.s.portal(self.token)['cases'][0]['conversation']
    def test_routine_answer_needs_no_staff_action_and_acceptance_is_information_only(self):
        c=self.intake();self.assertEqual(self.s.analyse(c['id'])['status'],'COMPLETED')
        current=self.case(c);self.assertEqual(current['status'],'FOLLOW_UP');self.assertFalse(current['owner'])
        reply=[m for m in self.messages(c) if m['sender']=='AI_SUPPORT']
        self.assertEqual([m['text'] for m in reply],[self.answer['answer']])
        self.assertEqual(current['analysis']['approved_answer_ref']['version'],1)
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':True},secrets.token_hex(12))
        current=self.case(c);self.assertEqual(current['status'],'ANSWERED');self.assertFalse(current['verification'])
        self.assertEqual(self.s.snapshot()['reports']['verified_closures'],0)
        self.assertEqual(self.s.snapshot()['examples'],[])
    def test_new_tenant_turn_restarts_ai_once_and_uses_current_question_as_evidence(self):
        c=self.intake();self.s.analyse(c['id']);key=secrets.token_hex(12)
        payload={'id':c['id'],'note':'Which devices should I include in the Wi-Fi report?'}
        self.s.portal_update(self.token,payload,key);self.s.portal_update(self.token,payload,key)
        self.assertEqual(self.case(c)['status'],'AI_PENDING');self.s.analyse(c['id'])
        self.assertEqual(self.ai.calls[-1][0]['case']['description'],payload['note'])
        self.assertEqual(len([m for m in self.messages(c) if m['sender']=='TENANT']),1)
        self.assertEqual(len([m for m in self.messages(c) if m['sender']=='AI_SUPPORT']),2)
        with self.assertRaises(ValueError):self.s.analyse(c['id'])
    def test_uncertainty_unknown_answer_and_unmatched_language_never_publish(self):
        original=self.ai.analyse
        for change in [{'uncertainty':True},{'approved_answer_id':'OTHER-FAQ'},{'request_language':'ms'},{'match_confidence':0.5},{'severity':'MEDIUM'},{'requires_human':True}]:
            c=self.intake(title='A new Wi-Fi question '+secrets.token_hex(3))
            self.ai.analyse=lambda ctx,ex,change=change:{**original(ctx,ex),**change}
            self.s.analyse(c['id']);self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
            with self.s.store.connect() as db:
                self.assertFalse(any(m['case_id']==c['id'] and m['sender']=='AI_SUPPORT' for m in self.s.store.all(db,'message')))
        self.ai.analyse=original
    def test_knowledge_is_scoped_to_the_verified_property(self):
        other=self.cmd('portal_issue',{'tenant_id':'OTHER'})['token']
        c=self.s.portal_submit(other,{'title':'Wi-Fi question','description':'How do I report a Wi-Fi connection problem?'},secrets.token_hex(12))
        self.s.analyse(c['id']);self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertEqual(self.ai.calls[-1][0]['approved_answers'],[])
    def test_source_update_or_policy_pause_during_generation_discards_result(self):
        original=self.ai.analyse
        for mutation in ['knowledge','policy']:
            self.cmd('automation_settings',{'enabled':True})
            c=self.intake(title='Wi-Fi question '+secrets.token_hex(3))
            def change(ctx,examples):
                result=original(ctx,examples)
                if mutation=='knowledge':
                    answer=ctx['approved_answers'][0]
                    self.cmd('answer',{**answer,'answer':'Corrected fictional answer. Ask support about affected devices.','confirmed':True})
                else:self.cmd('automation_settings',{'enabled':False})
                return result
            self.ai.analyse=change
            self.assertEqual(self.s.analyse(c['id'])['status'],'STALE')
            self.assertFalse(self.case(c)['draft'])
            self.ai.analyse=original
    def test_danger_and_explicit_human_requests_bypass_routine_ai(self):
        for text in ['There is smoke and sparks from the socket.','I want to speak to a human please.','The pipe is broken and leaking water.']:
            c=self.intake(description=text,title='Help '+secrets.token_hex(3))
            self.assertEqual(c['status'],'HUMAN_REVIEW')
        self.assertEqual(self.ai.calls,[])
    def test_unresolved_feedback_reopens_accepted_answer_for_staff(self):
        c=self.intake();self.s.analyse(c['id'])
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':True},secrets.token_hex(12))
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':False,'note':'That still does not answer my question.'},secrets.token_hex(12))
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
    def test_disabled_mode_and_operator_intake_preserve_reviewed_drafts(self):
        self.cmd('automation_settings',{'enabled':False});c=self.intake();self.s.analyse(c['id'])
        self.assertEqual(self.case(c)['status'],'AI_PENDING')
        self.cmd('automation_settings',{'enabled':True})
        c=self.cmd('intake',{'title':'Wi-Fi issue','description':'How do I report the connection issue?','tenant_id':'T'})
        self.s.analyse(c['id']);self.assertEqual(self.case(c)['status'],'AI_PENDING')
    def test_fresh_private_request_after_acceptance_does_not_reuse_old_outcome(self):
        payload={'title':'Wi-Fi question','description':'How do I report a Wi-Fi connection problem?'}
        first_key=secrets.token_hex(12)
        first=self.s.portal_submit(self.token,payload,first_key)
        self.s.analyse(first['id'])
        self.s.portal_feedback(self.token,{'id':first['id'],'resolved':True},secrets.token_hex(12))
        replay=self.s.portal_submit(self.token,payload,first_key)
        self.assertEqual(replay['id'],first['id'])
        fresh=self.s.portal_submit(self.token,payload,secrets.token_hex(12))
        self.assertNotEqual(fresh['id'],first['id'])
        self.assertEqual(fresh['status'],'AI_PENDING')
        self.assertEqual(self.case(first)['status'],'ANSWERED')
        repeated_active=self.s.portal_submit(self.token,payload,secrets.token_hex(12))
        self.assertEqual(repeated_active['id'],fresh['id'])
        self.s.analyse(fresh['id'])
        self.assertEqual(self.case(fresh)['status'],'FOLLOW_UP')
    def test_unresolved_router_note_has_receipt_and_replays_without_duplicate(self):
        c=self.intake();self.s.analyse(c['id'])
        key=secrets.token_hex(12)
        payload={'id':c['id'],'resolved':False,'note':'my router is not working'}
        self.s.portal_feedback(self.token,payload,key)
        self.s.portal_feedback(self.token,payload,key)
        current=self.case(c)
        self.assertEqual(current['status'],'HUMAN_REVIEW')
        messages=next(x for x in self.s.portal(self.token)['cases'] if x['id']==c['id'])['conversation']
        self.assertEqual(sum(m['sender']=='TENANT' and m['text']==payload['note'] for m in messages),1)
        self.assertEqual(sum(m['sender']=='SYSTEM' and 'staff queue' in m['text'] for m in messages),1)
        self.assertFalse(next(x for x in self.s.portal(self.token)['cases'] if x['id']==c['id'])['automatic_pending'])
        calls=len(self.ai.calls)
        self.s.portal_update(self.token,{'id':c['id'],'note':'The same issue affects two devices.'},secrets.token_hex(12))
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertEqual(len(self.ai.calls),calls)
    def test_staff_takeover_stops_automation(self):
        c=self.intake();self.s.analyse(c['id']);current=self.case(c)
        self.cmd('case_action',{'id':c['id'],'revision':current['revision'],'action':'acknowledge','owner':'QA operator'})
        self.s.portal_update(self.token,{'id':c['id'],'note':'Another question about the Wi-Fi report.'},secrets.token_hex(12))
        self.assertEqual(self.case(c)['status'],'IN_PROGRESS')
        self.assertEqual(len(self.ai.calls),1)
    def test_model_failure_routes_to_staff_and_sends_only_a_handover_receipt(self):
        c=self.intake();self.ai.fail=True;self.s.analyse(c['id'])
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertFalse(any(m['sender']=='AI_SUPPORT' for m in self.messages(c)))
        self.assertTrue(any(m['sender']=='SYSTEM' for m in self.messages(c)))
    def test_followup_runs_automatically_without_claiming_resolution(self):
        c=self.intake();self.s.analyse(c['id'])
        for _ in range(2):
            with self.s.store.connect() as db:
                current=self.s.store.get(db,'case',c['id']);current['followup_due']='2000-01-01T00:00:00+00:00';self.s.store.put(db,'case',current)
            self.s.tick()
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertTrue(any('Did this answer' in m['text'] for m in self.messages(c)))
    def test_no_permission_or_conflicting_version_cannot_approve_knowledge(self):
        with self.assertRaises(ValueError):self.cmd('answer',{**self.answer,'confirmed':False})
        with self.assertRaises(ValueError):self.cmd('answer_deactivate',{'id':self.answer['id'],'version':0})
        self.cmd('answer_deactivate',{'id':self.answer['id'],'version':1})
        c=self.intake();self.s.analyse(c['id']);self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
    def test_native_plan_schema_rejects_unknown_ids_before_publication(self):
        c=self.intake()
        with self.s.store.connect() as db:context=self.s.context(db,c)
        ai=SupportAI(Settings(),Path(self.tmp.name)/'memory')
        triage=dict(report_type='COMPLAINT',relevance='SUPPORT',category='WIFI',severity='LOW',summary='A routine Wi-Fi reporting question.',uncertainty=False,evidence='Wi-Fi')
        plan=dict(plan='Answer using the approved reporting guidance.',response='This free-form draft must never be auto-published.',requires_human=False,record_ids=[],approved_answer_id='FAKE',match_confidence=.99,request_language='en')
        with patch.object(ai,'generate',side_effect=[triage,plan]):
            with self.assertRaisesRegex(ValueError,'AI_UNKNOWN_ANSWER'):ai.analyse(context,[])
    def test_three_automatic_turns_then_staff_handover(self):
        c=self.intake();self.s.analyse(c['id'])
        for i in range(3):
            self.s.portal_update(self.token,{'id':c['id'],'note':'More information about the Wi-Fi report '+str(i)},secrets.token_hex(12))
            self.s.analyse(c['id'])
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertEqual(len([m for m in self.messages(c) if m['sender']=='AI_SUPPORT']),3)
    def test_manual_mode_still_uses_property_knowledge_without_publishing(self):
        self.cmd('automation_settings',{'enabled':False})
        c=self.intake();self.s.analyse(c['id'])
        self.assertEqual(self.ai.calls[-1][0]['verified_records'][0]['id'],self.answer['id'])
        self.assertEqual(self.case(c)['status'],'AI_PENDING')
    def test_failed_answer_text_overrides_an_accidental_resolved_button(self):
        c=self.intake();self.s.analyse(c['id'])
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':True,'note':"The answer didn't help and it is still not working."},secrets.token_hex(12))
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
    def test_failed_answer_in_a_reply_hands_over_without_another_ai_call(self):
        c=self.intake();self.s.analyse(c['id'])
        self.s.portal_update(self.token,{'id':c['id'],'note':'That did not help. My question is unresolved.'},secrets.token_hex(12))
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW');self.assertEqual(len(self.ai.calls),1)


if __name__=='__main__':unittest.main()
