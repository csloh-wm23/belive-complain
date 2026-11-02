"""Adapted support guidance must remain grounded, current and safe before publication."""
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive.ai import SupportAI
from belive.service import Service
from belive.settings import Settings


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ai=SupportAI(Settings(),Path(self.tmp.name)/'memory')
        self.s=Service(Path(self.tmp.name)/'cases.db',self.ai)
        self.cmd('condo',dict(id='DEMO',name='Fictional guidance property',rules='Fictional verified support guidance only.',confirmed=True))
        self.cmd('tenant',dict(id='T',condo_id='DEMO',unit_ref='QA',verified_by='QA staff',evidence='Fictional checked tenancy.',confirmed=True))
        self.token=self.cmd('portal_issue',{'tenant_id':'T'})['token']
        self.guide=self.cmd('answer',dict(condo_id='DEMO',question='Wi-Fi router connection problems',category='WIFI',
            kind='GUIDANCE',language='en',answer='Ask which devices are affected and whether the network name is visible. Ask at most two questions. Do not diagnose an outage.',
            source='Fictional reviewed support playbook.',confirmed=True))
        with patch.object(self.ai,'readiness',return_value=True):self.cmd('automation_settings',{'enabled':True})

    def tearDown(self):self.tmp.cleanup()
    def cmd(self,name,p):return self.s.command(name,p,secrets.token_hex(12))
    def create(self):return self.s.portal_submit(self.token,{'title':'Router problem','description':'my router is not working (fictional test '+secrets.token_hex(3)+')'},secrets.token_hex(12))
    def current(self,c):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',c['id'])
    def replies(self,c):return [m for x in self.s.portal(self.token)['cases'] if x['id']==c['id'] for m in x['conversation'] if m['sender']=='AI_SUPPORT']
    def outputs(self):
        return [dict(report_type='COMPLAINT',relevance='SUPPORT',category='WIFI',severity='LOW',summary='A reported Wi-Fi problem.',uncertainty=False,evidence='my router is not working'),
            dict(plan='Use the approved intake guidance.',response='Is the Wi-Fi network name visible, and does the same issue affect another device?',
                 requires_human=False,record_ids=[self.guide['id']],approved_answer_id=self.guide['id'],match_confidence=.98,request_language='en'),
            dict(grounded=True,safe=True,uncertainty=False,unsupported_claims=[])]

    def test_simple_guidance_adapts_response_and_checks_current_conversation(self):
        c=self.create();outputs=self.outputs()
        with patch.object(self.ai,'generate',side_effect=outputs) as generate:
            job=self.s.analyse(c['id'])
        self.assertEqual(job['status'],'COMPLETED')
        self.assertEqual(self.current(c)['status'],'FOLLOW_UP')
        self.assertEqual(self.replies(c)[0]['text'],outputs[1]['response'])
        self.assertNotEqual(self.replies(c)[0]['text'],self.guide['answer'])
        self.assertEqual(generate.call_args_list[-1].args[0],'Safety Review Agent')
        self.assertEqual(generate.call_args_list[-1].args[2]['approved_guidance']['id'],self.guide['id'])
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':True},secrets.token_hex(12))
        self.assertEqual(self.current(c)['status'],'ANSWERED')
        self.assertFalse(self.current(c)['verification'])

    def test_unsafe_unsupported_or_uncertain_review_never_publishes(self):
        for change in [{'grounded':False},{'safe':False},{'uncertainty':True},{'unsupported_claims':['Invented building outage.']}]:
            with self.subTest(change=change):
                c=self.create();outputs=self.outputs();outputs[2].update(change)
                with patch.object(self.ai,'generate',side_effect=outputs):self.s.analyse(c['id'])
                self.assertEqual(self.current(c)['status'],'HUMAN_REVIEW')
                self.assertEqual(self.replies(c),[])
                self.assertIn('AI_UNGROUNDED_GUIDANCE',self.current(c)['review_reason'])

    def test_review_keeps_the_current_approved_style_projection(self):
        c=self.create()
        with self.s.store.connect() as db:context=self.s.context(db,c)
        examples=[{'id':'REVIEWED-STYLE','text':'Ask one concise question at a time.'}]
        with patch.object(self.ai,'generate',side_effect=self.outputs()) as generate:
            self.ai.analyse(context,examples)
        self.assertEqual(generate.call_count,3)
        for call in generate.call_args_list:self.assertEqual(call.args[-1],examples)

    def test_missing_citation_or_invalid_review_fails_closed(self):
        for broken in ['citation','schema']:
            c=self.create();outputs=self.outputs()
            if broken=='citation':outputs[1]['record_ids']=[]
            else:outputs[2]['safe']='yes'
            with patch.object(self.ai,'generate',side_effect=outputs):self.s.analyse(c['id'])
            self.assertEqual(self.current(c)['status'],'HUMAN_REVIEW');self.assertEqual(self.replies(c),[])

    def test_high_urgency_never_enters_the_guidance_review_or_publishes(self):
        c=self.create();triage=self.outputs()[0];triage['severity']='HIGH'
        with patch.object(self.ai,'generate',return_value=triage) as generate:self.s.analyse(c['id'])
        self.assertEqual(generate.call_count,1)
        self.assertEqual(self.current(c)['status'],'HUMAN_REVIEW');self.assertEqual(self.replies(c),[])

    def test_guide_revision_during_review_discards_the_candidate(self):
        c=self.create();outputs=self.outputs()
        def generate(role,*args):
            if role=='Complaint Analysis Agent':return outputs[0]
            if role=='Support Response Agent':return outputs[1]
            self.cmd('answer',{**self.guide,'answer':'Corrected fictional guide. Ask only whether the network is visible.','confirmed':True})
            return outputs[2]
        with patch.object(self.ai,'generate',side_effect=generate):job=self.s.analyse(c['id'])
        self.assertEqual(job['status'],'STALE');self.assertEqual(self.replies(c),[])

    def test_all_categories_can_store_guidance_without_granting_action_permission(self):
        for category in ['CLEANING','MAINTENANCE','ACCESS','UTILITIES','BILLING','HOUSE_RULES','OTHER']:
            guide=self.cmd('answer',dict(condo_id='DEMO',question='How should this support issue be reported?',category=category,
                kind='GUIDANCE',language='en',answer='Ask for the affected area and when the issue started. Do not promise any action.',
                source='Fictional reviewed intake guidance.',confirmed=True))
            self.assertEqual(guide['category'],category)
        for problem in ['I need a refund for my rent payment.','The pipe is broken and leaking.','There is smoke from the socket.']:
            c=self.s.portal_submit(self.token,{'title':'Action needed','description':problem},secrets.token_hex(12))
            self.assertEqual(c['status'],'HUMAN_REVIEW');self.assertEqual(self.replies(c),[])
