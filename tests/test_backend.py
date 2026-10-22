"""Isolated integration tests: no real tenant, model or external-service calls."""
import json
import os
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive.ai import SupportAI,CATEGORIES
from belive.settings import Settings
from belive.connectors import deliver,scan,validate_source

class FakeAI:
    def __init__(self,fail=False):self.fail=fail;self.calls=[]
    def readiness(self):return True
    def analyse(self,context,examples):
        self.calls.append((context,examples))
        if self.fail:raise RuntimeError('provider timeout')
        return dict(relevance='SUPPORT',category='WIFI',severity='LOW',summary='Tenant reports a Wi-Fi issue.',
                    uncertainty=False,evidence=context['case']['description'],plan='Ask whether other devices are affected.',
                    response='Could you confirm whether other devices have the same issue?',requires_human=False,record_ids=[])

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ai=FakeAI();self.s=Service(Path(self.tmp.name)/'test.db',self.ai)
        self.command('condo',dict(id='C-A',name='Fictional test condo',rules='Test fixture guidance: report shared Wi-Fi outages to the support team.',confirmed=True))
        for tid in ['T-A','T-B']:
            self.command('tenant',dict(id=tid,condo_id='C-A',unit_ref='U-A',verified_by='Test staff',evidence='Fictional tenancy record checked.',confirmed=True))
    def tearDown(self):self.tmp.cleanup()
    def command(self,name,p,key=None):return self.s.command(name,p,key or secrets.token_hex(16))
    def intake(self,**extra):return self.command('intake',dict(title='Wi-Fi enquiry',description='My room Wi-Fi connection drops each evening.',tenant_id='T-A',**extra))
    def case(self,c):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',c['id'])
    def action(self,c,action,**extra):
        current=self.case(c);return self.command('case_action',dict(id=c['id'],revision=current['revision'],action=action,**extra))
    def close(self,c):
        self.action(c,'acknowledge',owner='Test support')
        self.action(c,'draft',note='Please clarify which step needs more explanation.')
        self.action(c,'followup',note='Test support has recorded the next action.')
        self.action(c,'verify',note='Fictional customer feedback was checked by staff.',confirmed=True)
        return self.action(c,'close')
    def test_immutable_sources_idempotency_and_redaction(self):
        p=dict(title='A cleaning request',description='Please contact sample@example.com or +60123456789 about cleaning.',platform='MANUAL_PUBLIC',source_id='post-1')
        key=secrets.token_hex(16);a=self.command('intake',p,key);b=self.command('intake',p,key);self.assertEqual(a['id'],b['id'])
        with self.assertRaises(ValueError):self.command('intake',{**p,'title':'Different title'},key)
        c=self.command('intake',p);self.assertEqual(a['id'],c['id'])
        self.assertNotIn('sample@example.com',a['description'])
        with self.s.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sources').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE sources SET body='changed'")
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM events')
    def test_numeric_source_ids_and_unverified_people_remain_distinct(self):
        a=self.command('intake',dict(title='Public Wi-Fi feedback',description='The Wi-Fi is dropping every evening.',platform='THREADS',source_id='123456789012345'))
        b=self.command('intake',dict(title='Public Wi-Fi feedback',description='The Wi-Fi is dropping every evening.',platform='THREADS',source_id='987654321098765'))
        self.assertEqual(a['source_id'],'123456789012345');self.assertNotEqual(a['id'],b['id'])
    def test_response_dedup_and_guidance_revoked_during_analysis(self):
        old=self.intake();self.close(old);self.command('feedback',dict(id=old['id'],verdict='APPROVED'))
        c=self.command('intake',dict(title='New Wi-Fi request',description='My bedroom connection stopped working today.',tenant_id='T-A'))
        original=self.ai.analyse
        def revoke(context,examples):
            self.command('feedback',dict(id=old['id'],verdict='REJECTED'))
            return original(context,examples)
        self.ai.analyse=revoke
        self.assertEqual(self.s.analyse(c['id'])['status'],'STALE');self.assertFalse(self.case(c)['draft'])
        self.action(c,'draft',note='Could you clarify when this started?')
        self.action(c,'queue_response',confirmed=True);self.action(c,'queue_response',confirmed=True)
        self.assertEqual(sum(m['kind']=='TENANT_RESPONSE' for m in self.s.snapshot()['outbox']),1)
    def test_risk_bypasses_ai_and_escalates_once_per_level(self):
        c=self.command('intake',dict(title='Urgent safety issue',description='There is smoke and sparks from the room socket.',tenant_id='T-A'))
        self.assertEqual(c['severity'],'CRITICAL');self.assertEqual(c['status'],'HUMAN_REVIEW')
        with self.assertRaises(ValueError):self.s.analyse(c['id'])
        for level in [1,2]:
            with self.s.store.connect() as db:
                c=self.s.store.get(db,'case',c['id']);c['ack_due']='2000-01-01T00:00:00+00:00';self.s.store.put(db,'case',c)
            self.s.tick();self.assertEqual(self.case(c)['escalation'],level)
        count=len(self.s.snapshot()['outbox']);self.s.tick();self.assertEqual(count,len(self.s.snapshot()['outbox']));self.assertEqual(self.ai.calls,[])
    def test_ai_uses_only_matching_tenant_records_and_fails_honestly(self):
        for tid in ['T-A','T-B']:self.command('record',dict(tenant_id=tid,text='Verified fixture facts for '+tid,source='Test record',confirmed=True))
        c=self.intake();self.s.analyse(c['id']);current=self.case(c)
        self.assertTrue(current['draft']);self.assertEqual(len(self.ai.calls[0][0]['verified_records']),1)
        self.assertEqual(self.ai.calls[0][0]['verified_records'][0]['tenant_id'],'T-A')
        self.ai.fail=True;self.s.analyse(c['id']);self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertIn('AI_FAILED',self.case(c)['review_reason'])
    def test_case_closure_workorder_and_learning_revocation(self):
        c=self.intake()
        with self.assertRaises(ValueError):self.action(c,'close')
        self.action(c,'acknowledge',owner='Test support')
        self.action(c,'draft',note='Ask which safe checks have already been tried.')
        self.action(c,'workorder',note='Inspect the reported Wi-Fi equipment issue.',department='Maintenance')
        self.action(c,'followup',note='Test investigation recorded; awaiting confirmation.')
        self.action(c,'verify',note='Fictional confirmation was verified by support.',confirmed=True)
        with self.assertRaises(ValueError):self.action(c,'close')
        w=self.s.snapshot()['workorders'][0];self.action(c,'complete_workorder',workorder_id=w['id'],note='Test inspection recorded as complete by assigned staff.')
        self.action(c,'close');self.command('feedback',dict(id=c['id'],verdict='APPROVED',share=True));self.assertEqual(len(self.s.snapshot()['examples']),1)
        self.command('feedback',dict(id=c['id'],verdict='REJECTED'));self.assertEqual(self.s.snapshot()['examples'],[])
        self.command('feedback',dict(id=c['id'],verdict='CORRECTED',text='Ask one clarification at a time.'))
        self.action(c,'reopen',note='Tenant reports the issue has returned.');self.assertEqual(self.s.snapshot()['examples'],[])
    def test_followup_reminders_do_not_close_case(self):
        c=self.intake();self.action(c,'acknowledge',owner='Staff');self.action(c,'followup',note='The case needs follow-up confirmation.')
        for _ in range(2):
            with self.s.store.connect() as db:
                cur=self.s.store.get(db,'case',c['id']);cur['followup_due']='2000-01-01T00:00:00+00:00';self.s.store.put(db,'case',cur)
            self.s.tick()
        self.assertEqual(self.case(c)['status'],'HUMAN_REVIEW')
        self.assertEqual(sum(m['kind']=='TENANT_FOLLOWUP' for m in self.s.snapshot()['outbox']),2)
    def test_removed_operations_are_rejected_even_with_cached_success(self):
        for name in ['move','move_complete','staff']:
            key=secrets.token_hex(16);payload={'tenant_id':'T-A'}
            from belive.store import digest
            fingerprint=digest(json.dumps([name,payload],sort_keys=True))
            with self.s.store.connect() as db:
                db.execute('INSERT INTO requests VALUES(?,?)',(key,json.dumps({'fingerprint':fingerprint,'result':{'id':'OLD-SUCCESS'}})))
            with self.assertRaisesRegex(ValueError,'only tenant enquiry and complaint'):
                self.command(name,payload,key)
        self.assertNotIn('MOVE_IN_OUT',CATEGORIES)
        with self.assertRaisesRegex(ValueError,'Only property support guidance'):
            self.command('condo',dict(id='C-B',name='Old scheduling form',rules='Legacy rule text.',days=[5,6],confirmed=True))
    def test_legacy_arrangements_are_preserved_but_inactive(self):
        legacy={'id':'MOVE-OLD','tenant_id':'T-A','status':'SCHEDULED'}
        message={'id':'MSG-OLD','entity':legacy['id'],'kind':'TENANT_MOVE_NOTICE','text':'Legacy arrangement notice.','target':'T-A','status':'APPROVED'}
        with self.s.store.connect() as db:
            self.s.store.put(db,'move',legacy);self.s.store.put(db,'outbox',message)
            condo=self.s.store.get(db,'condo','C-A');condo.update(days=[5,6],start='08:00',end='18:00',checklist=['Keys checked'])
            self.s.store.put(db,'condo',condo)
        snapshot=self.s.snapshot()
        self.assertNotIn('moves',snapshot);self.assertNotIn('staff',snapshot);self.assertEqual(snapshot['outbox'],[])
        self.assertTrue(snapshot['condos'][0]['needs_review']);self.assertEqual(snapshot['condos'][0]['rules'],'')
        with patch('belive.connectors.request_json') as send:
            with self.assertRaisesRegex(ValueError,'outside tenant complaint support'):deliver(self.s,message['id'])
            send.assert_not_called()
        with self.assertRaisesRegex(ValueError,'outside tenant complaint support'):self.command('approve_message',{'id':message['id']})
        token=self.command('portal_issue',{'tenant_id':'T-A'})['token'];self.assertNotIn('moves',self.s.portal(token))
        c=self.intake();self.s.analyse(c['id']);self.assertIsNone(self.ai.calls[-1][0]['condo_rules'])
        with self.s.store.connect() as db:
            self.assertEqual(self.s.store.get(db,'move',legacy['id']),legacy)
            self.assertEqual(self.s.store.get(db,'outbox',message['id'])['status'],'APPROVED')
    def test_removed_category_is_not_accepted_from_ai(self):
        ai=SupportAI(Settings(),Path(self.tmp.name)/'memory')
        context={'case':{'description':'Please arrange a move.'},'verified_records':[]}
        result=dict(relevance='SUPPORT',category='MOVE_IN_OUT',severity='LOW',summary='Request',uncertainty=False,evidence='arrange a move')
        with patch.object(ai,'generate',return_value=result):
            with self.assertRaisesRegex(ValueError,'AI_INVALID_VALUES'):ai.analyse(context,[])
    def test_portal_scope_and_key_not_in_cached_requests(self):
        c=self.intake();other=self.command('intake',dict(title='Other tenant request',description='The shared area needs a cleaning review.',tenant_id='T-B'))
        result=self.command('portal_issue',dict(tenant_id='T-A'));token=result['token']
        portal=self.s.portal(token);self.assertEqual([x['id'] for x in portal['cases']],[c['id']]);self.assertNotIn('draft',portal['cases'][0])
        with self.assertRaises(ValueError):self.s.portal_update(token,dict(id=other['id'],note='Not my case but trying to edit.'),secrets.token_hex(16))
        with self.s.store.connect() as db:self.assertNotIn(token,str([tuple(x) for x in db.execute('SELECT * FROM requests')]))
    def test_delivery_requires_approval_and_uncertain_attempt_is_not_retried(self):
        c=self.intake();self.action(c,'draft',note='Please clarify when the Wi-Fi issue occurs.');self.action(c,'queue_response',confirmed=True)
        m=self.s.snapshot()['outbox'][0]
        with self.assertRaises(ValueError):deliver(self.s,m['id'])
        self.command('approve_message',dict(id=m['id']))
        with patch.dict(os.environ,{'BELIVE_NOTIFICATION_URL':'https://gateway.example.test/notify','BELIVE_NOTIFICATION_SECRET':'test-secret'}),patch('belive.connectors.request_json',side_effect=TimeoutError) as send:
            self.assertEqual(deliver(self.s,m['id'])['status'],'UNKNOWN')
            with self.assertRaises(ValueError):deliver(self.s,m['id'])
            self.assertEqual(send.call_count,1)
    def test_source_allowlist_and_missing_configuration(self):
        with self.assertRaises(ValueError):validate_source(dict(platform='FACEBOOK',resource='https://example.com',authorised=True))
        source=self.command('source',dict(platform='GOOGLE',resource='accounts/1/locations/2',authorised=True,enabled=True))
        with patch.dict(os.environ,{'BELIVE_GOOGLE_TOKEN':''}):self.assertEqual(scan(self.s,source['id']),[])
        self.assertEqual(self.s.snapshot()['sources'][0]['error'],'CONNECTOR_NOT_CONFIGURED')
    def test_ai_schema_and_exact_evidence_validation(self):
        ai=SupportAI(Settings(),Path(self.tmp.name)/'memory')
        context={'case':{'description':'The Wi-Fi is unstable.'},'verified_records':[]}
        bad=dict(relevance='SUPPORT',category='WIFI',severity='LOW',summary='An issue',uncertainty=False,evidence='invented excerpt')
        with patch.object(ai,'generate',return_value=bad):
            with self.assertRaises(ValueError):ai.analyse(context,[])
        with patch.object(ai,'generate',return_value={**bad,'evidence':'The Wi-Fi','uncertainty':'false'}):
            with self.assertRaises(ValueError):ai.analyse(context,[])

if __name__=='__main__':unittest.main()
