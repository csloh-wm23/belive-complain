"""Optional installed-Hermes test: no model or provider request is made."""
import shutil
import tempfile
import unittest
from pathlib import Path
from belive.ai import SupportAI
from belive.settings import Settings
from belive.hermes_native import memory_snapshot

@unittest.skipUnless(shutil.which('hermes'),'Native Hermes is not installed')
class NativeMemoryTests(unittest.TestCase):
    def test_current_projection_persists_and_revokes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ai=SupportAI(Settings(),Path(tmp)/'isolated-hermes')
            result=ai.sync([{'id':'TEST-STYLE','text':'Ask one concise clarification at a time.'}])
            self.assertEqual(result['entries'],1)
            self.assertIn('TEST-STYLE',memory_snapshot(ai.home))
            self.assertEqual(ai.sync([])['entries'],0)
            self.assertNotIn('TEST-STYLE',memory_snapshot(ai.home))
