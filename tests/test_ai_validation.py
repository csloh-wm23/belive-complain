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
from belive import hosted_ai
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
    def test_public_preview_preserves_complete_case_specific_reply_at_every_level(self):
        examples = [
            ('SIMPLE', 'My phone cannot connect to Wi-Fi, but my laptop works.',
             'Sorry your phone cannot connect while your laptop still works. '
             'What phone model are you using, and is an error message shown when you try to connect?'),
            ('MODERATE', 'The shared washing machine has not spun for five days despite my earlier report.',
             'We’re sorry the washing machine is still unusable after your earlier report. '
             'What brand and model is it, and is an error code showing on the display?'),
            ('HIGH', 'We lost power and got no update.',
             'We’re sorry about the power interruption and lack of updates you reported.\n\n'
             'Please contact BeLive tenant support privately so staff can review the situation.'),
        ]
        for level, report, expected in examples:
            with self.subTest(level=level), patch.object(self.ai, 'generate', return_value={'reply': expected}):
                reply = self.ai.public_reply_preview({'complaint_level': level, 'report': report})
            self.assertEqual(reply, expected)

    def test_public_preview_does_not_append_an_unrequested_contact_footer(self):
        expected = (
            'We’re sorry the washer is still not spinning and that your earlier report has not helped. '
            'Could you share the brand, model and any error code visible on the display?'
        )
        context = {'complaint_level': 'MODERATE', 'report': 'Our shared washer is still not spinning.'}
        with patch.object(self.ai, 'generate', return_value={'reply': expected}):
            self.assertEqual(self.ai.public_reply_preview(context), expected)

    def test_threads_draft_respects_platform_characters_without_truncating_chinese(self):
        context = {'platform':'THREADS','complaint_level':'MODERATE',
                   'report':'The shared kitchen has not been cleaned.'}
        reply = ('很抱歉，公共厨房仍未清洁。请说明受影响的区域和已经报告的情况。' * 30)[:500]
        self.assertGreater(len(reply.encode('utf-8')), 500)
        with patch.object(self.ai, 'generate', return_value={'reply':reply}) as generate:
            self.assertEqual(self.ai.public_reply_preview(context), reply)
        self.assertIn('500 characters', generate.call_args.args[1])
        with patch.object(self.ai, 'generate', return_value={'reply':reply+'。'}):
            with self.assertRaises(ValueError):
                self.ai.public_reply_preview(context)

    def test_public_preview_keeps_a_complete_reply_longer_than_the_old_opening_limit(self):
        expected = (
            'We’re sorry the shared washer has remained unusable after your earlier report, especially '
            'when you need it for your normal laundry and have already tried to get an update. '
            'Could you share its brand and model, any error code on the display, and whether it starts '
            'filling with water but stops before spinning or does not start at all? '
            'Those details can help identify the relevant manual information without guessing which '
            'appliance you have or assuming what caused the fault.'
        )
        self.assertGreater(len(expected), 420)
        context = {'complaint_level': 'MODERATE', 'report': 'The shared washer is unusable after an earlier report.'}
        with patch.object(self.ai, 'generate', return_value={'reply': expected}):
            self.assertEqual(self.ai.public_reply_preview(context), expected)

    def test_public_preview_rejects_invalid_reply_objects(self):
        for result in [None, [], ['not a reply'], 'not an object', {},
                       {'reply': 'A valid-looking reply.', 'extra': 'unexpected field'},
                       {'reply': None}, {'reply': 123}, {'reply': ['not text']},
                       {'reply': ''}, {'reply': ' '}, {'reply': 'x' * 1501}]:
            with self.subTest(result=result), patch.object(self.ai, 'generate', return_value=result):
                with self.assertRaises(ValueError):
                    self.ai.public_reply_preview({'complaint_level': 'MODERATE', 'report': 'The washer will not spin.'})

    def test_public_preview_rejects_unverified_payment_causes_at_every_level(self):
        for level in ['SIMPLE', 'MODERATE', 'HIGH']:
            for cause in ['due to a payment issue', 'because of overdue payments', 'for missed payments']:
                context = {'complaint_level': level,
                           'report': 'My electricity was cut off even though I say I already paid my bill.'}
                reply = 'We’re sorry your electricity was cut off ' + cause + '. What happened when you contacted support?'
                with self.subTest(level=level, cause=cause), patch.object(self.ai, 'generate', return_value={'reply': reply}):
                    with self.assertRaisesRegex(ValueError, 'AI_UNSAFE_OUTPUT'):
                        self.ai.public_reply_preview(context)

    def test_public_preview_can_acknowledge_a_disputed_interruption_without_an_account_finding(self):
        expected = (
            'We’re sorry about the electricity interruption and lack of updates you described. '
            'Please contact tenant support privately so staff can review the account details with you.'
        )
        context = {'complaint_level': 'HIGH', 'report': 'My electricity was cut off. I say my bill is paid, but I got no update.'}
        with patch.object(self.ai, 'generate', return_value={'reply': expected}):
            self.assertEqual(self.ai.public_reply_preview(context), expected)

    def test_public_preview_checks_later_sentences_for_claimed_or_promised_work_at_every_level(self):
        unsafe_endings = [
            "We've already repaired the washing machine.",
            'We have restored the electricity.',
            'Your refund has been approved.',
            'Our technician has been dispatched to fix it.',
            'We will repair it tomorrow.',
        ]
        for level in ['SIMPLE', 'MODERATE', 'HIGH']:
            for ending in unsafe_endings:
                with self.subTest(level=level, ending=ending), patch.object(
                        self.ai, 'generate', return_value={'reply': 'We’re sorry about the issue you reported. ' + ending}):
                    with self.assertRaisesRegex(ValueError, 'AI_UNSAFE_OUTPUT'):
                        self.ai.public_reply_preview({'complaint_level': level, 'report': 'The machine stopped working.'})

    def test_public_preview_rejects_links_secrets_and_public_private_detail_requests_at_every_level(self):
        unsafe_endings = [
            'Read https://example.invalid/manual for instructions.',
            'Please post your password or OTP here.',
            'Please post your unit number and account number publicly.',
            'Email fictional-user@example.invalid to arrange help.',
            'Please call +60125551234 to arrange help.',
        ]
        for level in ['SIMPLE', 'MODERATE', 'HIGH']:
            for ending in unsafe_endings:
                with self.subTest(level=level, ending=ending), patch.object(
                        self.ai, 'generate', return_value={'reply': 'We’re sorry about the issue you reported. ' + ending}):
                    with self.assertRaisesRegex(ValueError, 'AI_UNSAFE_OUTPUT'):
                        self.ai.public_reply_preview({'complaint_level': level, 'report': 'The machine stopped working.'})

    def test_public_preview_can_acknowledge_a_reported_earlier_repair_without_claiming_new_work(self):
        expected = (
            'You reported that the washer stopped spinning again after an earlier repair. '
            'What brand and model is it, and is an error code showing now?'
        )
        context = {'complaint_level': 'MODERATE', 'report': 'Someone repaired the washer before, but it stopped spinning again.'}
        with patch.object(self.ai, 'generate', return_value={'reply': expected}):
            self.assertEqual(self.ai.public_reply_preview(context), expected)

    def test_public_preview_rejects_appliance_internal_repair_and_interlock_instructions(self):
        unsafe_checks = [
            'Remove the back panel and inspect the motor wiring.',
            'Open the casing to check the internal power board.',
            'Bypass the door interlock to see whether the washer spins.',
            'Bridge the fuse and try running another cycle.',
        ]
        for level in ['SIMPLE', 'MODERATE', 'HIGH']:
            for check in unsafe_checks:
                with self.subTest(level=level, check=check), patch.object(
                        self.ai, 'generate', return_value={'reply': 'We’re sorry the washer is not working. ' + check}):
                    with self.assertRaisesRegex(ValueError, 'AI_UNSAFE_OUTPUT'):
                        self.ai.public_reply_preview({'complaint_level': level, 'report': 'The washer will not spin.'})

    def test_malformed_json_has_fixed_diagnostic(self):
        exc=json.JSONDecodeError('Invalid JSON','Fictional response only',0)
        self.assertEqual(failure_code(exc),'AI_INVALID_JSON')

    @staticmethod
    def completion(value):
        return io.BytesIO(json.dumps({'choices': [{
            'finish_reason': 'stop', 'message': {'content': json.dumps(value)},
        }]}).encode())

    def test_explicit_legacy_direct_transport_retains_its_validation_without_native_runtime(self):
        lesson = {'id':'STYLE-TEST','text':'Ask when the appliance stopped. staff@example.com',
                  'tenant_id':'TENANT-PRIVATE'}
        context = {**self.context, 'property_version': {'id': 'PROPERTY-PRIVATE'},
                   'conversation': [{'sender': 'TENANT', 'text': 'Contact example@example.com',
                                     'case_id': 'CASE-PRIVATE'}]}
        for provider, model in hosted_ai.DEFAULT_MODELS.items():
            with self.subTest(provider=provider):
                with patch.dict(os.environ, {
                    'BELIVE_AGENT_ENGINE':'direct','BELIVE_AI_PROVIDER': provider, 'BELIVE_AI_MODEL': '', 'BELIVE_AI_KEY': 'test-key-only',
                }), patch('belive.settings.load_env'):
                    settings = load_settings()
                self.assertEqual(settings.llm_model, model)
                ai = SupportAI(settings, self.root / 'unused-memory')
                with (
                    patch('belive.ai.runtime_python', side_effect=AssertionError('native runtime called')),
                    patch('belive.hosted_ai.urlopen', side_effect=[
                        self.completion({**self.triage, 'evidence': 'description'}),
                        self.completion(self.plan),
                    ]) as request,
                ):
                    result = ai.analyse(context, [lesson])
                self.assertEqual([a['agent'] for a in result['agent_trace']],
                                 ['Complaint Analysis Agent','Support Response Agent'])
                self.assertEqual(result['evidence'], context['case']['description'])
                self.assertEqual(result['complaint_level'], 'MODERATE')
                self.assertTrue(result['requires_human'])
                self.assertEqual(result['learning_used']['example_ids'], ['STYLE-TEST'])
                for call in request.call_args_list:
                    http_request = call.args[0]
                    self.assertEqual(http_request.full_url, hosted_ai.ENDPOINTS[provider])
                    self.assertEqual(http_request.get_header('Authorization'), 'Bearer test-key-only')
                    body = json.loads(http_request.data)
                    self.assertEqual(body['model'], model)
                    self.assertEqual(body['response_format']['type'], 'json_schema')
                    self.assertNotIn('tools', body)
                    self.assertNotIn(b'test-key-only', http_request.data)
                    for private in ['PROPERTY-PRIVATE','TENANT-PRIVATE','CASE-PRIVATE','@example.com']:
                        self.assertNotIn(private.encode(), http_request.data)
                    if provider == 'openai':
                        self.assertEqual(body['reasoning_effort'], 'none')
                        self.assertEqual(body['service_tier'], 'default')
                        self.assertEqual(body['max_completion_tokens'], 2500)
                        self.assertIs(body['store'], False)
                        self.assertNotIn('provider', body)
                    else:
                        self.assertTrue(body['provider']['zdr'])
                sent = json.loads(json.loads(request.call_args.args[0].data)['messages'][1]['content'])
                self.assertEqual(sent['reviewed_examples'], [{'id':'STYLE-TEST',
                                 'text':'Ask when the appliance stopped. [email removed]'}])

    def test_hosted_connection_check_reports_missing_key_and_safe_auth_failure(self):
        for provider, model in hosted_ai.DEFAULT_MODELS.items():
            with self.subTest(provider=provider):
                settings = Settings(agent_engine='direct',llm_provider=provider, llm_model=model)
                with patch('belive.service.load_settings', return_value=settings):
                    service = Service(self.root / (provider+'.db'))
                with (
                    patch('belive.ai.runtime_python', side_effect=AssertionError('native runtime called')),
                    patch('belive.hosted_ai.urlopen') as request,
                ):
                    self.assertEqual(service.check_ai()['detail'], 'AI_NOT_CONFIGURED')
                    request.assert_not_called()
                    settings.llm_api_key = 'test-key-only'
                    request.side_effect = HTTPError(hosted_ai.ENDPOINTS[provider], 401, 'private error', {},
                                                    io.BytesIO(b'sensitive provider response'))
                    failed = service.check_ai()
                    self.assertEqual(failed['status'], 'FAILED')
                    self.assertIn('rejected the API key', failed['detail'])
                    self.assertNotIn('private error', str(failed))
                    self.assertNotIn('test-key-only', str(failed))
                    request.side_effect = None
                    request.return_value = self.completion({'ok': True})
                    passed = service.check_ai()
                    self.assertEqual(passed['status'], 'PASSED')
                    self.assertEqual(passed['model'], model)
                    self.assertEqual(json.loads(json.loads(request.call_args.args[0].data)['messages'][1]['content']),
                                     {'context':{'check':'connection only; no tenant data'},'reviewed_examples':[]})

if __name__=='__main__':unittest.main()
