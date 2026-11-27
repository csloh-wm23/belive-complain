"""WhatsApp classification, level explanation, routing and substantive-reply boundaries."""
import secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive import whatsapp as wa, whatsapp_triage as triage
from test_backend import FakeAI
from test_whatsapp import fixture_assessment,plan

class WhatsAppTriageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'case.db',FakeAI())
        self.patches=[patch('belive.whatsapp_ai.reply',return_value=plan()),patch('belive.whatsapp_ai.review',return_value=True),
            patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment),patch('belive.whatsapp.request_json',side_effect=AssertionError('No Meta calls'))]
        self.reply,self.review,self.assessor,self.net=[p.start() for p in self.patches]
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def rows(self,kind):
        with self.s.store.connect() as db:return self.s.store.all(db,kind)
    def command(self,name,**p):return self.s.command(name,p,secrets.token_hex(16))
    def incoming(self,text='The shared washer stopped halfway through the cycle.'):
        r=self.command('wa_simulate',customer='qa-triage',text=text);wa.process_thread(self.s,r['thread_id']);return r
    def prepared(self,severity='MEDIUM',uncertain=False):
        a=fixture_assessment(None,{'conversation':[{'role':'CUSTOMER','text':'The shared washer stopped halfway through the cycle.'}]})
        a.update(category='MAINTENANCE',severity=severity,uncertainty=uncertain,summary='A shared washer stopped mid-cycle.',
                 level_reason='A physical appliance fault needs investigation and staff action.',requires_human=severity!='LOW' or uncertain)
        self.assessor.side_effect=None;self.assessor.return_value=a
    def test_moderate_is_assessed_and_routed_with_private_ai_assistance(self):
        self.prepared();self.command('routing_settings',departments={'MAINTENANCE':'Fictional maintenance desk'},confirmed=True)
        self.reply.return_value={**plan(),'reply':'Please report the laundry room and error display.','needs_staff':True,'staff_question':'Confirm the safe maintenance arrangements.','needs_maintenance':True}
        self.incoming();case=self.rows('case')[0];out=self.rows('wa_outgoing')[0]
        self.assertEqual((case['category'],case['severity'],case['staff_destination']),('MAINTENANCE','MEDIUM','Fictional maintenance desk'))
        self.assertEqual(out['assessment']['complaint_level'],'MODERATE');self.assertTrue(out['assessment']['level_reason'])
        self.assertEqual(out['delivery_kind'],'ACKNOWLEDGEMENT');self.assertIn('laundry room',out['staff_draft'])
        self.assertNotIn('laundry room',out['text']);self.assertEqual(case['status'],'HUMAN_REVIEW');self.net.assert_not_called()
    def test_high_draft_is_not_sent_as_automatic_advice(self):
        self.prepared('HIGH');self.reply.return_value={**plan(),'reply':'This proposed assistance remains private.'}
        self.incoming();out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['assessment']['complaint_level'],'HIGH');self.assertIn('as a priority',out['text'])
        self.assertNotIn('remains private',out['text']);self.assertEqual(out['staff_draft'],'This proposed assistance remains private.')
    def test_simple_enquiry_is_answered_without_becoming_a_staff_task(self):
        self.prepared('LOW');self.assessor.return_value.update(report_type='ENQUIRY',requires_human=False)
        self.incoming('What information should a maintenance report include?');out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['delivery_kind'],'SIMPLE');self.assertEqual(out['text'],self.reply.return_value['reply'])
        self.assertEqual(self.rows('wa_staff'),[]);self.assertEqual(out['assessment']['report_type'],'ENQUIRY')
    def test_uncertain_low_assessment_is_not_a_simple_automatic_reply(self):
        self.prepared('LOW',True);self.incoming();out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['assessment']['complaint_level'],'MODERATE');self.assertEqual(out['delivery_kind'],'ACKNOWLEDGEMENT')
    def test_reviewed_low_followup_during_open_handover_is_sent_without_closing_staff_task(self):
        first=self.incoming('Can you help with my Wi-Fi?')
        with self.s.store.connect() as db:
            thread=self.s.store.get(db,'wa_thread',first['thread_id']);thread['state']='WAITING_STAFF';self.s.store.put(db,'wa_thread',thread)
            case=self.s.store.get(db,'case',first['case_id']);case.update(status='HUMAN_REVIEW',handoff=True);self.s.store.put(db,'case',case)
            self.s.store.put(db,'wa_staff',{'id':'WAS-pending-test','thread_id':thread['id'],'case_id':case['id'],'status':'OPEN','question':'Existing request remains open.'})
        self.reply.return_value={**plan(),'reply':'Hi! What would you like to ask?'}
        self.incoming('Hi')
        out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['delivery_kind'],'ACKNOWLEDGEMENT');self.assertEqual(out['status'],'SIMULATED')
        self.assertEqual(out['text'],'Hi! What would you like to ask?');self.assertTrue(self.rows('case')[0]['handoff'])
        self.assertEqual(self.rows('case')[0]['status'],'HUMAN_REVIEW')
        self.assertEqual(len(self.rows('wa_staff')),1);self.assertEqual(self.rows('wa_staff')[0]['status'],'OPEN')
        self.review.assert_called();self.net.assert_not_called()
    def test_danger_precedes_all_normal_models_and_retrieval(self):
        with patch('belive.company_sop.retrieve',side_effect=AssertionError('No routine retrieval before danger screen')) as lookup:
            self.incoming('Smoke and sparks are coming from the washer.')
        self.assessor.assert_not_called();self.reply.assert_not_called();lookup.assert_not_called()
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['assessment']['severity'],'CRITICAL');self.assertIn('move away',out['text'])
    def test_assessment_failure_routes_without_an_unassessed_case(self):
        self.assessor.side_effect=ValueError('Invalid provider output');self.incoming()
        case=self.rows('case')[0];self.assertEqual(case['severity'],'MEDIUM');self.assertTrue(case['analysis']['uncertainty'])
        self.assertEqual(case['status'],'HUMAN_REVIEW');self.assertEqual(self.rows('wa_outgoing')[0]['delivery_kind'],'ACKNOWLEDGEMENT')
    def test_short_followup_does_not_downgrade_an_unresolved_high_case(self):
        self.prepared('HIGH');self.incoming()
        self.prepared('LOW');self.assessor.return_value.update(report_type='ENQUIRY',category='OTHER',requires_human=False)
        self.incoming('Okay, thank you.')
        case=self.rows('case')[0];self.assertEqual((case['category'],case['severity']),('MAINTENANCE','HIGH'))
        self.assertIn('priority has been retained',case['analysis']['level_reason'])
        self.assertEqual(case['status'],'HUMAN_REVIEW')
    def test_failed_followup_keeps_the_unresolved_high_priority(self):
        self.prepared('HIGH');self.incoming()
        self.assessor.side_effect=ValueError('Provider assessment failed')
        self.incoming('Any update from the team?')
        case=self.rows('case')[0]
        self.assertEqual((case['category'],case['severity']),('MAINTENANCE','HIGH'))
        self.assertTrue(case['analysis']['uncertainty']);self.assertEqual(case['status'],'HUMAN_REVIEW')
    def queued_simple(self):
        self.prepared('LOW');self.assessor.return_value.update(report_type='ENQUIRY',requires_human=False)
        with patch('belive.whatsapp.deliver'):
            r=self.incoming('What details should a maintenance report contain?')
        return r,self.rows('wa_outgoing')[0]
    def test_staff_priority_change_suppresses_a_queued_simple_reply(self):
        r,out=self.queued_simple();case=self.rows('case')[0]
        self.command('case_action',id=case['id'],revision=case['revision'],action='assess',category='MAINTENANCE',severity='HIGH',note='Staff confirmed this needs urgent investigation.')
        result=wa.deliver(self.s,out['id'])
        self.assertEqual(result['status'],'SUPERSEDED');self.assertEqual(self.rows('wa_turn')[0]['status'],'COMPLETE')
        self.assertFalse(any(m['direction']=='AI' for m in self.rows('wa_message')));self.net.assert_not_called()
    def test_case_note_change_or_closure_cannot_send_an_old_queued_reply(self):
        r,out=self.queued_simple();case=self.rows('case')[0]
        self.command('case_action',id=case['id'],revision=case['revision'],action='note',note='Staff is checking the latest customer context.')
        self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SUPERSEDED')
        with self.s.store.connect() as db:
            case=self.s.store.get(db,'case',r['case_id']);case['status']='CLOSED';self.s.store.put(db,'case',case)
            out.update(status='QUEUED',case_revision=case['revision']);self.s.store.put(db,'wa_outgoing',out)
        self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SUPERSEDED')
        self.assertFalse(any(t['status']=='PENDING' for t in self.rows('wa_turn')));self.net.assert_not_called()
    def test_send_policy_rechecks_current_level_even_when_revision_is_unchanged(self):
        r,out=self.queued_simple()
        with self.s.store.connect() as db:
            case=self.s.store.get(db,'case',r['case_id']);case['severity']='MEDIUM';self.s.store.put(db,'case',case)
        self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SUPERSEDED');self.net.assert_not_called()
    def test_urgent_acknowledgement_does_not_wait_for_shared_knowledge(self):
        from belive import repository_memory as rm
        self.command('wa_knowledge',title='Fictional shared washer guidance',text='Staff checks the washing machine; do not repair it yourself.',source='Reviewed test source',confirmed=True)
        rm.configure(self.s)
        with patch('belive.shared_memory.sync',side_effect=AssertionError('Urgent acknowledgement must not sync unrelated knowledge')) as sync, \
             patch('belive.reply_learning.matching',side_effect=AssertionError('Urgent acknowledgement does not use tips')) as tips:
            self.incoming('Smoke and sparks are coming from the shared washer.')
        out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['status'],'SIMULATED');self.assertEqual(out['delivery_kind'],'URGENT_ACKNOWLEDGEMENT')
        self.assertEqual(out['knowledge_versions'],{});self.assertEqual(out['shared_revisions'],{});self.assertEqual(out['tip_ids'],[])
        sync.assert_not_called();tips.assert_not_called();self.assessor.assert_not_called();self.reply.assert_not_called()
    def test_configured_maintenance_destination_is_used_for_new_and_upgraded_work_orders(self):
        self.prepared();self.command('routing_settings',departments={'MAINTENANCE':'Fictional property maintenance desk'},confirmed=True)
        self.reply.return_value={**plan(),'needs_staff':True,'staff_question':'Please confirm safe maintenance arrangements.'}
        self.incoming();self.reply.return_value.update(needs_maintenance=True)
        self.incoming('Please arrange maintenance for the same washer.')
        work=[x for x in self.rows('outbox') if x['kind']=='STAFF_WORK_ORDER']
        self.assertEqual(len(work),1);self.assertEqual(work[0]['target'],'Fictional property maintenance desk')
        # A fresh customer taking the maintenance path directly uses the same approved destination.
        r=self.command('wa_simulate',customer='another-triage-customer',text='The shared washer needs a maintenance visit.')
        wa.process_thread(self.s,r['thread_id'])
        work=[x for x in self.rows('outbox') if x['kind']=='STAFF_WORK_ORDER']
        self.assertEqual(len(work),2);self.assertTrue(all(x['target']=='Fictional property maintenance desk' for x in work))

    def test_verified_staff_relay_is_saved_for_reviewed_case_learning(self):
        self.prepared();r=self.incoming();thread=self.rows('wa_thread')[0]
        self.reply.return_value={**plan(),'reply':'The team confirmed the laundry room has been inspected; use the other labelled washer while this one is checked.'}
        self.command('wa_staff_reply',thread_id=r['thread_id'],revision=thread['revision'],confirmed=True,
            guidance='Verified fictional guidance: inspection completed; use the other labelled washer during checks.')
        wa.process_thread(self.s,r['thread_id']);out=self.rows('wa_outgoing')[0];case=self.rows('case')[0]
        self.assertEqual(out['delivery_kind'],'VERIFIED_STAFF_GUIDANCE');self.assertEqual(case['draft'],out['text'])
        self.assertEqual(out['status'],'SIMULATED');self.assertFalse(self.rows('wa_staff')[0]['status']=='OPEN')

