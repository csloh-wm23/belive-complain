"""Encrypted knowledge pushes restore usable memory, not private customer databases."""
import base64,copy,json,secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from belive import repository_memory as rm,shared_memory as sm
from belive.service import Service
from test_backend import FakeAI

class RepositoryMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.archive=self.root/'team-memory.enc.json';self.a=Service(self.root/'a'/'app.db',FakeAI());self.b=Service(self.root/'b'/'app.db',FakeAI())
    def tearDown(self):self.tmp.cleanup()
    def seed(self):
        self.a.command('wa_knowledge',{'title':'Fictional Wi-Fi SOP','text':'Ask which devices are affected before giving a safe phone-side check.','source':'Reviewed fictional source','confirmed':True},secrets.token_hex(16))
        with self.a.store.connect() as db:
            self.a.store.put(db,'case',{'id':'PRIVATE','status':'CLOSED','category':'WIFI','description':'SECRET-CUSTOMER','sample_data':True})
            self.a.store.put(db,'feedback',{'id':'APPROVED','case_id':'PRIVATE','verdict':'CORRECTED','public_question':'Why does my Wi-Fi disconnect?','text':'Check whether the issue affects other devices before changing settings.'})
            self.a.store.put(db,'reply_learning',{'id':'APPROVED-TIP','case_id':'PRIVATE','question':'SECRET-CUSTOMER asks about Wi-Fi','reply':'SECRET-REPLY','customer_feedback':'SECRET-FEEDBACK','tip':'Acknowledge what was already tried and avoid repeating that step.','status':'APPROVED','approved':True,'revision':1,'scope_condo':None,'category':'WIFI','sample_data':True})
    def export(self):return rm.export(self.a,self.archive)
    def restore(self):return rm.restore(self.b,self.archive,key=rm.read_key(self.a))
    def test_encrypted_round_trip_restores_sop_experiences_and_tips_for_retrieval(self):
        self.seed();self.assertEqual(self.export()['records'],3);self.restore()
        from belive.experience_learning import experiences
        from belive.reply_learning import matching
        with self.b.store.connect() as db:
            self.assertEqual(len(sm.knowledge(self.b,db)),1);self.assertEqual(experiences(self.b,db)[0]['id'],'SHARED-APPROVED');self.assertEqual(matching(self.b,db,'Wi-Fi keeps disconnecting')[0]['id'],'SHARED-APPROVED-TIP');self.assertEqual(self.b.store.all(db,'case'),[])
        encrypted=self.archive.read_text();self.assertNotIn('phone-side',encrypted);self.assertNotIn('SECRET',encrypted)
        plain=json.dumps(rm.unpack(json.loads(encrypted),rm.read_key(self.a)));self.assertNotIn('SECRET',plain);self.assertNotIn('customer_feedback',plain)
    def test_bad_key_and_tampering_do_not_change_existing_knowledge(self):
        self.seed();self.export();before=self.b.snapshot()
        with self.assertRaises(ValueError):rm.restore(self.b,self.archive,key=secrets.token_bytes(32))
        self.assertEqual(self.b.snapshot()['cases'],before['cases'])
        envelope=json.loads(self.archive.read_text());cipher=bytearray(base64.b64decode(envelope['ciphertext']));cipher[0]^=1;envelope['ciphertext']=base64.b64encode(cipher).decode();self.archive.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError):self.restore()
        with self.b.store.connect() as db:self.assertEqual(self.b.store.all(db,'memory_record'),[])
    def test_revocation_survives_restore_and_origin_sync_without_resurrection(self):
        self.seed();self.export();self.restore()
        with self.a.store.connect() as db:r=next(x for x in self.a.store.all(db,'memory_record') if x['kind']=='experience')
        sm.change(self.a,{'key':r['key'],'revision':r['revision'],'enabled':False,'confirmed':True});self.export();self.restore();sm.sync(self.a);sm.sync(self.b)
        with self.b.store.connect() as db:self.assertEqual(sm.experiences(self.b,db),[])
        with self.a.store.connect() as db:self.assertEqual(sm.experiences(self.a,db),[])
    def test_unchanged_export_keeps_same_ciphertext_and_key(self):
        self.seed();self.export();before=self.archive.read_bytes();self.assertFalse(self.export()['changed']);self.assertEqual(self.archive.read_bytes(),before)
    def test_pull_preserves_concurrent_local_proposal_for_review(self):
        self.seed();self.export();self.restore()
        for service,text in ((self.a,'Updated approved rule from the first computer.'),(self.b,'Different local proposal from the second computer.')):
            with service.store.connect() as db:r=service.store.all(db,'wa_knowledge')[0];r['text']=text;service.store.put(db,'wa_knowledge',r)
        self.export();self.restore()
        with self.b.store.connect() as db:
            conflicts=self.b.store.all(db,'memory_conflict');self.assertEqual(len(conflicts),1);self.assertIn('Different local',conflicts[0]['local_value']['text']);self.assertIn('first computer',sm.knowledge(self.b,db)[0]['text'])
        with self.assertRaises(ValueError):rm.export(self.b,self.root/'b.enc.json')
        sm.resolve(self.b,{'id':conflicts[0]['id'],'choice':'local','confirmed':True,'remote_revision':conflicts[0]['remote_revision']})
        with self.b.store.connect() as db:self.assertIn('Different local',sm.knowledge(self.b,db)[0]['text'])
    def test_startup_requests_key_then_restores_only_when_archive_changes(self):
        self.seed();self.export();rm.startup(self.b,self.archive)
        with self.b.store.connect() as db:self.assertEqual(self.b.store.all(db,'repository_backup')[0]['status'],'RESTORE_REQUIRED')
        rm.key_path(self.b).write_bytes(rm.key_path(self.a).read_bytes());rm.startup(self.b,self.archive)
        with patch('belive.repository_memory.restore') as restore:rm.startup(self.b,self.archive);restore.assert_not_called()
    def test_source_pdf_is_encrypted_restored_and_verified(self):
        import hashlib
        self.seed();body=b'%PDF synthetic source';sha=hashlib.sha256(body).hexdigest();directory=self.a.store.path.parent/'company_documents';directory.mkdir();(directory/(sha+'.pdf')).write_bytes(body)
        with self.a.store.connect() as db:self.a.store.put(db,'sop_document',{'id':'DOC-QA','sha256':sha,'filename':'synthetic.pdf','active':True,'revision':1})
        self.export();self.restore();self.assertEqual((self.b.store.path.parent/'company_documents'/(sha+'.pdf')).read_bytes(),body)
        (directory/(sha+'.pdf')).write_bytes(b'corrupted')
        with self.assertRaises(ValueError):self.export()
    def test_push_check_rejects_stale_knowledge_before_attempting_git(self):
        from scripts import knowledge_backup
        self.seed();self.export()
        with self.a.store.connect() as db:r=self.a.store.all(db,'wa_knowledge')[0];r['text']='This new approved guidance has not been exported yet.';self.a.store.put(db,'wa_knowledge',r)
        with patch('sys.argv',['knowledge_backup.py','check','--database',str(self.a.store.path)]),patch('belive.repository_memory.ARCHIVE',self.archive),patch('scripts.knowledge_backup.subprocess.run') as git:
            with self.assertRaisesRegex(ValueError,'Knowledge changed'):knowledge_backup.main()
            git.assert_not_called()

if __name__=='__main__':unittest.main()
