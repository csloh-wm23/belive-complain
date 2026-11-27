"""One exact own-account demo input; normal company replies remain excluded."""
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from belive import connectors, public_replies
from belive.service import Service


def expiry(minutes=30):
    return (datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat()


def reply(reply_id='401', text='BELIVE TEST — Fictional complaint: the shared washing machine is not working.', **extra):
    return {'id':reply_id,'text':text,'is_reply_owned_by_me':True,
            'timestamp':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
            'permalink':'https://www.threads.com/@fixture/post/test'+reply_id,**extra}


class ThreadsOwnReplyTestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service=Service(Path(self.tmp.name)/'test.db',Mock())
        self.payload={'platform':'THREADS','resource':'123/threads','authorised':True,
                      'own_reply_test_id':'401','own_reply_test_expires_at':expiry()}
        self.source=self.service.command('source',self.payload,'fixture-test-source')

    def current_source(self):
        with self.service.store.connect() as db:
            return self.service.store.get(db,'source',self.source['id'])

    def scan(self, items, after_read=None):
        recent=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        def read(url,token='',**kwargs):
            self.assertNotIn('payload',kwargs)
            self.assertNotEqual(kwargs.get('method'),'POST')
            if '/123/threads?' in url:return {'data':[{'id':'400','timestamp':recent}]}
            if after_read:after_read()
            return {'data':items}
        with patch.object(connectors,'get_value',return_value='fixture-only-token'), \
                patch.object(connectors,'request_json',side_effect=read):
            return connectors.scan(self.service,self.source['id'])

    def test_validation_requires_threads_exact_numeric_id_and_short_aware_future_expiry(self):
        self.assertEqual(connectors.validate_source(self.payload)['own_reply_test_id'],'401')
        invalid=[{'own_reply_test_id':'*'}, {'own_reply_test_id':401}, {'own_reply_test_id':{}},
                 {'own_reply_test_id':''},{'own_reply_test_expires_at':''},
                 {'own_reply_test_expires_at':expiry(-1)}, {'own_reply_test_expires_at':expiry(61)},
                 {'own_reply_test_expires_at':'2026-11-28T12:00:00'},
                 {'own_reply_test_expires_at':{}}, {'platform':'FACEBOOK','resource':'123/feed'},
                 {'platform':'GOOGLE','resource':'accounts/123/locations/456'}]
        for values in invalid:
            with self.subTest(values=values),self.assertRaises(ValueError):
                connectors.validate_source({**self.payload,**values})
        cleared=connectors.validate_source({**self.payload,'own_reply_test_id':'','own_reply_test_expires_at':''})
        self.assertEqual(cleared['own_reply_test_id'],'')

    def test_exact_labelled_own_reply_imports_once_with_test_metadata_and_source_link(self):
        ids=self.scan([reply(),reply('402'),reply('403',is_reply_owned_by_me=False)])
        self.assertEqual(len(ids),2)
        with self.service.store.connect() as db:
            cases=self.service.store.all(db,'case')
            case=next(c for c in cases if c['source_id']=='401')
            ordinary=next(c for c in cases if c['source_id']=='403')
            self.assertEqual(case['public_source_kind'],'THREADS_OWN_REPLY_TEST')
            self.assertIs(case['test_only'],True)
            self.assertEqual(case['source_author_type'],'CONNECTED_ACCOUNT')
            self.assertTrue(case['title'].startswith('TEST ONLY'))
            self.assertEqual(case['public_url'],reply()['permalink'])
            self.assertEqual(case['parent_source_id'],'400')
            self.assertFalse(ordinary.get('test_only'))
            self.assertTrue(self.current_source()['own_reply_test_used_at'])
            self.assertEqual(len(self.service.store.all(db,'outbox')),0)
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],2)
        self.assertEqual(self.scan([reply(),reply('402')]),[])
        self.service.ai.analyse.assert_not_called()

    def test_marker_exact_id_and_expiry_are_all_required_even_if_source_was_tampered(self):
        current=datetime.now(timezone.utc)
        window=(current-timedelta(days=30),current)
        for source,item in [
            (self.source,reply(text='TEST: A fictional washing machine complaint without the exact marker.')),
            (self.source,reply('402')),
            ({**self.source,'own_reply_test_expires_at':expiry(-1)},reply()),
            ({**self.source,'own_reply_test_expires_at':expiry(65)},reply()),
            ({**self.source,'own_reply_test_used_at':current.isoformat()},reply()),
            ({k:v for k,v in self.source.items() if not k.startswith('own_reply_test')},reply()),
            (self.source,reply(timestamp=(current-timedelta(days=31)).isoformat())),
        ]:
            with self.subTest(source=source,item=item):
                self.assertIsNone(connectors._threads_reply(item,source,window,'400'))
        self.assertIsNotNone(connectors._threads_reply(reply(text='belive test: Fictional appliance complaint.'),self.source,window,'400'))

    def test_selected_test_reply_fails_closed_when_api_ownership_is_missing_or_false(self):
        for flag in (None,False,0,1,'true'):
            item=reply(is_reply_owned_by_me=flag)
            if flag is None:item.pop('is_reply_owned_by_me')
            with self.subTest(flag=flag):self.assertEqual(self.scan([item]),[])
        with self.service.store.connect() as db:self.assertFalse(self.service.store.all(db,'case'))
        self.assertFalse(self.current_source().get('own_reply_test_used_at'))

    def test_revocation_expiry_pause_or_resource_change_during_read_blocks_test_intake(self):
        for field,value in [('own_reply_test_id',''),('own_reply_test_expires_at',expiry(-1)),
                            ('enabled',False),('resource','456/threads'),('authorised',False)]:
            self.service.command('source',{**self.payload,'id':self.source['id'],'enabled':True},'fixture-reset-'+field)
            def change(field=field,value=value):
                with self.service.lock,self.service.store.connect() as db:
                    current=self.service.store.get(db,'source',self.source['id'])
                    current[field]=value;self.service.store.put(db,'source',current)
            with self.subTest(field=field):
                self.assertEqual(self.scan([reply()],after_read=change),[])
                self.assertFalse(self.current_source().get('own_reply_test_used_at'))
        with self.service.store.connect() as db:self.assertFalse(self.service.store.all(db,'case'))

    def test_concurrent_reads_of_different_edits_claim_only_one_test_input(self):
        barrier=threading.Barrier(2)
        results=[];errors=[]
        def read(source):
            item=reply(text='BELIVE TEST — Fictional washer complaint from '+threading.current_thread().name)
            window=connectors._collection_window(source)
            row=connectors._threads_reply(item,source,window,'400')
            barrier.wait(timeout=5)
            return [row]
        def run():
            try:results.append(connectors.scan(self.service,self.source['id']))
            except Exception as exc:errors.append(str(exc))
        with patch.object(connectors,'read_source',side_effect=read):
            threads=[threading.Thread(target=run,name='fixture-'+str(i)) for i in range(2)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors,[])
        self.assertEqual(sum(len(x) for x in results),1)
        with self.service.store.connect() as db:
            self.assertEqual(len(self.service.store.all(db,'case')),1)
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE action='THREADS_TEST_EXCEPTION_CLAIMED'").fetchone()[0],1)

    def test_failed_reserved_intake_consumes_exception_and_records_failure_without_retry(self):
        original=self.service.command
        def fail(name,*args,**kwargs):
            if name=='intake':raise ValueError('fixture intake failure')
            return original(name,*args,**kwargs)
        with patch.object(self.service,'command',side_effect=fail):self.assertEqual(self.scan([reply()]),[])
        self.assertTrue(self.current_source().get('own_reply_test_used_at'))
        with self.service.store.connect() as db:
            self.assertFalse(self.service.store.all(db,'case'))
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE action='THREADS_TEST_INTAKE_FAILED'").fetchone()[0],1)
        self.assertEqual(self.scan([reply()]),[])

    def test_later_metadata_failure_leaves_initial_case_durably_test_only_and_publish_blocked(self):
        initial_writes=[];original=self.service.store.put
        def record(db,kind,value):
            if kind=='case':initial_writes.append(dict(value))
            return original(db,kind,value)
        with patch.object(self.service.store,'put',side_effect=record), \
                patch.object(connectors,'_source_metadata',side_effect=RuntimeError('fixture metadata failure')):
            self.assertEqual(self.scan([reply()]),[])
        self.assertTrue(initial_writes)
        self.assertIs(initial_writes[0]['test_only'],True)
        self.assertEqual(initial_writes[0]['public_source_kind'],'THREADS_OWN_REPLY_TEST')
        with self.service.store.connect() as db:
            cases=self.service.store.all(db,'case')
            self.assertEqual(len(cases),1)
            case=cases[0]
            self.assertIs(case['test_only'],True)
            self.assertEqual(case['source_author_type'],'CONNECTED_ACCOUNT')
            self.assertEqual(len(case['source_versions']),1)
        with patch.object(public_replies,'request_json') as transport:
            ready=public_replies.eligibility(self.service,case)
            self.assertFalse(ready['ready'])
            self.assertIn('local draft only',ready['reason'])
        transport.assert_not_called()
        self.assertTrue(self.current_source()['own_reply_test_used_at'])

    def test_internal_intake_marker_requires_the_durable_exact_claim_and_text(self):
        payload={'platform':'THREADS','source_id':'401','title':'TEST ONLY — Public tenant feedback',
                 'description':reply()['text'],'_own_reply_test_source':self.source['id']}
        with self.assertRaisesRegex(ValueError,'current exact reserved'):
            self.service.command('intake',payload,'fixture-unclaimed-marker')
        self.scan([reply()])
        for change in ({'source_id':'402'},{'description':'BELIVE TEST: A different fictional appliance complaint.'},
                       {'platform':'FACEBOOK'},{'title':'Ordinary customer feedback'}):
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'current exact reserved'):
                self.service.command('intake',{**payload,**change},'fixture-bad-claim-'+str(len(str(change))))

    def test_successful_outbound_receipts_cannot_be_reimported_through_test_exception(self):
        earlier=self.service.command('intake',{'platform':'THREADS','source_id':'700',
            'title':'Earlier fixture','description':'TEST: An earlier fictional support complaint.'},'fixture-earlier')
        for from_attempt in (False,True):
            with self.subTest(from_attempt=from_attempt),self.service.store.connect() as db:
                earlier['public_reply']={} if from_attempt else {'platform':'THREADS','status':'POSTED','receipt_id':'401'}
                self.service.store.put(db,'case',earlier)
                if from_attempt:self.service.store.put(db,'public_reply_attempt',{'id':'fixture-posted',
                    'result':{'platform':'THREADS','status':'POSTED','receipt_id':'401'}})
            self.assertEqual(self.scan([reply()]),[])
            self.assertFalse(self.current_source().get('own_reply_test_used_at'))
        with self.service.store.connect() as db:
            self.assertEqual(len(self.service.store.all(db,'case')),1)

    def test_normal_source_save_preserves_exception_and_clear_keeps_source_identity(self):
        self.scan([reply()])
        saved=self.service.command('source',{'platform':'THREADS','resource':'123/threads','authorised':True,
            'lookback_days':7},'fixture-window-update')
        self.assertEqual(saved['id'],self.source['id'])
        self.assertEqual(saved['own_reply_test_id'],'401')
        self.assertTrue(saved['own_reply_test_used_at'])
        cleared=self.service.command('source',{**self.payload,'own_reply_test_id':'','own_reply_test_expires_at':''},'fixture-clear-test')
        self.assertEqual(cleared['id'],self.source['id'])
        self.assertFalse(cleared.get('own_reply_test_used_at'))
        self.assertEqual(cleared['own_reply_test_id'],'')
        self.assertEqual(self.scan([reply()]),[])
        with self.service.store.connect() as db:self.assertEqual(len(self.service.store.all(db,'source')),1)

    def test_selected_post_source_obeys_the_same_narrow_exception(self):
        source=connectors.validate_source({**self.payload,'resource':'400/replies'})
        with patch.object(connectors,'get_value',return_value='fixture-only-token'), \
                patch.object(connectors,'request_json',return_value={'data':[reply(),reply('402')]}):
            rows=connectors.read_source(source)
        self.assertEqual([r['id'] for r in rows],['401'])
        self.assertIs(rows[0]['test_only'],True)

    def test_test_cases_cannot_send_to_threads_or_become_approved_customer_lessons(self):
        case_id=self.scan([reply()])[0]
        with self.service.store.connect() as db:case=self.service.store.get(db,'case',case_id)
        with patch.object(public_replies,'request_json') as transport:
            ready=public_replies.eligibility(self.service,case)
            self.assertFalse(ready['ready'])
            self.assertIn('local draft only',ready['reason'])
            with self.assertRaisesRegex(ValueError,'local draft only'):
                public_replies.publish(self.service,{'id':case_id,'revision':case['revision'],
                    'text':'A fictional reply draft.','confirmed':True},'fixture-staff','fixture-blocked-send')
        transport.assert_not_called()
        with self.service.store.connect() as db:
            case['status']='CLOSED';self.service.store.put(db,'case',case)
        with self.assertRaisesRegex(ValueError,'cannot become approved customer lessons'):
            self.service.command('feedback',{'id':case_id,'verdict':'APPROVED'},'fixture-no-lesson')
        with self.service.store.connect() as db:
            self.assertFalse(self.service.store.all(db,'public_reply_attempt'))
            self.assertFalse(self.service.store.all(db,'feedback'))

    def test_read_failure_does_not_consume_exception_or_mask_connector_failure(self):
        with patch.object(connectors,'read_source',side_effect=RuntimeError('fixture failure')):
            self.assertEqual(connectors.scan(self.service,self.source['id']),[])
        source=self.current_source()
        self.assertEqual(source['status'],'FAILED')
        self.assertFalse(source.get('own_reply_test_used_at'))


if __name__=='__main__':unittest.main()
