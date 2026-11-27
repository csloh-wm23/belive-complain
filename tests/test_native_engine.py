"""Native Hermes must be the default executor, never a model-name based label."""
import json,secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from belive.settings import Settings
from belive import hosted_ai,decisions
from belive.ai import SupportAI
from belive.service import Service
from test_backend import FakeAI

class NativeEngineTests(unittest.TestCase):
    def settings(self):return Settings(llm_provider='openai',llm_model=hosted_ai.DEFAULT_MODELS['openai'],llm_api_key=secrets.token_urlsafe(24))
    def test_openai_model_does_not_implicitly_bypass_native_hermes(self):
        settings=self.settings();self.assertEqual(settings.agent_engine,'hermes');self.assertFalse(hosted_ai.uses_direct_api(settings))
        settings.decisions_enabled=True;self.assertFalse(decisions.enabled(settings))
    def test_structured_generation_uses_native_agent_and_passes_images_without_direct_call(self):
        settings=self.settings();schema={'type':'object','properties':{'ok':{'type':'boolean'}}}
        with patch('belive.hermes_native.native_request',return_value={'text':'{"ok":true}'}) as native,patch('belive.hosted_ai.urlopen',side_effect=AssertionError('Unexpected direct API')):
            result=hosted_ai.generate(settings,[{'role':'system','content':'Neutral test'}],{'query':'a fictional question'},[],schema,images=['data:image/png;base64,TEST'])
        self.assertEqual(json.loads(result['text']),{'ok':True});native.assert_called_once();self.assertEqual(native.call_args.kwargs['response_schema'],schema)
        self.assertEqual(native.call_args.args[0][1]['content'][1]['type'],'image_url')
    def test_missing_native_runtime_does_not_fall_back_to_direct_provider(self):
        settings=self.settings()
        with patch('belive.ai.runtime_python',side_effect=RuntimeError('HERMES_NOT_INSTALLED')):self.assertFalse(SupportAI(settings,Path('unused')).readiness())
        with patch('belive.hermes_native.runtime_python',side_effect=RuntimeError('HERMES_NOT_INSTALLED')),patch('belive.hosted_ai.urlopen',side_effect=AssertionError('Unexpected fallback')):
            with self.assertRaisesRegex(RuntimeError,'HERMES_NOT_INSTALLED'):hosted_ai.generate(settings,[{'role':'system','content':'Neutral test'}],{},[],None)
    def test_engine_evidence_rejects_wrong_engine_and_excludes_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Service(Path(tmp)/'qa.db',FakeAI())
            with self.assertRaises(ValueError):s.record_native_execution({'engine':'direct','agent_class':'run_agent.AIAgent'})
            secret=secrets.token_urlsafe(24);s.record_native_execution({'engine':'hermes-native','agent_class':'run_agent.AIAgent','role':'QA','api_key':secret,'customer_text':'private test text'})
            with s.store.connect() as db:stored=json.dumps(s.store.all(db,'native_execution'))
            self.assertNotIn(secret,stored);self.assertNotIn('private test text',stored)
    def test_direct_transport_requires_an_explicit_legacy_selection(self):
        settings=self.settings();settings.agent_engine='direct';self.assertTrue(hosted_ai.uses_direct_api(settings))

    def test_public_preview_uses_native_role_without_examples_or_direct_transport(self):
        settings = self.settings()
        context = {'complaint_level': 'MODERATE', 'report': 'The shared washer will not spin.',
                   'assessment_summary': 'Reported washer fault after an earlier request.'}
        expected = (
            'We’re sorry the washer is still not spinning after your earlier report. '
            'What brand and model is it, and is an error code showing?'
        )
        with tempfile.TemporaryDirectory() as tmp, \
                patch('belive.ai.runtime_python', return_value='fixture-native-runtime'), \
                patch('belive.ai.native_request', return_value={'text': json.dumps({'reply': expected})}) as native, \
                patch('belive.hosted_ai.urlopen', side_effect=AssertionError('Unexpected direct transport')) as direct:
            reply = SupportAI(settings, Path(tmp) / 'memory').public_reply_preview(context)
        self.assertEqual(reply, expected)
        native.assert_called_once()
        direct.assert_not_called()
        self.assertEqual(native.call_args.kwargs['role'], 'Public Reply Preview Agent')
        self.assertEqual(native.call_args.kwargs['examples'], [])
        self.assertEqual(native.call_args.kwargs['dispatch']('read_reviewed_styles', {}), {'styles': []})
        self.assertEqual(json.loads(native.call_args.args[0][1]['content']), context)
        self.assertNotIn(settings.llm_api_key, json.dumps(native.call_args.args[0]))

    def test_public_preview_missing_native_runtime_never_returns_a_fallback_draft(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch('belive.ai.runtime_python', side_effect=RuntimeError('HERMES_NOT_INSTALLED')), \
                patch('belive.ai.native_request') as native, \
                patch('belive.hosted_ai.urlopen', side_effect=AssertionError('Unexpected direct fallback')) as direct:
            with self.assertRaises(RuntimeError):
                SupportAI(self.settings(), Path(tmp) / 'memory').public_reply_preview({
                    'complaint_level': 'MODERATE', 'report': 'The shared washer will not spin.',
                })
        native.assert_not_called()
        direct.assert_not_called()

if __name__=='__main__':unittest.main()
