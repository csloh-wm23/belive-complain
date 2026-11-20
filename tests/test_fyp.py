"""Complaint levels, real agent boundaries, demo isolation and measured feedback reuse."""
import secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive.ai import SupportAI
from belive.settings import Settings
from belive import demo,learning
from test_automation import RoutineAI

class LearningAI(RoutineAI):
    same=False
    fail=False
    def analyse(self,context,examples):
        if self.fail:raise RuntimeError('AI_FAILED_OR_INVALID')
        result=super().analyse(context,examples)
        response='Try the device-side checks. Which devices are affected? Is the network name visible?'
        if examples and not self.same:response='1. Check that Wi-Fi is on.\n2. When did the issue start?'
        return {**result,'response':response,'guidance_review_passed':True,
                'learning_used':{'count':len(examples),'example_ids':[x['id'] for x in examples]}}

class FypTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ai=LearningAI()
        self.s=Service(Path(self.tmp.name)/'app.db',self.ai)
        self.cmd('demo_prepare',{'confirmed':True});self.cmd('automation_settings',{'enabled':True})
        self.token=demo.session(self.s)['token']
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,name,p,key=None):
        # Retain regression coverage for saved legacy writing-format comparisons.
        if name=='learning_start':p={'mode':'style_legacy',**p}
        return self.s.command(name,p,key or secrets.token_hex(12))
    def intake(self,text='How do I report a Wi-Fi connection problem?'):
        return self.s.portal_submit(self.token,{'title':'Wi-Fi support','description':text},secrets.token_hex(12))
    def current(self,c):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',c['id'])
    def replies(self,c):return [m for x in self.s.portal(self.token)['cases'] if x['id']==c['id'] for m in x['conversation'] if m['sender']=='AI_SUPPORT']

    def test_only_simple_replies_automatically_and_moderate_keeps_ai_draft(self):
        c=self.intake();self.s.analyse(c['id']);self.assertEqual(self.current(c)['status'],'FOLLOW_UP');self.assertTrue(self.replies(c))
        original=self.ai.analyse
        self.ai.analyse=lambda ctx,ex:{**original(ctx,ex),'severity':'MEDIUM','complaint_level':'SIMPLE'}
        c=self.intake('My Wi-Fi connection needs further investigation.');self.s.analyse(c['id'])
        current=self.current(c);self.assertEqual(current['status'],'HUMAN_REVIEW');self.assertTrue(current['draft'])
        self.assertEqual(self.replies(c),[])
        snapshot=next(x for x in self.s.snapshot()['cases'] if x['id']==c['id'])
        self.assertEqual(snapshot['complaint_level'],'MODERATE')
        self.assertTrue(next(x for x in self.s.portal(self.token)['cases'] if x['id']==c['id'])['ai_draft_ready'])

    def test_reply_outcomes_count_unique_sends_and_reopened_cases(self):
        original = self.ai.analyse
        self.ai.analyse = lambda ctx, ex: {**original(ctx, ex), 'severity': 'MEDIUM'}
        case = self.intake()
        self.s.analyse(case['id'])

        def act(action, **fields):
            return self.cmd('case_action', dict(id=case['id'], revision=self.current(case)['revision'],
                                                action=action, **fields))

        act('publish_response', confirmed=True)
        act('publish_response', confirmed=True)
        with self.s.store.connect() as db:
            current = self.current(case)
            current['status'] = 'CLOSED'
            self.s.store.put(db, 'case', current)
        act('reopen', note='Tenant still reports the same issue.')
        outcomes = self.s.snapshot()['reports']['reply_outcomes']
        self.assertEqual(outcomes, dict(staff_replies=1, ai_drafts_sent=1,
                                        ai_drafts_unchanged=1, reopened_after_reply=1))

    def test_moderate_physical_case_gets_ai_assistance_without_sending(self):
        c=self.intake('The fan is broken and needs a repair.')
        self.assertEqual(c['status'],'HUMAN_REVIEW');self.assertTrue(c['ai_assistance_pending'])
        self.assertEqual(self.ai.calls,[])
        self.s.analyse(c['id']);current=self.current(c)
        self.assertTrue(current['analysis']);self.assertTrue(current['draft'])
        self.assertEqual(current['status'],'HUMAN_REVIEW');self.assertFalse(current['ai_assistance_pending'])
        self.assertEqual(self.replies(c),[])

    def test_belive_routing_uses_saved_department_after_ai_category_check(self):
        self.cmd('routing_settings',{'departments':{'WIFI':'Demo network team'},'confirmed':True})
        original=self.ai.analyse
        self.ai.analyse=lambda ctx,ex:{**original(ctx,ex),'severity':'MEDIUM'}
        c=self.intake();self.s.analyse(c['id'])
        self.assertEqual(self.current(c)['staff_destination'],'Demo network team')
        with self.s.store.connect() as db:
            self.assertTrue(any(x['entity']==c['id'] and x['target']=='Demo network team' and x['status']=='PENDING_APPROVAL' for x in self.s.store.all(db,'outbox')))
        with self.assertRaises(ValueError):self.cmd('routing_settings',{'departments':{'INVENTED':'Other team'},'confirmed':True})

    def test_learning_scores_only_the_declared_format_and_real_length(self):
        numbered='1. Check the Wi-Fi setting.\n2. Which device is affected?'
        self.assertEqual(learning.score(numbered)['passed'],3)
        self.assertFalse(learning.score('An introductory paragraph.\n'+numbered)['checks']['numbered_steps'])
        self.assertEqual(learning.score(numbered)['word_count'],len(numbered.split()))

    def test_unrelated_message_stops_before_response_agent(self):
        c=self.intake()
        with self.s.store.connect() as db:context=self.s.context(db,c)
        triage=dict(report_type='NON_SUPPORT',relevance='NON_SUPPORT',category='OTHER',severity='LOW',summary='Not a support message.',uncertainty=False,evidence='Wi-Fi')
        ai=SupportAI(Settings(),Path(self.tmp.name)/'agents')
        with patch.object(ai,'generate',return_value=triage) as generate:result=ai.analyse(context,[])
        self.assertEqual(generate.call_count,1);self.assertEqual(result['complaint_level'],'NOT_A_COMPLAINT')
        self.assertNotIn('response',result)

    def test_high_danger_never_waits_for_response_agent(self):
        c=self.intake('There is smoke from the electrical socket.')
        self.assertEqual(c['severity'],'CRITICAL');self.assertEqual(c['status'],'HUMAN_REVIEW')
        self.assertEqual(self.ai.calls,[]);self.assertEqual(self.replies(c),[])

    def test_distinct_analysis_response_and_review_calls_are_recorded(self):
        c=self.intake()
        with self.s.store.connect() as db:context=self.s.context(db,c)
        guide=next(a for a in context['approved_answers'] if a.get('kind')=='GUIDANCE')
        triage=dict(report_type='COMPLAINT',relevance='SUPPORT',category='WIFI',severity='LOW',summary='A routine support question.',uncertainty=False,evidence='Wi-Fi')
        response=dict(plan='Use approved guidance.',response='Which device is affected?',requires_human=False,record_ids=[guide['id']],approved_answer_id=guide['id'],match_confidence=.99,request_language='en')
        review=dict(grounded=True,safe=True,uncertainty=False,unsupported_claims=[])
        ai=SupportAI(Settings(),Path(self.tmp.name)/'agents')
        with patch.object(ai,'generate',side_effect=[triage,response,review]):result=ai.analyse(context,[])
        self.assertEqual([x['agent'] for x in result['agent_trace']],['Complaint Analysis Agent','Support Response Agent','Safety Review Agent'])
        self.assertTrue(all(x['status']=='COMPLETED' for x in result['agent_trace']))

    def test_demo_access_never_returns_other_tenant_records(self):
        self.cmd('condo',dict(id='REAL',name='Normal property',rules='Verified support guidance for a normal tenant.',confirmed=True))
        self.cmd('tenant',dict(id='REAL-T',condo_id='REAL',unit_ref='UNIT',verified_by='QA',evidence='Verified test record for normal access.',confirmed=True))
        real=self.cmd('intake',dict(title='Other private case',description='Private case belonging to another test tenant.',tenant_id='REAL-T'))
        self.assertNotIn(real['id'],str(self.s.portal(self.token)))
        self.assertEqual(demo.session(self.s)['token'],self.token)
        self.cmd('demo_settings',{'enabled':False})
        with self.assertRaises(ValueError):demo.session(self.s)
        with self.assertRaises(ValueError):self.s.portal(self.token)

    def test_cannot_enable_demo_on_normal_records_by_configuration_alone(self):
        with self.s.store.connect() as db:
            t=self.s.store.get(db,'tenant',demo.TENANT);t['demo_only']=False;self.s.store.put(db,'tenant',t)
            self.assertFalse(demo.info(self.s,db)['available'])
        with self.assertRaises(ValueError):demo.session(self.s)

    def test_learning_measures_improvement_and_reuses_lesson_in_future_demo_reply(self):
        run=self.cmd('learning_start',{})
        learning.execute(self.s,run['id'])
        with self.s.store.connect() as db:first=self.s.store.get(db,'learning_run',run['id'])
        self.assertEqual(first['status'],'BASELINE_READY')
        self.cmd('learning_improve',{'id':run['id'],'lesson':learning.LESSON,'confirmed':True})
        learning.execute(self.s,run['id'])
        with self.s.store.connect() as db:
            final=self.s.store.get(db,'learning_run',run['id'])
            self.assertEqual(final['status'],'COMPLETE');self.assertGreater(final['change'],0)
            self.assertTrue(final['adopted_lesson_id'])
            self.assertEqual(self.s.styles(db,shared=True),[])
            self.assertEqual(self.s.styles(db,condo_id='OTHER'),[])
        self.assertEqual(self.ai.calls[0][0],self.ai.calls[1][0])
        self.assertEqual(self.ai.calls[0][1],[]);self.assertEqual(len(self.ai.calls[1][1]),1)
        c=self.intake('Wi-Fi network keeps dropping. What should I check on my device?');self.s.analyse(c['id'])
        self.assertEqual(self.ai.calls[-1][1][0]['id'],final['adopted_lesson_id'])
        self.cmd('lesson_revoke',{'id':final['adopted_lesson_id']})
        with self.s.store.connect() as db:self.assertEqual(self.s.styles(db,condo_id=demo.PROPERTY),[])

    def test_learning_rejects_a_stalled_repair_without_creating_a_comparison(self):
        question='My refrigerator has been broken for three months and no one comes to fix it.'
        with self.assertRaisesRegex(ValueError,'Repair requests and danger reports go to staff'):
            self.cmd('learning_start',{'category':'HOUSE_RULES','question':question})
        self.assertEqual(self.s.snapshot()['learning_runs'],[])
        practice='What details should I include when reporting a refrigerator that is no longer cooling?'
        entry=self.cmd('learning_start',{'category':'MAINTENANCE','question':practice})
        run=next(row for row in self.s.snapshot()['learning_runs'] if row['id']==entry['id'])
        self.assertEqual((run['category'],run['question']),('MAINTENANCE',practice))

    def test_learning_uses_approved_guidance_for_all_support_topics(self):
        from belive.ai import CATEGORIES

        self.assertEqual({item['category'] for item in self.s.snapshot()['learning_scenarios']}, set(CATEGORIES))
        for category in CATEGORIES:
            with self.subTest(category=category):
                run=self.cmd('learning_start',{'category':category})
                with self.s.store.connect() as db:
                    saved=self.s.store.get(db,'learning_run',run['id'])
                self.assertEqual(saved['category'],category)
                self.assertEqual(saved['question'],learning.SCENARIOS[category][1])
                self.assertEqual(saved['context']['approved_answers'][0]['category'],category)
        with self.assertRaisesRegex(ValueError,'safe informational question'):
            self.cmd('learning_start',{'category':'UTILITIES','question':'I can smell gas in the building.'})
        with self.assertRaisesRegex(ValueError,'supported practice topic'):
            self.cmd('learning_start',{'category':'UNKNOWN'})

    def test_response_agent_gets_only_matching_topic_lessons_after_classification(self):
        case=self.intake('How should I report a dirty shared kitchen?')
        with self.s.store.connect() as db:
            context=self.s.context(db,case)
        triage=dict(report_type='ENQUIRY',relevance='SUPPORT',category='CLEANING',severity='LOW',
                    summary='The tenant wants to report a cleaning issue.',uncertainty=False,evidence='dirty shared kitchen')
        response=dict(plan='Clarify the location.',response='Which part of the kitchen needs attention?',
                      requires_human=False,record_ids=[],approved_answer_id='',match_confidence=0,request_language='en')
        lessons=[dict(id='wifi-style',text='Ask which Wi-Fi device is affected.',scope_category='WIFI'),
                 dict(id='cleaning-style',text='Ask which area is affected.',scope_category='CLEANING')]
        ai=SupportAI(Settings(),Path(self.tmp.name)/'agents')
        with patch.object(ai,'generate',side_effect=[triage,response]) as generate:
            result=ai.analyse(context,lessons)
        self.assertEqual(generate.call_args_list[0].args[3],[])
        self.assertEqual(generate.call_args_list[1].args[3],[lessons[1]])
        self.assertEqual(result['learning_used'],{'count':1,'example_ids':['cleaning-style']})

    def test_no_improvement_does_not_invent_a_success_or_save_a_lesson(self):
        self.ai.same=True;run=self.cmd('learning_start',{});learning.execute(self.s,run['id'])
        self.cmd('learning_improve',{'id':run['id'],'lesson':learning.LESSON,'confirmed':True});learning.execute(self.s,run['id'])
        with self.s.store.connect() as db:
            final=self.s.store.get(db,'learning_run',run['id'])
            self.assertEqual(final['change'],0);self.assertNotIn('adopted_lesson_id',final)
            self.assertEqual(self.s.store.all(db,'learned_style'),[])

    def test_learning_failure_does_not_create_scores(self):
        self.ai.fail=True;run=self.cmd('learning_start',{});learning.execute(self.s,run['id'])
        with self.s.store.connect() as db:
            final=self.s.store.get(db,'learning_run',run['id'])
            self.assertEqual(final['status'],'FAILED');self.assertIsNone(final['baseline'])
            self.assertEqual(self.s.store.all(db,'learned_style'),[])

    def test_learning_requires_reviewed_feedback_and_replays_do_not_create_runs(self):
        key=secrets.token_hex(12);run=self.cmd('learning_start',{},key)
        self.assertEqual(self.cmd('learning_start',{},key)['id'],run['id'])
        learning.execute(self.s,run['id'])
        with self.assertRaises(ValueError):self.cmd('learning_improve',{'id':run['id'],'lesson':learning.LESSON,'confirmed':False})

    def test_restart_marks_unfinished_comparison_interrupted(self):
        run=self.cmd('learning_start',{})
        restarted=Service(self.s.store.path,self.ai)
        with restarted.store.connect() as db:
            saved=restarted.store.get(db,'learning_run',run['id'])
            self.assertEqual(saved['status'],'INTERRUPTED')
            self.assertIsNone(saved['baseline'])

    def test_recovery_never_resumes_demo_access_or_adopted_lessons(self):
        from belive.backups import operation
        from belive.store import Store
        self.s.workspace_config=Path(self.tmp.name)/'workspace.json'
        run=self.cmd('learning_start',{});learning.execute(self.s,run['id'])
        self.cmd('learning_improve',{'id':run['id'],'lesson':learning.LESSON,'confirmed':True});learning.execute(self.s,run['id'])
        pending=self.cmd('learning_start',{})
        backup=operation(self.s,'backup',{},secrets.token_hex(12))
        restored=operation(self.s,'restore',{'id':backup['id'],'confirmed':True},secrets.token_hex(12))
        recovered=Store(Path(restored['path']))
        with recovered.connect() as db:
            self.assertFalse(recovered.get(db,'demo','tenant-demo')['enabled'])
            self.assertTrue(all(not x['active'] for x in recovered.all(db,'learned_style')))
            self.assertEqual(recovered.get(db,'learning_run',pending['id'])['status'],'INTERRUPTED')
            self.assertEqual(recovered.all(db,'portal'),[])