class StaffContinuationPolicyTests(unittest.TestCase):
    def test_verified_same_issue_continues_despite_uncertain_fault(self):
        a={'severity':'MEDIUM','uncertainty':True,'level_reason':'Unconfirmed fault.','requires_human':True}
        draft={**plan(),'handling':'ANSWER','related_request_id':'staff-one','sources_used':['staff-one']}
        ctx={'latest_sender':'CUSTOMER','staff_guidance':[{'id':'staff-one','verified_solution':'Collect location, then record it.'}],
             'support_requests':[{'id':'staff-one','status':'ANSWERED'}]}
        _,result,kind,private=triage.apply_policy(a,draft,ctx)
        self.assertEqual(kind,'VERIFIED_STAFF_GUIDANCE');self.assertFalse(result['needs_staff']);self.assertIsNone(private)
        for change in ({'staff_guidance':[]},{'support_requests':[{'id':'staff-one','status':'CLOSED'}]},
                       {'staff_guidance':[{'id':'other-issue','verified_solution':'Unrelated instructions'}]},
                       {'sop_lookup_uncertain':True},{'explicit_staff_requested':True}):
            with self.subTest(change=change):
                self.assertNotEqual(triage.apply_policy(a,draft,{**ctx,**change})[2],'VERIFIED_STAFF_GUIDANCE')
        self.assertNotEqual(triage.apply_policy({**a,'severity':'HIGH'},draft,ctx)[2],'VERIFIED_STAFF_GUIDANCE')

