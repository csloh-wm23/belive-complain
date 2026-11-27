"""Structural safety and routing tests; these fixtures are not model-reasoning evidence."""
import unittest
from unittest.mock import patch
import test_whatsapp as fixture
from test_whatsapp import plan,fixture_assessment

class AutonomyPolicyTests(unittest.TestCase):
    setUp=fixture.WhatsAppTests.setUp;tearDown=fixture.WhatsAppTests.tearDown
    rows=fixture.WhatsAppTests.rows;cmd=fixture.WhatsAppTests.cmd;incoming=fixture.WhatsAppTests.incoming;process=fixture.WhatsAppTests.process
    def medium(self):
        def assess(s,c):
            value=fixture_assessment(s,c);value.update(severity='MEDIUM',requires_human=True);return value
        self.assessment.side_effect=assess
    def test_missing_information_can_be_clarified_without_lowering_fault_priority(self):
        self.medium();self.reply.return_value={**plan(),'handling':'CLARIFY','decision_reason':'Need equipment identification.','reply':'What model is it, and what exactly is on the display?'}
        self.process(self.incoming('A shared appliance stopped with an unknown code.'))
        out=self.rows('wa_outgoing')[0]
        self.assertEqual((out['status'],out['delivery_kind']),('SIMULATED','CLARIFICATION'))
        self.assertEqual(self.rows('case')[0]['severity'],'MEDIUM');self.assertEqual(self.rows('wa_staff'),[])
        self.assertTrue(self.review.call_args.args[1]['clarification_only'])
    def test_source_supported_noninvasive_guidance_keeps_review_and_medium_priority(self):
        self.medium()
        self.reply.side_effect=[{**plan(),'handling':'RESEARCH','research':'TECHNICAL','search_query':'fictional QA model display manual'},
                                {**plan(),'handling':'ANSWER','decision_reason':'Retrieved official guidance supports these observations.','reply':'Read the displayed indicator without opening the equipment.','sources_used':['WEB-QA']}]
        with patch('belive.whatsapp_ai.research',return_value={'summary':'Fictional isolated official evidence for observing the display.','sources':[{'id':'WEB-QA','url':'https://www.samsung.com/support/','kind':'TECHNICAL','title':'QA fixture'}]}) as search:
            self.process(self.incoming('What does the display mean on model QA-100?'))
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['delivery_kind'],'REVIEWED_GUIDANCE');self.assertEqual(out['status'],'SIMULATED')
        self.assertEqual(self.rows('wa_staff'),[]);search.assert_called_once();self.review.assert_called()
    def test_unverified_medium_answer_does_not_become_automatic_guidance(self):
        self.medium();self.reply.return_value={**plan(),'handling':'ANSWER','reply':'Unverified proposed advice.'}
        self.process(self.incoming('The equipment has stopped.'))
        self.assertEqual(self.rows('wa_outgoing')[0]['delivery_kind'],'ACKNOWLEDGEMENT')
        self.assertNotIn('Unverified proposed advice',self.rows('wa_outgoing')[0]['text'])
        self.assertEqual(len(self.rows('wa_staff')),1)
    def test_review_revision_can_request_research_that_has_not_happened(self):
        self.medium()
        self.reply.side_effect=[
            {**plan(),'handling':'TEAM','needs_staff':True,'staff_question':'Confirm next action.','handover_reply':'Let me check with the team.'},
            {**plan(),'handling':'RESEARCH','research':'TECHNICAL','search_query':'fictional QA model manual'},
            {**plan(),'handling':'ANSWER','reply':'Read the indicator without opening the equipment.','sources_used':['WEB-QA']}]
        self.review.side_effect=[False,True]
        with patch('belive.whatsapp_ai.research',return_value={'summary':'Fictional official observation guidance.','sources':[{'id':'WEB-QA','url':'https://www.samsung.com/support/','kind':'TECHNICAL','title':'QA fixture'}]}) as search:
            self.process(self.incoming('The equipment stopped with an indicator.'))
        search.assert_called_once();self.assertFalse(self.reply.call_args_list[1].args[1]['research_attempted'])
        self.assertEqual(self.rows('wa_outgoing')[0]['delivery_kind'],'REVIEWED_GUIDANCE');self.assertEqual(self.rows('wa_staff'),[])
    def test_initial_uncertainty_is_preserved_but_fresh_verified_next_step_can_be_reviewed(self):
        def assess(s,c):
            value=fixture_assessment(s,c);value.update(severity='MEDIUM',uncertainty=True,requires_human=True,research='TECHNICAL',search_query='fictional QA official manual');return value
        self.assessment.side_effect=assess
        self.reply.return_value={**plan(),'handling':'ANSWER','reply':'Read the visible indicator; do not open the equipment.','sources_used':['WEB-QA']}
        with patch('belive.whatsapp_ai.research',return_value={'summary':'Fictional official safe observation.','sources':[{'id':'WEB-QA','url':'https://www.samsung.com/support/','kind':'TECHNICAL','title':'QA fixture'}]}) as search:
            self.process(self.incoming('What safe observation can I make while the cause is uncertain?'))
        out=self.rows('wa_outgoing')[0];search.assert_called_once()
        self.assertTrue(out['assessment']['uncertainty']);self.assertEqual(out['delivery_kind'],'REVIEWED_GUIDANCE')
        self.assertEqual(self.rows('wa_staff'),[]);self.review.assert_called()
    def test_high_risk_and_explicit_staff_requests_cannot_hide_as_clarification(self):
        for high in (True,False):
            def assess(s,c):
                value=fixture_assessment(s,c);value.update(severity='HIGH' if high else 'LOW',requires_human=high);return value
            self.assessment.side_effect=assess;self.reply.return_value={**plan(),'handling':'CLARIFY','reply':'What details can you share?'}
            self.process(self.incoming('There is a serious unresolved security issue.' if high else 'Please contact staff now.',customer='risk-'+str(high)))
            out=self.rows('wa_outgoing')[0];self.assertEqual(out['delivery_kind'],'ACKNOWLEDGEMENT');self.assertEqual(out['handling'],'TEAM')
    def test_on_site_work_goes_to_configured_maintenance_without_general_staff_relay(self):
        self.cmd('routing_settings',departments={'MAINTENANCE':'Fictional maintenance intake','WIFI':'Fictional helpdesk'},confirmed=True)
        self.reply.return_value={**plan(),'handling':'TEAM','needs_staff':True,'needs_maintenance':True,'staff_question':'Inspect the failed shared equipment once its location is confirmed.'}
        self.process(self.incoming('The equipment needs physical inspection.'))
        request=self.rows('wa_staff')[0];jobs=self.rows('outbox')
        self.assertEqual(request['assigned_team'],'Fictional maintenance intake');self.assertTrue(request['routing_confirmed'])
        work=[j for j in jobs if j['kind']=='STAFF_WORK_ORDER'];self.assertEqual(len(work),1)
        self.assertEqual(work[0]['target'],'Fictional maintenance intake');self.assertEqual(work[0]['status'],'NEEDS_DETAILS')
        self.assertFalse(any(j['target']=='Fictional helpdesk' for j in jobs))
        self.assertFalse(any(j['kind']=='STAFF_ALERT' for j in jobs))
    def test_supplied_location_makes_maintenance_ready_and_priority_follows_severity(self):
        self.medium();self.reply.return_value={**plan(),'handling':'TEAM','needs_staff':True,'needs_maintenance':True,'staff_question':'Inspect the damaged equipment.'}
        self.process(self.incoming('The equipment is physically damaged.'));r=self.rows('wa_staff')[0]
        self.reply.return_value={**plan(),'handling':'TEAM','needs_staff':True,'needs_maintenance':True,'related_request_id':r['id'],'staff_question':'Inspect the damaged equipment at the supplied location.','maintenance_property':'Fictional House QA','maintenance_unit':'T-01','maintenance_location_complete':True}
        def assess(s,c):
            value=fixture_assessment(s,c);value.update(severity='HIGH',requires_human=True);return value
        self.assessment.side_effect=assess
        self.process(self.incoming('Fictional House QA, room T-01; this is a serious access issue.'))
        r=self.rows('wa_staff')[0];active=[n for n in self.rows('outbox') if n['status'] not in {'CANCELLED','REJECTED'}]
        self.assertEqual((r['severity'],r['priority'],r['intake_state']),('HIGH',3,'READY_FOR_MAINTENANCE'))
        self.assertEqual(len(active),1);self.assertEqual(active[0]['status'],'PENDING_APPROVAL')
        self.assertIn('T-01',active[0]['text']);self.assertEqual(active[0]['support_request_id'],r['id'])
    def test_public_help_can_continue_for_same_issue_while_maintenance_request_stays_open(self):
        self.medium();self.reply.return_value={**plan(),'handling':'TEAM','needs_staff':True,'needs_maintenance':True,'staff_question':'Inspect the fault.'}
        first=self.incoming('The shared equipment stopped.');self.process(first)
        request=self.rows('wa_staff')[0];job_count=len(self.rows('outbox'))
        self.reply.side_effect=[
            {**plan(),'handling':'RESEARCH','research':'TECHNICAL','search_query':'fictional QA manual'},
            {**plan(),'handling':'TEAM','needs_staff':True,'needs_maintenance':True,'related_request_id':request['id'],'reply':'You can read the visible indicator without opening the equipment.','staff_question':'Inspection remains pending.','sources_used':['WEB-QA']}]
        with patch('belive.whatsapp_ai.research',return_value={'summary':'Fictional safe observation.','sources':[{'id':'WEB-QA','url':'https://www.samsung.com/support/','kind':'TECHNICAL','title':'QA fixture'}]}):
            self.process(self.incoming('Can I check anything safely while waiting?'))
        out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['delivery_kind'],'REVIEWED_TEAM_GUIDANCE');self.assertIn('visible indicator',out['text'])
        self.assertEqual(self.rows('wa_staff')[0]['status'],'OPEN');self.assertEqual(sum(j['status'] not in {'CANCELLED','REJECTED'} for j in self.rows('outbox')),job_count)
        self.assertFalse(out['continues_request']);self.assertEqual(out['reply_to_message_id'],request['origin_message_id'])
        self.assertFalse(self.review.call_args.args[1]['acknowledgement_only'])
    def test_ai_answered_issue_without_staff_guidance_does_not_break_next_customer_question(self):
        self.medium();self.reply.return_value={**plan(),'handling':'TEAM','needs_staff':True,'staff_question':'Review the fault.'}
        self.process(self.incoming('A fault needs further information.'))
        request=self.rows('wa_staff')[0]
        with self.s.store.connect() as db:
            request.update(status='ANSWERED',progress='WAITING_CUSTOMER');request.pop('guidance',None);self.s.store.put(db,'wa_staff',request)
        self.reply.return_value={**plan(),'handling':'CLARIFY','reply':'What is the new question about?'}
        self.process(self.incoming('I have a different issue to report.'))
        self.assertEqual(self.rows('wa_outgoing')[0]['status'],'SIMULATED')
        self.assertEqual(self.reply.call_args.args[1]['staff_guidance'],[])
        self.assertFalse(any(t['status']=='PROCESSING' for t in self.rows('wa_turn')))
