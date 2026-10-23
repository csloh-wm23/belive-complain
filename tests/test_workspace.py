"""Database selection and durable records, using temporary files only."""
import secrets
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from belive.service import Service
from belive.workspace import selected_database,validate_database_path,save_selection
from test_backend import FakeAI

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.active=self.root/'active.db';self.config=self.root/'workspace.json'
        self.service=Service(self.active,FakeAI(),workspace_config=self.config)
    def tearDown(self):self.tmp.cleanup()
    def command(self,name,p):return self.service.command(name,p,secrets.token_hex(16))
    def test_selection_persists_without_moving_active_records(self):
        self.command('condo',dict(id='C-A',name='Fictional property',rules='Verified test support guidance.',confirmed=True))
        target=self.root/'Selected workspace.db'
        self.command('database_location',{'path':str(target)})
        snapshot=self.service.snapshot()
        self.assertEqual(snapshot['storage']['active'],str(self.active));self.assertEqual(snapshot['storage']['selected'],str(target))
        self.assertTrue(snapshot['storage']['restart_required']);self.assertFalse(target.exists())
        self.assertEqual(selected_database(self.config),target)
        reopened=Service(self.active,FakeAI(),workspace_config=self.config)
        self.assertEqual(reopened.snapshot()['condos'][0]['id'],'C-A')
        switched=Service(selected_database(self.config),FakeAI(),workspace_config=self.config)
        self.assertEqual(switched.snapshot()['condos'],[]);self.assertFalse(switched.snapshot()['storage']['restart_required'])
        self.assertEqual(reopened.snapshot()['condos'][0]['id'],'C-A')
    def test_reject_unrelated_database_without_modifying_it(self):
        foreign=self.root/'unrelated.db'
        with closing(sqlite3.connect(foreign)) as db:db.execute('CREATE TABLE private_data(value TEXT)')
        before=foreign.read_bytes()
        with self.assertRaisesRegex(ValueError,'not a BeLive'):save_selection(self.config,foreign)
        self.assertEqual(before,foreign.read_bytes());self.assertFalse(self.config.exists())
        self.assertEqual(validate_database_path(self.active),self.active)
        bad=self.root/'text.db';bad.write_text('This is not SQLite.')
        with self.assertRaisesRegex(ValueError,'not a readable SQLite'):validate_database_path(bad)
        with self.assertRaisesRegex(ValueError,'absolute SQLite'):validate_database_path('relative.db')
    def test_source_checks_default_on_and_pause_survives_restart(self):
        source=self.command('source',dict(platform='GOOGLE',resource='accounts/1/locations/2',authorised=True))
        self.assertTrue(source['enabled'])
        self.command('source',{**source,'enabled':False})
        reopened=Service(self.active,FakeAI(),workspace_config=self.config)
        self.assertFalse(reopened.snapshot()['sources'][0]['enabled'])
