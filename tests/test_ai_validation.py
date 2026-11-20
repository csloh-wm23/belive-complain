"""Regression checks for tenant-report evidence, safe diagnostics and recovery."""
import io
import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from belive import openrouter
from belive.ai import SupportAI,failure_code
from belive.service import Service
from belive.settings import Settings, load_settings
from test_backend import FakeAI

class AIValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ai=SupportAI(Settings(),self.root/'memory')
        self.context={'case':{'title':'my pipe broke','description':'no one comes and fix it'},
                      'verified_records':[],'tenant_verified':True,
                      'conversation':[{'text':'A conversation-only excerpt.'}]}
        self.triage=dict(report_type='COMPLAINT',relevance='SUPPORT',category='MAINTENANCE',severity='MEDIUM',
                         summary='Tenant reports a broken pipe and an unresolved request.',
                         uncertainty=False,evidence='my pipe broke')
        self.plan=dict(plan='Staff should assess the reported pipe problem.',
                       response='Is water currently leaking, and where is the pipe?',
                       requires_human=True,record_ids=[])
    def tearDown(self):self.tmp.cleanup()
    def service(self):
        s=Service(self.root/'test.db',FakeAI())
        def command(name,p):return s.command(name,p,secrets.token_hex(16))
        command('condo',dict(id='C',name='Fictional test property',rules='Fictional support guidance only.',confirmed=True))
        command('tenant',dict(id='T',condo_id='C',unit_ref='U',verified_by='QA staff',evidence='Fictional test tenancy checked.',confirmed=True))
        c=command('intake',dict(**self.context['case'],tenant_id='T'))
        return s,c
    def current(self,s,c):
        with s.store.connect() as db:return s.store.get(db,'case',c['id'])
    def test_exact_title_and_description_quotes_are_attributed(self):
        for evidence,field in [('my pipe broke','title'),('no one comes and fix it','description')]:
            with self.subTest(field=field),patch.object(self.ai,'generate',side_effect=[{**self.triage,'evidence':evidence},dict(self.plan)]) as generate:
                result=self.ai.analyse(self.context,[])
                self.assertEqual(result['evidence'],evidence);self.assertEqual(result['evidence_field'],field)
                self.assertTrue(result['requires_human']);self.assertEqual(generate.call_count,2)
    def test_local_model_can_select_exact_report_evidence(self):
        ai = SupportAI(Settings(llm_provider='ollama'), self.root / 'local-memory')
        with patch.object(ai, 'generate', side_effect=[{**self.triage, 'evidence': 'description'}, dict(self.plan)]):
            result = ai.analyse(self.context, [])
        self.assertEqual(result['evidence_field'], 'description')
        self.assertEqual(result['evidence'], self.context['case']['description'])

    def test_quotes_from_other_context_or_paraphrases_are_rejected(self):
        context={**self.context,'verified_records':[{'id':'R','text':'A record-only excerpt.'}]}
        for evidence in ['the pipe is broken','My pipe broke','A record-only excerpt.','A conversation-only excerpt.','',123]:
            with self.subTest(evidence=evidence),patch.object(self.ai,'generate',return_value={**self.triage,'evidence':evidence}) as generate:
                with self.assertRaisesRegex(ValueError,'AI_UNGROUNDED_EVIDENCE'):self.ai.analyse(context,[])
                self.assertEqual(generate.call_count,1)
    def test_title_quote_does_not_bypass_schema_checks(self):
        with patch.object(self.ai,'generate',return_value={**self.triage,'uncertainty':'false'}):
            with self.assertRaisesRegex(ValueError,'AI_INVALID_VALUES'):self.ai.analyse(self.context,[])
    def test_conflicting_complaint_labels_get_one_checked_retry(self):
        context={**self.context,'tenant_verified':False,'case':{'title':'Public review',
                 'description':'The tour was enjoyable and the view was beautiful.'}}
        conflict={**self.triage,'report_type':'ENQUIRY','relevance':'NON_SUPPORT',
                  'category':'OTHER','severity':'LOW','evidence':'The tour was enjoyable'}
        corrected={**conflict,'report_type':'NON_SUPPORT','summary':'Positive feedback without a support request.'}
        with patch.object(self.ai,'generate',side_effect=[conflict,corrected]) as generate:
            result=self.ai.analyse(context,[])
        self.assertEqual(result['report_type'],'NON_SUPPORT')
        self.assertEqual(generate.call_count,2)
        self.assertIn('previous pair conflicted',generate.call_args.args[1])
        with patch.object(self.ai,'generate',return_value=conflict) as generate:
            with self.assertRaisesRegex(ValueError,'AI_INVALID_VALUES'):
                self.ai.analyse(context,[])
            self.assertEqual(generate.call_count,2)

    def test_specific_failure_is_visible_and_successful_retry_clears_old_reason(self):
        s,c=self.service()
        with patch.object(s.ai,'analyse',side_effect=ValueError('AI_UNGROUNDED_EVIDENCE')):
            job=s.analyse(c['id'])
        current=self.current(s,c)
        self.assertEqual(job['status'],'FAILED');self.assertEqual(job['error'],'AI_UNGROUNDED_EVIDENCE')
        self.assertEqual(current['status'],'HUMAN_REVIEW');self.assertIsNone(current['analysis'])
        self.assertIn('complaint title or description',current['review_reason'])
        self.assertEqual(s.analyse(c['id'])['status'],'COMPLETED')
        self.assertEqual(self.current(s,c)['review_reason'],'')
        with s.store.connect() as db:self.assertEqual(s.store.get(db,'job',job['id'])['status'],'FAILED')
    def test_valid_pipe_assessment_remains_a_staff_case_without_publication(self):
        s,c=self.service();s.ai=self.ai
        with patch.object(self.ai,'generate',side_effect=[dict(self.triage),dict(self.plan)]):
            job=s.analyse(c['id'])
        current=self.current(s,c)
        self.assertEqual(job['status'],'COMPLETED');self.assertEqual(current['status'],'HUMAN_REVIEW')
        self.assertEqual(current['analysis']['evidence_field'],'title')
        self.assertEqual(current['draft'],self.plan['response'])
        self.assertNotIn('AI_FAILED',current['review_reason'])
        with s.store.connect() as db:
            self.assertFalse(any(m['kind']=='TENANT_RESPONSE' for m in s.store.all(db,'outbox')))
    def test_unexpected_exception_does_not_expose_raw_provider_details(self):
        s,c=self.service();secret='Bearer fictional-secret-do-not-log'
        with patch.object(s.ai,'analyse',side_effect=RuntimeError('AI_UNGROUNDED_EVIDENCE '+secret)):
            job=s.analyse(c['id'])
        self.assertEqual(job['error'],'AI_FAILED_OR_INVALID')
        with s.store.connect() as db:
            persisted=[s.store.all(db,'case'),s.store.all(db,'job'),s.store.audit(db)]
        self.assertNotIn(secret,json.dumps(persisted))
    def test_high_public_preview_keeps_full_acknowledgement_and_private_next_step(self):
        context = {'complaint_level': 'HIGH', 'report': 'We lost power and got no update.'}
        acknowledgement = (
            "We’re sorry about the power interruption and the lack of updates you described. "
            "We understand how disruptive that was."
        )
        with patch.object(self.ai, 'generate', return_value={'reply': acknowledgement}):
            reply = self.ai.public_reply_preview(context)
        body, next_step = reply.split('\n\n')
        self.assertEqual(body, acknowledgement)
        self.assertIn('privately through the BeLive tenant app', next_step)

    def test_high_public_preview_leaves_payment_attribution_for_staff(self):
        context = {'complaint_level': 'HIGH', 'report': 'My electricity was cut off.'}
        acknowledgement = (
            "We’re sorry your electricity was cut off due to a payment issue. "
            "It sounds like you also had trouble reaching the team."
        )
        with patch.object(self.ai, 'generate', return_value={'reply': acknowledgement}):
            reply = self.ai.public_reply_preview(context)
        self.assertIn('electricity was cut off.', reply)
        self.assertIn('trouble reaching the team', reply)
        self.assertNotIn('payment issue', reply)

    def test_high_public_preview_checks_the_full_acknowledgement(self):
        context = {'complaint_level': 'HIGH', 'report': 'We lost power and got no update.'}
        with patch.object(self.ai, 'generate',
                          return_value={'reply': "We’re sorry about the power interruption. We've already restored it."}):
            with self.assertRaisesRegex(ValueError, 'AI_UNSAFE_OUTPUT'):
                self.ai.public_reply_preview(context)

    def test_malformed_json_has_fixed_diagnostic(self):
        exc=json.JSONDecodeError('Invalid JSON','Fictional response only',0)
        self.assertEqual(failure_code(exc),'AI_INVALID_JSON')

    def test_hosted_hermes_runs_both_agents_and_loads_reviewed_replies_without_native_runtime(self):
        with patch.dict(os.environ, {
            'BELIVE_AI_PROVIDER': 'openrouter', 'BELIVE_AI_MODEL': '', 'BELIVE_AI_KEY': 'test-key-only',
        }), patch('belive.settings.load_env'):
            settings = load_settings()
        self.assertEqual(settings.llm_model, openrouter.DEFAULT_MODEL)
        ai = SupportAI(settings, self.root / 'unused-memory')
        lesson = {'id':'STYLE-TEST','text':'Ask when the appliance stopped. staff@example.com',
                  'tenant_id':'TENANT-PRIVATE'}
        context = {**self.context, 'property_version': {'id': 'PROPERTY-PRIVATE'},
                   'conversation': [{'sender': 'TENANT', 'text': 'Contact example@example.com',
                                     'case_id': 'CASE-PRIVATE'}]}
        def completion(value):
            return io.BytesIO(json.dumps({'choices': [{
                'finish_reason':'stop', 'message':{'content':json.dumps(value)}
            }]}).encode())
        with patch('belive.ai.runtime_python', side_effect=AssertionError('native runtime called')), \
             patch('belive.openrouter.urlopen', side_effect=[
                 completion({**self.triage,'evidence':'description'}), completion(self.plan),
             ]) as request:
            result = ai.analyse(context, [lesson])
        self.assertEqual([a['agent'] for a in result['agent_trace']],
                         ['Complaint Analysis Agent','Support Response Agent'])
        self.assertEqual(result['evidence'], context['case']['description'])
        self.assertEqual(result['complaint_level'], 'MODERATE')
        self.assertTrue(result['requires_human'])
        self.assertEqual(result['learning_used']['example_ids'], ['STYLE-TEST'])
        for call in request.call_args_list:
            http_request = call.args[0]
            self.assertEqual(http_request.full_url, 'https://openrouter.ai/api/v1/chat/completions')
            self.assertEqual(http_request.get_header('Authorization'), 'Bearer test-key-only')
            body = json.loads(http_request.data)
            self.assertEqual(body['model'], openrouter.DEFAULT_MODEL)
            self.assertEqual(body['response_format']['type'], 'json_schema')
            self.assertTrue(body['provider']['zdr'])
            self.assertNotIn('tools', body)
            self.assertNotIn(b'test-key-only', http_request.data)
            for private in ['PROPERTY-PRIVATE','TENANT-PRIVATE','CASE-PRIVATE','@example.com']:
                self.assertNotIn(private.encode(), http_request.data)
        sent = json.loads(json.loads(request.call_args.args[0].data)['messages'][1]['content'])
        self.assertEqual(sent['reviewed_examples'], [{'id':'STYLE-TEST',
                         'text':'Ask when the appliance stopped. [email removed]'}])

    def test_hosted_connection_check_reports_missing_key_and_safe_auth_failure(self):
        settings = Settings(llm_provider='openrouter', llm_model=openrouter.DEFAULT_MODEL)
        with patch('belive.service.load_settings', return_value=settings):
            service = Service(self.root / 'hosted.db')
        with patch('belive.ai.runtime_python', side_effect=AssertionError('native runtime called')), \
             patch('belive.openrouter.urlopen') as request:
            self.assertEqual(service.check_ai()['detail'], 'AI_NOT_CONFIGURED')
            request.assert_not_called()
            settings.llm_api_key = 'test-key-only'
            request.side_effect = HTTPError(openrouter.ENDPOINT, 401, 'private error', {},
                                            io.BytesIO(b'sensitive provider response'))
            failed = service.check_ai()
            self.assertEqual(failed['status'], 'FAILED')
            self.assertIn('rejected the API key', failed['detail'])
            self.assertNotIn('private error', str(failed))
            self.assertNotIn('test-key-only', str(failed))
            request.side_effect = None
            request.return_value = io.BytesIO(b'{"choices":[{"finish_reason":"stop","message":{"content":"{\\"ok\\":true}"}}]}')
            passed = service.check_ai()
            self.assertEqual(passed['status'], 'PASSED')
            self.assertEqual(passed['model'], openrouter.DEFAULT_MODEL)
            self.assertEqual(json.loads(json.loads(request.call_args.args[0].data)['messages'][1]['content']),
                             {'context':{'check':'connection only; no tenant data'},'reviewed_examples':[]})

if __name__=='__main__':unittest.main()