class WhatsAppAssessmentValidationTests(unittest.TestCase):
    def context(self):return {'conversation':[{'role':'CUSTOMER','text':'The washer stopped.'},{'role':'AI','text':'A previous answer.'},{'role':'CUSTOMER','text':'It still does not start.'}]}
    def result(self):return dict(report_type='COMPLAINT',category='MAINTENANCE',severity='MEDIUM',summary='The washer is not starting.',level_reason='A physical shared-appliance fault requires staff investigation.',uncertainty=False,evidence_index=2,research='NONE',search_query='')
    def test_exact_customer_evidence_is_extracted_and_shape_is_recorded(self):
        with patch('belive.whatsapp_ai.ask',return_value=self.result()) as ask:a=triage.assess(None,self.context())
        self.assertEqual(a['evidence'],'It still does not start.');self.assertEqual(a['complaint_level'],'MODERATE')
        self.assertEqual(ask.call_args.args[1],'Complaint Analysis Agent')
    def test_invalid_category_boolean_index_and_ai_message_index_are_rejected(self):
        for extra in ({'category':'MADE_UP'},{'evidence_index':True},{'evidence_index':1},{'uncertainty':'false'}):
            with self.subTest(extra=extra),patch('belive.whatsapp_ai.ask',return_value={**self.result(),**extra}):
                with self.assertRaises(ValueError):triage.assess(None,self.context())

if __name__=='__main__':unittest.main()
