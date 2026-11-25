"""Private credential storage and database-scoped platform reads; no external requests."""
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from belive.service import Service
from belive.settings import load_settings
from belive import credentials as c
from belive.connectors import read_source
from test_backend import FakeAI


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env_key = secrets.token_urlsafe(40)
        self.db_key = secrets.token_urlsafe(40)
        self.environment = patch.dict(os.environ, {'BELIVE_AI_PROVIDER': 'openai', 'BELIVE_AI_MODEL': 'fixture-model',
            'BELIVE_AI_KEY': self.env_key, 'BELIVE_FACEBOOK_TOKEN': self.env_key, 'BELIVE_FACEBOOK_VERSION': 'v24.0'}, clear=True)
        self.environment.start()
        self.root_patch = patch('belive.settings.ROOT', self.root);self.root_patch.start()
        self.s = Service(self.root / 'test.db', FakeAI())
    def tearDown(self):
        self.root_patch.stop();self.environment.stop();self.tmp.cleanup()
    def save(self, values=None, remove=None, version=None):
        return c.save(self.s, {'values': values or {}, 'remove': remove or [],
            'version': c.load(self.s.store.path)['version'] if version is None else version}, 'credential-qa')
    def test_ciphertext_only_and_no_secrets_in_status_snapshot_audit_or_repr(self):
        result = self.save({'BELIVE_AI_KEY': self.db_key})
        self.assertEqual(c.get_value('BELIVE_AI_KEY', database=self.s.store.path), self.db_key)
        with self.s.store.connect() as db:
            raw = db.execute('SELECT ciphertext FROM private_credentials').fetchone()[0]
            objects = json.dumps(self.s.store.audit(db)) + json.dumps(self.s.store.all(db, 'health'))
        for public in (json.dumps(result), json.dumps(self.s.snapshot()), objects, repr(load_settings(self.s.store.path)), raw):
            self.assertNotIn(self.db_key, public);self.assertNotIn(self.env_key, public)
        self.assertEqual(self.s.settings.llm_api_key, self.db_key)
        self.assertTrue(c.key_path(self.s.store.path).is_file())
        self.assertEqual(next(f for f in result['fields'] if f['name']=='BELIVE_AI_KEY')['source'], 'database')
    def test_environment_is_unchanged_and_removing_override_restores_explicit_fallback(self):
        self.save({'BELIVE_AI_KEY': self.db_key})
        self.assertEqual(os.environ['BELIVE_AI_KEY'], self.env_key)
        self.assertEqual(c.get_value('BELIVE_AI_KEY'), self.env_key)
        self.save(remove=['BELIVE_AI_KEY'])
        self.assertEqual(self.s.settings.llm_api_key, self.env_key)
        self.assertEqual(c.get_value('BELIVE_AI_KEY', database=self.s.store.path), self.env_key)
    def test_context_scopes_do_not_leak_between_databases_and_platform_reads_use_store(self):
        other = Service(self.root / 'other.db', FakeAI())
        self.save({'BELIVE_FACEBOOK_TOKEN': self.db_key})
        other_key = secrets.token_urlsafe(40)
        c.save(other, {'version': 0, 'values': {'BELIVE_FACEBOOK_TOKEN': other_key}}, 'credential-qa')
        with patch('belive.connectors.request_json', return_value={'data': []}) as request:
            with c.credential_scope(self.s.store.path):
                read_source({'platform': 'FACEBOOK', 'resource': '123/feed'})
                self.assertEqual(request.call_args.args[1], self.db_key)
                with c.credential_scope(other.store.path):self.assertEqual(c.get_value('BELIVE_FACEBOOK_TOKEN'), other_key)
                self.assertEqual(c.get_value('BELIVE_FACEBOOK_TOKEN'), self.db_key)
        self.assertEqual(c.get_value('BELIVE_FACEBOOK_TOKEN'), self.env_key)
    def test_missing_key_and_tampering_lock_tokens_instead_of_silent_env_fallback(self):
        self.save({'BELIVE_AI_KEY': self.db_key, 'BELIVE_FACEBOOK_TOKEN': self.db_key})
        key = c.key_path(self.s.store.path);original = key.read_bytes();key.unlink()
        self.assertEqual(c.status(self.s.store.path)['status'], 'LOCKED')
        self.assertEqual(c.get_value('BELIVE_AI_KEY', database=self.s.store.path), '')
        self.assertEqual(c.get_value('BELIVE_FACEBOOK_TOKEN', database=self.s.store.path), '')
        key.write_bytes(original)
        with self.s.store.connect() as db:db.execute("UPDATE private_credentials SET ciphertext='bad'")
        self.assertEqual(c.status(self.s.store.path)['status'], 'LOCKED')
        self.assertEqual(c.get_value('BELIVE_AI_KEY', database=self.s.store.path), '')
    def test_stale_save_and_invalid_settings_do_not_replace_current_values(self):
        self.save({'BELIVE_AI_KEY': self.db_key})
        with self.assertRaisesRegex(ValueError, 'changed'):self.save({'BELIVE_AI_KEY': 'another'}, version=0)
        for values in ({'UNSUPPORTED': 'value'}, {'BELIVE_AI_PROVIDER':'wrong'}, {'BELIVE_AI_MODEL':'bad model'},
                       {'BELIVE_WHATSAPP_PHONE_NUMBER_ID':'not-a-number'}, {'BELIVE_FACEBOOK_VERSION':'bad'},
                       {'BELIVE_NOTIFICATION_URL':'http://example.test'}, {'BELIVE_AI_KEY':'bad\nvalue'}):
            with self.subTest(keys=list(values)):
                with self.assertRaises(ValueError):self.save(values)
        self.assertEqual(c.get_value('BELIVE_AI_KEY', database=self.s.store.path), self.db_key)
    def test_knowledge_export_excludes_credentials_and_private_backup_has_only_ciphertext(self):
        from belive import repository_memory as rm
        from belive.backups import copy_database
        self.save({'BELIVE_AI_KEY':self.db_key})
        rm.configure(self.s)
        exported=json.dumps(rm.payload(self.s))
        self.assertNotIn(self.db_key,exported);self.assertNotIn('private_credentials',exported)
        recovery=self.root/'recovery';recovery.mkdir();target=recovery/'copy.db'
        copy_database(self.s.store.path,target)
        self.assertEqual(c.status(target)['status'],'LOCKED')
        self.assertNotIn(self.db_key,target.read_bytes().decode('latin1'))

    def test_database_configuration_does_not_switch_native_hermes_engine(self):
        self.save({'BELIVE_AI_PROVIDER':'openai','BELIVE_AI_MODEL':'gpt-6-luna','BELIVE_AI_KEY':self.db_key})
        self.assertEqual(self.s.settings.agent_engine, 'hermes')
        self.assertEqual(self.s.settings.llm_model, 'gpt-6-luna')
        with self.assertRaises(ValueError):self.save({'BELIVE_AGENT_ENGINE':'direct'})

if __name__=='__main__':unittest.main()
