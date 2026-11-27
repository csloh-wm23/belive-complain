"""Optional installed-Hermes test: no model or provider request is made."""
import shutil
import tempfile
import unittest
from pathlib import Path
from belive.ai import SupportAI
from belive.settings import Settings
from belive.hermes_native import memory_snapshot,runtime_python,native_request,close_workers

def installed():
    try:runtime_python();return True
    except RuntimeError:return False

@unittest.skipUnless(installed(),'Native Hermes is not installed')
class NativeMemoryTests(unittest.TestCase):
    def test_warm_worker_reloads_revocations_and_isolates_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                home=Path(tmp)/'customer-one'
                first=native_request([],Settings(),mode='memory',home=home,keep_warm=True,examples=[{'version_id':'FICTIONAL','approved_reply':'Use one short question.'}])
                second=native_request([],Settings(),mode='memory',home=home,keep_warm=True,examples=[])
                other=native_request([],Settings(),mode='memory',home=Path(tmp)/'customer-two',keep_warm=True,examples=[])
                self.assertFalse(first['reused_worker']);self.assertTrue(second['reused_worker'])
                self.assertEqual(first['entries'],1);self.assertEqual(second['entries'],0)
                self.assertNotIn('FICTIONAL',second['memory'])
                self.assertFalse(other['reused_worker']);self.assertEqual(other['entries'],0)
                self.assertEqual(second['api_calls'],0)
            finally:close_workers()

    def test_current_projection_persists_and_revokes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ai=SupportAI(Settings(),Path(tmp)/'isolated-hermes')
            result=ai.sync([{'id':'TEST-STYLE','text':'Ask one concise clarification at a time.'}])
            self.assertEqual(result['entries'],1)
            self.assertIn('TEST-STYLE',memory_snapshot(ai.home))
            self.assertEqual(ai.sync([])['entries'],0)
            self.assertNotIn('TEST-STYLE',memory_snapshot(ai.home))
