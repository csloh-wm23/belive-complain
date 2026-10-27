"""Regression checks for tenant-report evidence, safe diagnostics and recovery."""
import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive.ai import SupportAI,failure_code
from belive.service import Service
from belive.settings import Settings
from test_backend import FakeAI

class AIValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ai=SupportAI(Settings(),self.root/'memory')
        self.context={'case':{'title':'my pipe broke','description':'no one comes and fix it'},
                      'verified_records':[],'tenant_verified':True,
                      'conversation':[{'text':'A conversation-only excerpt.'}]}
        self.triage=dict(relevance='SUPPORT',category='MAINTENANCE',severity='MEDIUM',
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
    def test_quotes_from_other_context_or_paraphrases_are_rejected(self):
        context={**self.context,'verified_records':[{'id':'R','text':'A record-only excerpt.'}]}
        for evidence in ['the pipe is broken','My pipe broke','A record-only excerpt.','A conversation-only excerpt.','',123]:
            with self.subTest(evidence=evidence),patch.object(self.ai,'generate',return_value={**self.triage,'evidence':evidence}) as generate:
                with self.assertRaisesRegex(ValueError,'AI_UNGROUNDED_EVIDENCE'):self.ai.analyse(context,[])
                self.assertEqual(generate.call_count,1)
    def test_title_quote_does_not_bypass_schema_checks(self):
        with patch.object(self.ai,'generate',return_value={**self.triage,'uncertainty':'false'}):
            with self.assertRaisesRegex(ValueError,'AI_INVALID_VALUES'):self.ai.analyse(self.context,[])
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
    def test_malformed_json_has_fixed_diagnostic(self):
        exc=json.JSONDecodeError('Invalid JSON','Fictional response only',0)
        self.assertEqual(failure_code(exc),'AI_INVALID_JSON')

if __name__=='__main__':unittest.main()
