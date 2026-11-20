import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from belive.service import Service
from belive.google_replies import publish,readiness
from test_backend import FakeAI


class GoogleReplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'test.db',FakeAI())
        self.env=patch.dict(os.environ,{'BELIVE_GOOGLE_TOKEN':'test-token','BELIVE_GOOGLE_REPLY_ENABLED':'true'});self.env.start()
        self.cmd('source',dict(platform='GOOGLE',resource='accounts/123/locations/456',authorised=True))
        self.case=self.cmd('intake',dict(title='Fictional washer fault',description='The shared washing machine stopped working.',platform='GOOGLE',source_id='accounts/123/locations/456/review-789'))
        self.name='accounts/123/locations/456/reviews/review-789'
        self.reply='Sorry about the washer issue. Please contact BeLive privately with the affected location.'
        self.review=dict(name=self.name,comment=self.case['description'])
        self.receipt=dict(comment=self.reply,updateTime='2026-11-19T12:00:00Z')
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def cmd(self,name,p):return self.s.command(name,p,secrets.token_hex(16))
    def current(self):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',self.case['id'])
    def post(self,key=None,**extra):
        return publish(self.s,{'id':self.case['id'],'revision':self.current()['revision'],'text':self.reply,'confirmed':True,**extra},'qa-staff',key or secrets.token_hex(16))

    def test_reviewed_post_uses_exact_official_put_and_deduplicates(self):
        key=secrets.token_hex(16)
        with patch('belive.google_replies.request_json',side_effect=[self.review,self.receipt]) as request:
            result=self.post(key)
            self.assertEqual(result['status'],'POSTED')
            self.assertEqual(request.call_args.kwargs,dict(payload={'comment':self.reply},method='PUT'))
            self.assertEqual(request.call_args.args[0],'https://mybusiness.googleapis.com/v4/'+self.name+'/reply')
            self.assertEqual(self.post(key),result)
            self.assertEqual(self.post(),result)
            self.assertEqual(request.call_count,2)
            with self.assertRaisesRegex(ValueError,'Idempotency mismatch'):self.post(key,text='A different public reply.')
        self.assertEqual(self.current()['status'],self.case['status'])

    def test_no_credentials_or_confirmation_never_calls_google(self):
        with patch('belive.google_replies.request_json') as request:
            with self.assertRaisesRegex(ValueError,'confirm public posting'):self.post(confirmed=False)
            with patch.dict(os.environ,{'BELIVE_GOOGLE_REPLY_ENABLED':'false'}):
                with self.assertRaisesRegex(ValueError,'authorization'):self.post()
            with self.assertRaisesRegex(ValueError,'Case changed'):self.post(revision=0)
            request.assert_not_called()

    def test_public_link_is_not_a_google_api_review_resource(self):
        with self.s.store.connect() as db:
            case=self.current();case['source_id']='browser-review-fixture'
            self.s.store.put(db,'case',case)
            self.assertFalse(readiness(self.s.store,db,case)['ready'])
        with patch('belive.google_replies.request_json') as request:
            with self.assertRaisesRegex(ValueError,'public Maps link'):self.post()
            request.assert_not_called()

    def test_existing_reply_requires_explicit_replace_permission(self):
        existing={**self.review,'reviewReply':{'comment':'Existing company response.'}}
        with patch('belive.google_replies.request_json',return_value=existing) as request:
            result=self.post();self.assertEqual(result['status'],'FAILED');self.assertEqual(request.call_count,1)
        with patch('belive.google_replies.request_json',side_effect=[existing,self.receipt]):
            self.assertEqual(self.post(replace_existing=True)['status'],'POSTED')

    def test_changed_review_does_not_publish(self):
        with patch('belive.google_replies.request_json',return_value={**self.review,'comment':'A new complaint about a different problem.'}) as request:
            result=self.post();self.assertEqual(result['status'],'FAILED')
            self.assertIn('review changed',result['detail']);self.assertEqual(request.call_count,1)

    def test_timeout_is_unconfirmed_and_never_automatically_retried(self):
        with patch('belive.google_replies.request_json',side_effect=[self.review,TimeoutError('test')]) as request:
            result=self.post();self.assertEqual(result['status'],'UNKNOWN')
            with self.assertRaisesRegex(ValueError,'unconfirmed'):self.post()
            self.assertEqual(request.call_count,2)

    def test_google_permission_failure_is_not_reported_as_success(self):
        error=HTTPError('https://mybusiness.googleapis.com',403,'Forbidden',{},None)
        with patch('belive.google_replies.request_json',side_effect=[self.review,error]):
            result=self.post();self.assertEqual(result['status'],'FAILED');self.assertIn('403',result['detail'])
