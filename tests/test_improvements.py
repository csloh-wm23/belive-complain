"""End-to-end state checks for conversations, knowledge, priorities and recovery."""
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from belive.service import Service
from belive.ai import SupportAI
from belive.settings import Settings
from belive.backups import operation,checksum
from belive.workspace import selected_database
from belive.access import Access
from test_backend import FakeAI

class ImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.ai=FakeAI()
        self.s=Service(self.root/'active.db',self.ai,workspace_config=self.root/'workspace.json')
        self.cmd('condo',dict(id='C',name='Fixture property',rules='Verified fixture Wi-Fi support guidance.',confirmed=True))
        for tid in ['T-A','T-B']:self.cmd('tenant',dict(id=tid,condo_id='C',unit_ref='U',evidence='Fixture tenancy record checked.',verified_by='QA staff',confirmed=True))
        self.token=self.cmd('portal_issue',{'tenant_id':'T-A'})['token']
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,name,p):return self.s.command(name,p,secrets.token_hex(16))
    def case(self):return self.cmd('intake',dict(title='Fixture Wi-Fi case',description='The room Wi-Fi drops each evening.',tenant_id='T-A'))
    def current(self,c):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',c['id'])
    def action(self,c,action,**p):return self.cmd('case_action',dict(id=c['id'],revision=self.current(c)['revision'],action=action,**p))
    def test_only_published_messages_enter_tenant_conversation(self):
        c=self.case();self.action(c,'draft',note='PRIVATE unapproved response')
        self.action(c,'note',note='PRIVATE staff investigation note')
        self.assertNotIn('PRIVATE',str(self.s.portal(self.token)))
        with self.assertRaises(ValueError):self.action(c,'publish_response')
        self.action(c,'draft',note='Please tell support which devices are affected.')
        self.action(c,'publish_response',confirmed=True);self.action(c,'publish_response',confirmed=True)
        portal=self.s.portal(self.token);messages=portal['cases'][0]['conversation']
        self.assertEqual(sum(m['sender']=='SUPPORT' for m in messages),1)
        self.assertNotIn('PRIVATE',str(portal))
        key=secrets.token_hex(16);payload={'id':c['id'],'note':'Two devices have the same issue.'}
        self.s.portal_update(self.token,payload,key);self.s.portal_update(self.token,payload,key)
        self.assertEqual(sum(m['sender']=='TENANT' for m in self.s.portal(self.token)['cases'][0]['conversation']),1)
        other=self.cmd('intake',dict(title='Other tenant case',description='The kitchen needs cleaning attention.',tenant_id='T-B'))
        with self.assertRaises(ValueError):self.s.portal_feedback(self.token,{'id':other['id'],'resolved':False},secrets.token_hex(16))
    def test_tenant_feedback_never_auto_closes_and_unresolved_reopens(self):
        c=self.case();self.action(c,'acknowledge',owner='QA support')
        self.action(c,'followup',note='Staff action recorded, awaiting tenant feedback.')
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':True},secrets.token_hex(16))
        self.assertEqual(self.current(c)['status'],'FOLLOW_UP')
        self.action(c,'draft',note='Ask a single concise clarification at a time.')
        self.action(c,'verify',note='Staff verified the tenant confirmation against this case.',confirmed=True);self.action(c,'close')
        self.cmd('feedback',{'id':c['id'],'verdict':'APPROVED'});self.assertTrue(self.s.snapshot()['examples'])
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':False},secrets.token_hex(16))
        self.assertEqual(self.current(c)['status'],'HUMAN_REVIEW');self.assertEqual(self.s.snapshot()['examples'],[])
    def test_record_versions_deactivation_and_stale_ai_result(self):
        r=self.cmd('record',dict(tenant_id='T-A',text='Fixture verified context for Wi-Fi support.',source='Fixture policy',confirmed=True))
        c=self.case();self.s.analyse(c['id']);self.assertEqual(self.current(c)['analysis']['record_refs'][0]['version'],1)
        original=self.ai.analyse
        def modify(context,examples):
            self.cmd('record_update',dict(id=r['id'],version=1,action='CORRECT',text='Corrected verified fixture support guidance.',source='Fixture policy v2',reason='Source document was corrected by QA.',confirmed=True))
            return original(context,examples)
        self.ai.analyse=modify;self.assertEqual(self.s.analyse(c['id'])['status'],'STALE')
        self.ai.analyse=original;self.cmd('record_update',dict(id=r['id'],version=2,action='DEACTIVATE',reason='Guidance has been withdrawn by QA.'))
        self.s.analyse(c['id']);self.assertEqual(self.ai.calls[-1][0]['verified_records'],[])
        with self.s.store.connect() as db:
            self.assertEqual(len(self.s.store.history(db,'record',r['id'])),3)
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM record_history')
        with self.assertRaises(ValueError):self.cmd('record_update',dict(id=r['id'],version=1,action='DEACTIVATE',reason='Attempting a stale record change.'))
    def test_critical_and_overdue_priority_queue(self):
        c=self.case();self.action(c,'plan',note='Check verified Wi-Fi support context.',due_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        with self.s.store.connect() as db:
            old=self.s.store.get(db,'case',c['id']);old['action_due']='2000-01-01T00:00:00+00:00';self.s.store.put(db,'case',old)
        critical=self.cmd('intake',dict(title='Fixture safety report',description='Smoke is coming from the electrical socket.',tenant_id='T-A'))
        cases=self.s.snapshot()['cases'];self.assertEqual(cases[0]['id'],critical['id']);self.assertTrue(next(x for x in cases if x['id']==c['id'])['overdue'])
    def test_staff_assessment_and_safety_in_outcome_feedback(self):
        c=self.case();self.action(c,'assess',category='WIFI',severity='MEDIUM',note='Staff checked the reported service interruption.')
        self.assertEqual(self.current(c)['severity'],'MEDIUM')
        self.s.portal_feedback(self.token,{'id':c['id'],'resolved':True,'note':'There is still smoke and sparks from the socket.'},secrets.token_hex(16))
        self.assertEqual(self.current(c)['status'],'HUMAN_REVIEW');self.assertEqual(self.current(c)['severity'],'CRITICAL')
        with self.assertRaises(ValueError):self.action(c,'assess',category='WIFI',severity='LOW',note='Attempting to lower an active safety flag.')
    def test_evaluation_fixture_is_separate_and_multilingual(self):
        import json
        cases=json.loads((Path(__file__).resolve().parents[1]/'evals/tenant_support.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cases),24);self.assertEqual({x['language'] for x in cases},{'en','ms','zh'})
        self.assertTrue(all(x['fictional'] for x in cases))
    def test_backup_and_paused_recovery_preserve_active_database(self):
        c=self.case();self.action(c,'draft',note='A reviewed response for the test tenant.');self.action(c,'queue_response',confirmed=True)
        message=self.s.snapshot()['outbox'][0];self.cmd('approve_message',{'id':message['id']})
        self.cmd('source',dict(platform='GOOGLE',resource='accounts/1/locations/2',authorised=True))
        access=Access(self.s);access.create(dict(username='qa-admin',name='QA Admin',password='Isolated-test-password-123'),bootstrap=True)
        session,_=access.login(dict(username='qa-admin',password='Isolated-test-password-123'))
        key=secrets.token_hex(16);backup=operation(self.s,'backup',{},key)
        self.assertEqual(operation(self.s,'backup',{},key),backup);before=checksum(backup['path'])
        self.cmd('record',dict(tenant_id='T-A',text='A record added after the backup snapshot.',source='QA source',confirmed=True))
        with self.assertRaises(ValueError):operation(self.s,'restore',{'id':backup['id']},secrets.token_hex(16))
        restored=operation(self.s,'restore',{'id':backup['id'],'confirmed':True},secrets.token_hex(16))
        self.assertEqual(checksum(backup['path']),before);self.assertEqual(len(self.s.snapshot()['records']),1);self.assertIsNotNone(access.current(session))
        recovered=Service(selected_database(self.s.workspace_config),FakeAI())
        self.assertEqual(recovered.snapshot()['records'],[]);self.assertFalse(recovered.snapshot()['sources'][0]['enabled'])
        self.assertEqual(recovered.snapshot()['outbox'][0]['status'],'RECOVERY_HOLD')
        self.assertEqual(recovered.snapshot()['cases'][0]['status'],'HUMAN_REVIEW')
        self.assertIsNone(Access(recovered).current(session))
        with self.assertRaises(ValueError):recovered.portal(self.token)
    def test_recovery_cannot_revive_withdrawn_guidance(self):
        r=self.cmd('record',dict(tenant_id='T-A',text='Verified fixture guidance for support.',source='Fixture document',confirmed=True))
        c=self.case();self.action(c,'acknowledge',owner='QA support');self.action(c,'draft',note='Ask one clarification at a time.')
        self.action(c,'followup',note='QA fixture follow-up action recorded.');self.action(c,'verify',note='QA confirmed the fictional tenant feedback.',confirmed=True);self.action(c,'close')
        self.cmd('feedback',{'id':c['id'],'verdict':'APPROVED'})
        backup=operation(self.s,'backup',{},secrets.token_hex(16))
        self.cmd('feedback',{'id':c['id'],'verdict':'REJECTED'})
        operation(self.s,'restore',{'id':backup['id'],'confirmed':True},secrets.token_hex(16))
        recovered=Service(selected_database(self.s.workspace_config),FakeAI())
        snapshot=recovered.snapshot();self.assertEqual(snapshot['examples'],[])
        self.assertFalse(snapshot['records'][0]['active']);self.assertTrue(snapshot['condos'][0]['needs_review'])
    def test_backup_tampering_is_rejected(self):
        backup=operation(self.s,'backup',{},secrets.token_hex(16))
        with Path(backup['path']).open('ab') as handle:handle.write(b'tampered')
        with self.assertRaises(ValueError):operation(self.s,'restore',{'id':backup['id'],'confirmed':True},secrets.token_hex(16))
    def test_portal_revocation_preserves_conversation_and_blocks_access(self):
        c=self.case();self.action(c,'draft',note='Reviewed support response in the portal.')
        self.action(c,'publish_response',confirmed=True)
        self.cmd('portal_revoke',{'tenant_id':'T-A','confirmed':True})
        with self.assertRaises(ValueError):self.s.portal(self.token)
        replacement=self.cmd('portal_issue',{'tenant_id':'T-A'})['token']
        self.assertIn('Reviewed support response',str(self.s.portal(replacement)))
    def test_real_connection_status_does_not_claim_success_without_configuration(self):
        self.s.ai=SupportAI(Settings(),self.root/'memory')
        result=self.s.check_ai();self.assertEqual(result['status'],'FAILED');self.assertEqual(result['detail'],'AI_NOT_CONFIGURED')
        with patch('belive.ai.SupportAI.generate',return_value={'ok':1}):
            with self.assertRaises(ValueError):self.s.ai.check()
