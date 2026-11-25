"""Private knowledge safety backup is current, but never part of code publication."""
import contextlib
import io
import os
import secrets
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive import repository_memory as rm
from scripts import knowledge_backup, build_peer_package
from test_backend import FakeAI


class PrivatePublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        # A caller may inherit an incomplete GIT_CONFIG_* bundle; these repos must use only their own index.
        environment={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
        environment.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
        isolated=patch.dict(os.environ,environment,clear=True);isolated.start();self.addCleanup(isolated.stop)
        self.git('init','-q')
        self.s=Service(self.root/'data'/'case.db',FakeAI())
        self.s.command('wa_knowledge',dict(title='Fictional reporting guidance',text='Report the shared washer display; do not attempt a repair.',
                       source='Reviewed fictional test source',confirmed=True),secrets.token_hex(16))
        self.archive=self.root/'knowledge'/'team-memory.enc.json'
        rm.export(self.s,self.archive)
        self.archive_patch=patch('belive.repository_memory.ARCHIVE',self.archive);self.archive_patch.start();self.addCleanup(self.archive_patch.stop)

    def git(self,*args):
        result=subprocess.run(['git',*args],cwd=self.root,capture_output=True)
        diagnostic=result.stderr.decode('utf-8',errors='replace').replace(str(self.root),'[temporary repository]')
        self.assertEqual(result.returncode,0,'Temporary Git '+args[0]+' failed: '+diagnostic[:2000])
        return result

    def stage(self,name):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_text('Fictional test content only.',encoding='utf-8')
        self.git('add','--force','--',name)

    def check(self):return knowledge_backup.check(self.s,self.root)

    def test_current_private_export_allows_code_only_index_without_tracking_archive(self):
        self.stage('main.py');self.stage('.env.example')
        result=self.check()
        self.assertTrue(result['private_backup_current']);self.assertTrue(result['git_index_excludes_private_files'])
        self.assertNotIn(b'team-memory.enc.json',self.git('ls-files','--cached').stdout)
        self.assertTrue(self.archive.is_file());self.assertTrue(rm.key_path(self.s).is_file())

    def test_force_staged_encrypted_archive_blocks_push_and_stays_local(self):
        self.stage('knowledge/team-memory.enc.json')
        with self.assertRaisesRegex(ValueError,'staged/tracked'):self.check()
        self.assertTrue(self.archive.is_file())

    def test_other_indexed_private_paths_block_push(self):
        names=['knowledge/custom-export.enc.json','knowledge/source.pdf','.env','.env.production','data/case.db','knowledge-backup.key','private/.belive-credentials.key',
               'company_documents/source.pdf','shared_memory/store.json','whatsapp_media/photo.png',
               'backups/snapshot.json','artifacts/private-report.json','nested/store.sqlite3','nested/store.db-wal','memory-pairing.json']
        for name in names:
            with self.subTest(name=name):
                self.stage(name)
                with self.assertRaisesRegex(ValueError,'staged/tracked'):self.check()
                self.git('rm','--cached','--force','--',name)
                self.assertTrue((self.root/name).is_file())

    def test_missing_private_export_blocks_push_without_requesting_a_commit(self):
        self.archive.unlink()
        with self.assertRaisesRegex(ValueError,'Private knowledge backup is missing') as error:self.check()
        self.assertNotIn('commit',str(error.exception).lower())

    def test_git_index_failure_blocks_publication(self):
        with patch('scripts.knowledge_backup.subprocess.run',side_effect=subprocess.CalledProcessError(1,['git'])):
            with self.assertRaisesRegex(ValueError,'Git index could not be checked'):self.check()

    def test_source_peer_zip_excludes_even_forced_tracked_private_material(self):
        private=['knowledge/custom-export.enc.json','knowledge/team-memory.enc.json','knowledge-backup.key','.env','private/.belive-credentials.key','company_documents/source.pdf']
        for name in ['main.py','.env.example',*private]:self.stage(name)
        with patch('scripts.build_peer_package.ROOT',self.root),contextlib.redirect_stdout(io.StringIO()):build_peer_package.main()
        with zipfile.ZipFile(self.root/'artifacts'/'belive-shared-memory-client.zip') as archive:
            names=archive.namelist()
            self.assertIn('main.py',names);self.assertIn('.env.example',names)
            self.assertTrue(all(name not in names for name in private))
            self.assertIn('SHARED_MEMORY_PACKAGE.json',names)


if __name__=='__main__':unittest.main()
