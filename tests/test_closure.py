import secrets
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from test_backend import FakeAI


class InactivityClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Service(Path(self.tmp.name)/'test.db',FakeAI())
        self.receipt=self.s.website_submit({'title':'Fictional repair request','description':'Smoke and sparks from a socket.','rental_property':'QA Residence'},secrets.token_hex(16))
        self.cid=self.receipt['id'];self.code=self.receipt['complaint_code']

    def tearDown(self):self.tmp.cleanup()
    def current(self):
        with self.s.store.connect() as db:return self.s.store.get(db,'case',self.cid)
    def action(self,name,**fields):
        return self.s.command('case_action',dict(id=self.cid,revision=self.current()['revision'],action=name,**fields),secrets.token_hex(16))
    def start_wait(self):
        self.action('acknowledge',owner='QA staff')
        self.action('followup',note='Fictional repair completed and checked by staff.')
        return datetime.fromisoformat(self.current()['waiting_since'])
    def tick_at(self,moment):
        with patch('belive.service.now',return_value=moment.isoformat()):self.s.tick()

    def test_exact_seven_day_boundary_and_no_learning_or_duplicate_closure(self):
        since=self.start_wait()
        self.tick_at(since+timedelta(days=7,seconds=-1))
        self.assertEqual(self.current()['status'],'FOLLOW_UP')
        self.tick_at(since+timedelta(days=7))
        c=self.current();self.assertEqual(c['status'],'CLOSED')
        self.assertEqual(c['closure_reason'],'CUSTOMER_INACTIVE');self.assertFalse(c['verification'])
        self.assertEqual(self.s.snapshot()['reports']['verified_closures'],0)
        with self.assertRaisesRegex(ValueError,'no verified outcome'):
            self.s.command('feedback',dict(id=self.cid,verdict='CORRECTED',text='Reusable fictional support advice.'),secrets.token_hex(16))
        revision=c['revision'];self.tick_at(since+timedelta(days=8))
        self.assertEqual(self.current()['revision'],revision)
        portal=self.s.portal(self.code)['cases'][0]
        self.assertEqual(portal['closure_reason'],'CUSTOMER_INACTIVE')
        self.assertEqual(sum('did not receive your reply' in m['text'] for m in portal['conversation']),1)

    def test_customer_reply_stops_waiting_and_staff_followup_starts_new_period(self):
        since=self.start_wait()
        self.s.portal_update(self.code,dict(id=self.cid,note='The fault is still present beside the laundry door.'),secrets.token_hex(16))
        self.assertEqual(self.current()['status'],'IN_PROGRESS')
        self.tick_at(since+timedelta(days=20));self.assertEqual(self.current()['status'],'IN_PROGRESS')
        self.action('followup',note='Second inspection and repair completed by staff.')
        self.assertGreaterEqual(self.current()['waiting_since'],since.isoformat())

    def test_returning_message_reopens_same_case_with_original_code(self):
        since=self.start_wait();self.tick_at(since+timedelta(days=8))
        self.s.portal_update(self.code,dict(id=self.cid,note='I returned today and the fault needs another inspection.'),secrets.token_hex(16))
        self.assertEqual(self.current()['status'],'HUMAN_REVIEW')
        self.assertFalse(self.current().get('closure_reason'))
        self.assertEqual(len(self.s.portal(self.code)['cases']),1)

    def test_unresolved_button_also_reopens_inactive_closure(self):
        since=self.start_wait();self.tick_at(since+timedelta(days=8))
        self.s.portal_feedback(self.code,dict(id=self.cid,resolved=False),secrets.token_hex(16))
        self.assertEqual(self.current()['status'],'HUMAN_REVIEW')

    def test_confirmed_customer_outcome_waits_for_staff_instead_of_timeout(self):
        since=self.start_wait()
        self.s.portal_feedback(self.code,dict(id=self.cid,resolved=True),secrets.token_hex(16))
        self.tick_at(since+timedelta(days=20));self.assertEqual(self.current()['status'],'FOLLOW_UP')
        self.action('verify_close',note='Customer confirmed the checked repair.',confirmed=True)
        self.assertTrue(self.current()['verification'])

    def test_needs_staff_does_not_close_and_existing_wait_gets_full_period(self):
        self.tick_at(datetime.now(timezone.utc)+timedelta(days=100))
        self.assertEqual(self.current()['status'],'HUMAN_REVIEW')
        self.start_wait()
        with self.s.store.connect() as db:
            c=self.current();c.pop('waiting_since');self.s.store.put(db,'case',c)
        moment=datetime.now(timezone.utc)+timedelta(days=100)
        self.tick_at(moment);self.assertEqual(self.current()['waiting_since'],moment.isoformat())
        self.assertEqual(self.current()['status'],'FOLLOW_UP')

    def test_open_workorder_blocks_inactivity_closure(self):
        since=self.start_wait()
        with self.s.store.connect() as db:self.s.store.put(db,'workorder',dict(id='WO-QA',case_id=self.cid,status='OPEN'))
        self.tick_at(since+timedelta(days=20));self.assertEqual(self.current()['status'],'FOLLOW_UP')

    def test_wait_period_saved_and_validated(self):
        for days in (0,91,True,'7'):
            with self.assertRaises(ValueError):self.s.command('closure_settings',dict(days=days),secrets.token_hex(16))
        self.s.command('closure_settings',dict(days=3),secrets.token_hex(16))
        since=self.start_wait();self.tick_at(since+timedelta(days=3))
        self.assertEqual(self.current()['status'],'CLOSED')
        self.assertEqual(self.s.snapshot()['closure_policy']['days'],3)
