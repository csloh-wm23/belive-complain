"""Two independent databases sharing one authenticated, knowledge-only hub."""
import hashlib,json,secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from belive.service import Service
from belive import shared_memory as sm,whatsapp as wa
from belive.memory_hub import Hub,serve
from test_backend import FakeAI
from test_whatsapp import fixture_assessment,plan

class SharedMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.a=Service(self.root/'a'/'a.db',FakeAI());self.b=Service(self.root/'b'/'b.db',FakeAI())
        self.tokens=['host-'+secrets.token_urlsafe(36),'peer-'+secrets.token_urlsafe(36)];self.wid='MEM-'+secrets.token_hex(12)
        self.hub=Hub(self.root/'hub'/'knowledge.db',self.wid,{self.tokens[0]:'Host',self.tokens[1]:'Peer'});self.server=serve(self.hub,0);self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        from belive.hermes_native import close_workers
        close_workers();self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def cmd(self,s,name,**p):return s.command(name,p,secrets.token_hex(16))
    def rows(self,s,kind):
        with s.store.connect() as db:return s.store.all(db,kind)
    def pair(self,s,index):return sm.configure(s,{'url':self.url,'token':self.tokens[index],'workspace_id':self.wid})
    def sop(self,s):return self.cmd(s,'wa_knowledge',title='Fictional Wi-Fi support',text='Ask which devices are affected before giving a safe phone-side check.',source='Reviewed fictional support source',confirmed=True)
    def edit(self,s,text=None,active=True):
        old=self.rows(s,'wa_knowledge')[0];return self.cmd(s,'wa_knowledge',**{**old,'text':text or old['text'],'active':active,'confirmed':True})
    def shared(self,s,kind):
        with s.store.connect() as db:return sm.records(s,db,kind)
    def seed_learning(self):
        with self.a.store.connect() as db:
            self.a.store.put(db,'case',{'id':'CASE-PRIVATE','status':'CLOSED','category':'WIFI','sample_data':True,'description':'Secret customer conversation marker'})
            self.a.store.put(db,'feedback',{'id':'EXP-A','case_id':'CASE-PRIVATE','verdict':'CORRECTED','public_question':'What should I check when my Wi-Fi disconnects?','text':'Check which devices are affected and try reconnecting the phone.'})
            self.a.store.put(db,'reply_learning',{'id':'TIP-A','case_id':'CASE-PRIVATE','question':'I am SecretAlice in SecretRoom17 and my Wi-Fi drops.','reply':'Secret original private customer reply','customer_feedback':'Secret private complaint follow-up','tip':'Acknowledge previous checks and avoid repeating steps already tried.','status':'APPROVED','approved':True,'revision':1,'scope_condo':None,'category':'WIFI','sample_data':True})
    def test_two_way_sop_updates_share_one_workspace(self):
        self.sop(self.a);self.assertEqual(self.pair(self.a,0)['status'],'ONLINE');self.pair(self.b,1)
        self.assertEqual(self.shared(self.a,'sop'),self.shared(self.b,'sop'))
        self.edit(self.b,'Ask about the affected device and whether it works on another network.');sm.sync(self.b);sm.sync(self.a)
        self.assertEqual(self.shared(self.a,'sop'),self.shared(self.b,'sop'));self.assertIn('another network',self.shared(self.a,'sop')[0]['text'])
    def test_approved_experiences_and_tips_are_retrieved_by_both_without_customer_text(self):
        self.seed_learning();self.pair(self.a,0);self.pair(self.b,1)
        self.assertEqual(self.shared(self.a,'experience'),self.shared(self.b,'experience'));self.assertEqual(self.shared(self.a,'tip'),self.shared(self.b,'tip'))
        text=json.dumps(self.hub.snapshot());self.assertNotIn('Secret',text);self.assertNotIn('customer_feedback',text);self.assertNotIn('password_hash',text)
        from belive.reply_learning import matching
        with self.b.store.connect() as db:self.assertEqual(matching(self.b,db,'My Wi-Fi keeps disconnecting')[0]['id'],'SHARED-TIP-A')
        from belive.experience_learning import experiences
        with self.b.store.connect() as db:self.assertEqual(experiences(self.b,db)[0]['id'],'SHARED-EXP-A')
    def test_peer_revocation_does_not_get_resurrected_by_original_owner(self):
        self.seed_learning();self.pair(self.a,0);self.pair(self.b,1)
        with self.b.store.connect() as db:item=self.b.store.get(db,'memory_record','tip:TIP-A')
        sm.change(self.b,{'key':item['key'],'revision':item['revision'],'enabled':False,'confirmed':True})
        sm.sync(self.a);sm.sync(self.a);sm.sync(self.b)
        self.assertFalse(self.shared(self.a,'tip')[0]['enabled']);self.assertFalse(self.shared(self.b,'tip')[0]['enabled'])
        with self.a.store.connect() as db:self.assertEqual(sm.tips(self.a,db),[])
        with self.b.store.connect() as db:item=self.b.store.get(db,'memory_record','experience:EXP-A')
        sm.change(self.b,{'key':item['key'],'revision':item['revision'],'enabled':False,'confirmed':True});sm.sync(self.a);sm.sync(self.a)
        with self.a.store.connect() as db:self.assertEqual(sm.experiences(self.a,db),[])
    def test_local_new_rejection_and_replacement_lesson_propagates(self):
        self.seed_learning();self.pair(self.a,0);self.pair(self.b,1)
        with self.a.store.connect() as db:
            old=self.a.store.get(db,'reply_learning','TIP-A');old.update(status='REJECTED',approved=False,revision=2);self.a.store.put(db,'reply_learning',old)
            self.a.store.put(db,'feedback',{'id':'EXP-B','case_id':'CASE-PRIVATE','verdict':'CORRECTED','public_question':'How to report a Wi-Fi issue?','text':'Describe affected devices and when the disconnections happen.'})
        sm.sync(self.a);sm.sync(self.b)
        ex={x['id']:x for x in self.shared(self.b,'experience')};self.assertFalse(ex['EXP-A']['enabled']);self.assertTrue(ex['EXP-B']['enabled']);self.assertFalse(self.shared(self.b,'tip')[0]['enabled'])
    def test_simultaneous_changes_preserve_conflict_and_never_silently_overwrite(self):
        self.sop(self.a);self.pair(self.a,0);self.pair(self.b,1)
        self.edit(self.a,'Local proposal from computer A.');self.edit(self.b,'Local proposal from computer B.')
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(sm.sync,[self.a,self.b]))
        sm.sync(self.a);sm.sync(self.b)
        self.assertEqual(self.shared(self.a,'sop'),self.shared(self.b,'sop'))
        conflicts=[(s,x) for s in (self.a,self.b) for x in self.rows(s,'memory_conflict') if x['status']=='OPEN'];self.assertEqual(len(conflicts),1)
        owner,item=conflicts[0];self.assertNotEqual(item['local_value']['text'],item['remote_value']['text'])
        with self.assertRaises(ValueError):sm.resolve(owner,{'id':item['id'],'choice':'local'})
        sm.resolve(owner,{'id':item['id'],'choice':'remote'});sm.sync(self.a);sm.sync(self.b);self.assertEqual(self.shared(self.a,'sop'),self.shared(self.b,'sop'))
    def test_offline_old_edit_cannot_restore_revoked_sop(self):
        self.sop(self.a);self.pair(self.a,0);self.pair(self.b,1)
        self.edit(self.a,active=False);sm.sync(self.a)
        self.edit(self.b,'An old offline proposal must not silently replace a revocation.');sm.sync(self.b);sm.sync(self.a)
        self.assertFalse(self.shared(self.b,'sop')[0]['active']);self.assertTrue(any(x['status']=='OPEN' for x in self.rows(self.b,'memory_conflict')))
    def test_offline_connection_pauses_common_rules_and_still_acknowledges_customer(self):
        self.sop(self.a);self.pair(self.a,0);self.pair(self.b,1)
        with patch('belive.shared_memory.request',side_effect=ConnectionError('offline')):
            self.assertEqual(sm.sync(self.b)['status'],'OFFLINE');self.assertEqual(self.shared(self.b,'sop'),[])
            r=self.cmd(self.b,'wa_simulate',customer='qa',text='What rule applies to my complaint?')
            with patch('belive.whatsapp_ai.reply') as reply:wa.process_thread(self.b,r['thread_id']);reply.assert_not_called()
        self.assertEqual(self.rows(self.b,'wa_outgoing')[0]['status'],'SIMULATED');self.assertEqual(len(self.rows(self.b,'wa_staff')),1)
    def test_wrong_workspace_and_unauthorised_clients_cannot_read_or_publish(self):
        self.sop(self.a)
        with self.assertRaises(ValueError):sm.configure(self.a,{'url':self.url,'token':self.tokens[0],'workspace_id':'MEM-'+'f'*24})
        self.assertEqual(self.hub.snapshot()['records'],[])
        for headers in ({},{'Authorization':'Bearer wrong'},{'Authorization':'Bearer '+self.tokens[0],'Origin':'https://evil.example'},{'Authorization':'Bearer '+self.tokens[0],'Host':'public.example'}):
            with self.subTest(headers=list(headers)):
                with self.assertRaises(HTTPError) as cm:urlopen(Request(self.url+'/v1/knowledge',headers=headers))
                self.assertEqual(cm.exception.code,401)
        with self.assertRaises(ValueError):sm.validate_url('http://192.168.1.1:8878')
    def test_hub_rejects_account_fields_and_never_exposes_credentials(self):
        self.pair(self.a,0)
        p={'kind':'sop','expected_revision':0,'value':{'id':'X','title':'Test','text':'A harmless rule.','password_hash':'Do not share this'}}
        with self.assertRaises(ValueError):sm.request({'url':self.url,'token':self.tokens[0],'workspace_id':self.wid},p)
        with self.a.store.connect() as db:text=json.dumps(sm.status(self.a,db))
        self.assertNotIn(self.tokens[0],text);self.assertNotIn(self.tokens[1],text)
    def test_private_document_bytes_and_clauses_sync_with_checksum(self):
        from belive.company_sop import import_reviewed,document_path
        source=self.root/'template.pdf';source.write_bytes(b'%PDF-1.7\nFictional source only')
        section={'key':'rule','title':'A fictional company rule','guidance':'A general, approved support rule for a fictional test.','policy':'GENERAL_GUIDANCE','topics':['test'],'clauses':'Fixture 1','quotes':[{'page':1,'text':'Fictional source only'}]}
        import_reviewed(self.a,source,['Fictional source only'],[section],[],confirmed=True);self.pair(self.a,0);self.pair(self.b,1)
        doc=self.shared(self.b,'document')[0];self.assertEqual(document_path(self.b,doc).read_bytes(),source.read_bytes());self.assertEqual(len(self.shared(self.b,'sop')),1)
    def test_hermes_on_peer_receives_the_common_experience_and_tip(self):
        self.seed_learning();self.pair(self.a,0);self.pair(self.b,1);r=self.cmd(self.b,'wa_simulate',customer='qa',text='My Wi-Fi disconnects, what can I check?')
        with patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment) as assessment, \
                patch('belive.whatsapp_ai.reply',return_value=plan()) as reply, \
                patch('belive.whatsapp_ai.review',return_value=True), \
                patch('belive.hosted_ai.generate',side_effect=AssertionError('Unexpected provider call')) as provider:
            wa.process_thread(self.b,r['thread_id'])
        assessment.assert_called_once()
        reply.assert_called_once()
        provider.assert_not_called()
        ctx=reply.call_args.args[1]
        self.assertEqual(ctx['approved_experiences'][0]['id'],'SHARED-EXP-A')
        self.assertEqual(ctx['reviewed_writing_tips'][0]['id'],'SHARED-TIP-A')
        self.assertEqual(self.rows(self.b,'wa_staff'),[])
        self.assertEqual(self.rows(self.b,'wa_outgoing')[0]['status'],'SIMULATED')

if __name__=='__main__':unittest.main()
