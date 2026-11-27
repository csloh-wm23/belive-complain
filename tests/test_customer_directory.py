"""Private records stay empty by default; staff select versioned facts explicitly."""
import secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive import customer_directory as directory,whatsapp as wa
from test_backend import FakeAI
import test_whatsapp as fixtures

class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'qa.db',FakeAI())
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,action,**p):return self.s.command(action,p,secrets.token_hex(16))
    def save(self,**extra):return self.cmd('customer_profile_save',customer_id='fictional-qa',name='Fictional QA Person',phone='',tenancy_id='QA-lease',property_id='QA-house',property_name='QA Test House',unit='Room-Q',source='Isolated test only',confirmed=True,**extra)
    def rows(self,k):
        with self.s.store.connect() as db:return self.s.store.all(db,k)
    def link(self,profile,**extra):
        t=self.rows('wa_thread')[0]
        return self.cmd('customer_profile_link',thread_id=t['id'],revision=t['revision'],record_id=profile['id'],version=profile['version'],confirmed=True,**extra)
    def facts(self):
        with self.s.store.connect() as db:return directory.facts(self.s,db,self.rows('wa_thread')[0])
    def test_empty_initial_installation_and_phone_does_not_auto_match(self):
        with self.s.store.connect() as db:
            self.assertEqual(directory.snapshot(self.s,db)['records'],[])
            self.assertFalse(directory.snapshot(self.s,db)['automatic_matching'])
        self.save();self.cmd('wa_simulate',customer='fictional-qa',text='Where should I report an issue?')
        self.assertIsNone(self.facts())
    def test_selected_minimum_facts_and_update_require_new_selection(self):
        r=self.save();self.cmd('wa_simulate',customer='fictional-qa',text='The room door handle is loose.')
        self.link(r);facts=self.facts()
        self.assertEqual(facts['property_name'],'QA Test House');self.assertFalse(facts['identity_verified'])
        self.assertNotIn('name',facts);self.assertNotIn('phone',facts);self.assertNotIn('source',facts)
        with self.s.store.connect() as db:p=directory.records(self.s,db)[0]
        self.cmd('customer_profile_save',**{k:v for k,v in p.items() if k not in {'id','checked_at','checked_by'}},confirmed=True)
        self.assertIsNone(self.facts())
        with self.assertRaises(ValueError):self.link(r)
    def test_inactive_and_other_case_cannot_supply_facts(self):
        r=self.save();self.cmd('wa_simulate',customer='fictional-qa',text='A physical fault needs help.');self.link(r)
        with self.s.store.connect() as db:
            t=self.rows('wa_thread')[0];t['case_id']='different-case'
            self.assertIsNone(directory.facts(self.s,db,t))
            p=directory.records(self.s,db)[0]
        p.update(active=False)
        self.cmd('customer_profile_save',**{k:v for k,v in p.items() if k not in {'id','checked_at','checked_by'}},confirmed=True)
        self.assertIsNone(self.facts())
    def test_multiple_tenancies_do_not_overwrite_one_customer(self):
        a=self.save()
        b=self.cmd('customer_profile_save',customer_id='fictional-qa',name='Fictional QA Person',tenancy_id='QA-other',source='Isolated test only',confirmed=True)
        self.assertNotEqual(a['id'],b['id']);self.assertEqual(len(self.rows('customer_profile')),2)
        with self.assertRaises(ValueError):self.save()
    def test_stale_record_cannot_send_queued_location_reply(self):
        r=self.save();t=self.cmd('wa_simulate',customer='fictional-qa',text='The door handle is loose.')
        self.link(r)
        with patch('belive.whatsapp_triage.assess',side_effect=fixtures.fixture_assessment),patch('belive.whatsapp_ai.reply',return_value={**fixtures.plan(),'use_customer_record':True}),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.deliver'):
            wa.process_thread(self.s,t['thread_id'])
        out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['customer_record_facts']['id'],r['id'])
        with self.s.store.connect() as db:p=directory.records(self.s,db)[0]
        p.update(active=False)
        self.cmd('customer_profile_save',**{k:v for k,v in p.items() if k not in {'id','checked_at','checked_by'}},confirmed=True)
        self.assertEqual(wa.deliver(self.s,out['id'])['status'],'SUPERSEDED')
        self.assertTrue(any(t['status']=='PENDING' for t in self.rows('wa_turn')))

if __name__=='__main__':unittest.main()
