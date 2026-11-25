"""Rehearsals borrow active model settings without copying private credentials."""
import base64
import importlib.util
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive import credentials
from belive.service import Service
from test_backend import FakeAI

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rehearsal_setup_test',ROOT/'scripts'/'rehearse_native_support.py')
rehearsal=importlib.util.module_from_spec(spec);spec.loader.exec_module(rehearsal)


class NativeRehearsalSetupTests(unittest.TestCase):
    def test_database_only_model_configuration_is_used_without_copying_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);active_path=root/'active'/'support.db';active_path.parent.mkdir()
            generated_key=secrets.token_urlsafe(40)
            with patch.dict(os.environ,{'BELIVE_AGENT_ENGINE':'hermes'},clear=True),patch('belive.settings.ROOT',root):
                active=Service(active_path,FakeAI())
                credentials.save(active,{'version':0,'values':{'BELIVE_AI_PROVIDER':'openai','BELIVE_AI_MODEL':'fixture-rehearsal-model','BELIVE_AI_KEY':generated_key}},'fixture-admin')
                (active_path.parent/'knowledge-backup.key').write_text(base64.b64encode(secrets.token_bytes(32)).decode(),encoding='ascii')
                runtime=root/'native-python.exe'
                metadata={'version':'v0.23.3','commit':'fixture-pinned-commit','python':str(runtime)}
                with patch.object(rehearsal,'selected_database',return_value=active_path),patch.object(rehearsal,'runtime_info',return_value=metadata),patch.object(rehearsal,'runtime_python',return_value=runtime),patch('belive.ai.runtime_python',return_value=runtime),patch.object(rehearsal.repository_memory,'import_key',return_value={'records':0,'documents':0}):
                    isolated=rehearsal.setup(root/'isolated')
                self.assertEqual(isolated.settings.llm_api_key,generated_key)
                self.assertEqual(isolated.settings.llm_model,'fixture-rehearsal-model')
                self.assertEqual(isolated.settings.agent_engine,'hermes')
                self.assertIs(isolated.ai.settings,isolated.settings)
                self.assertNotIn('BELIVE_AI_KEY',os.environ)
                self.assertNotIn(generated_key,repr(isolated.settings))
                self.assertNotIn(generated_key,isolated.store.path.read_bytes().decode('latin1'))
                with isolated.store.connect() as db:
                    table=db.execute("SELECT 1 FROM sqlite_master WHERE name='private_credentials'").fetchone()
                    self.assertFalse(table)
                self.assertEqual(credentials.get_value('BELIVE_AI_KEY',database=active_path),generated_key)


if __name__=='__main__':unittest.main()
