"""Automatic local drafts share reservations with manual requests; no providers or posts."""
import copy
import os
import secrets
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from belive import public_draft_jobs as jobs, public_preview
from belive.service import Service
from server import Tasks
from test_backend import FakeAI


class DraftAI(FakeAI):
    def __init__(self):
        super().__init__()
        self.public_calls = []
        self.effect = None

    def public_reply_preview(self, context):
        self.public_calls.append(copy.deepcopy(context))
        if self.effect:
            return self.effect(context)
        if context['complaint_level'] == 'HIGH':
            return 'We’re sorry about the urgent concern you reported. Staff can review it privately with you.'
        return 'We’re sorry the washer is still not spinning. What brand, model and display error does it have?'


class PublicDraftJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ai = DraftAI()
        self.service = Service(Path(self.tmp.name) / 'test.db', self.ai)
        diagnostic = patch('belive.public_diagnostics.prepare', return_value={
            'state': 'NEEDS_DETAILS', 'details': {}, 'research_summary': '', 'sources': [],
        })
        diagnostic.start()
        self.addCleanup(diagnostic.stop)
        provider = patch('belive.hosted_ai.generate', side_effect=AssertionError('Unexpected provider call'))
        self.provider = provider.start()
        self.addCleanup(provider.stop)

    def case(self, assessed=True, level='MODERATE', platform='GOOGLE'):
        case = self.service.command('intake', {
            'title': 'Fictional washer complaint', 'description': 'The shared washer will not spin after an earlier report.',
            'platform': platform, 'source_id': 'fixture-' + secrets.token_hex(8),
        }, secrets.token_hex(16))
        if assessed:
            severity = {'SIMPLE': 'LOW', 'MODERATE': 'MEDIUM', 'HIGH': 'HIGH'}[level]
            case.update(category='MAINTENANCE', severity=severity, handoff=level != 'SIMPLE',
                        status='AWAITING_CONTACT' if level == 'SIMPLE' else 'HUMAN_REVIEW',
                        staff_destination='Fictional maintenance team', draft='Original staff posting draft.',
                        analysis={'report_type': 'COMPLAINT', 'relevance': 'SUPPORT', 'uncertainty': False,
                                  'requires_human': level != 'SIMPLE', 'severity': severity,
                                  'summary': 'The customer reports an unresolved shared washer fault.'})
            self.save_case(case)
        return case

    def save_case(self, case):
        with self.service.store.connect() as db:
            self.service.store.put(db, 'case', case)

    def saved(self, case):
        with self.service.store.connect() as db:
            return self.service.store.get(db, 'case', case['id'])

    def rows(self, kind):
        with self.service.store.connect() as db:
            return self.service.store.all(db, kind)

    def job(self, case):
        with self.service.store.connect() as db:
            return self.service.store.get(db, jobs.KIND, case['id'])

    def prepare(self, case, manual=False):
        return jobs.prepare(self.service, case['id'], self.saved(case)['revision'], 'Fictional operator', manual)

    def test_assessment_completion_prepares_a_tailored_draft_without_another_action(self):
        case = self.case(assessed=False)
        tasks = Tasks(self.service)
        with patch.object(tasks, 'start', side_effect=lambda key, fn: fn()):
            result = tasks.assess_and_preview(case['id'])
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(len(self.ai.public_calls), 1)
        self.assertIn('public_reply_preview', self.saved(case))
        self.assertEqual(self.job(case)['status'], 'COMPLETE')
        self.provider.assert_not_called()

    def test_current_draft_is_skipped_automatically_and_manual_rewrite_is_explicit(self):
        case = self.case()
        first = self.prepare(case)
        self.assertEqual(self.prepare(case), first)
        self.assertEqual(len(self.ai.public_calls), 1)
        self.prepare(case, manual=True)
        self.assertEqual(len(self.ai.public_calls), 2)

    def test_same_case_manual_and_auto_requests_share_one_running_generation(self):
        case = self.case()
        entered, release = threading.Event(), threading.Event()

        def waiting_reply(context):
            entered.set()
            self.assertTrue(release.wait(5), 'Test release was not signalled')
            return 'We’re sorry the washer is not spinning. Which display error is shown?'

        self.ai.effect = waiting_reply
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.prepare, case)
            try:
                self.assertTrue(entered.wait(5))
                state = self.prepare(case, manual=True)
                self.assertEqual(state['status'], 'RUNNING')
                self.assertTrue(state['current_input'])
                self.assertEqual(len(self.ai.public_calls), 1)
            finally:
                release.set()
            self.assertIn('display error', future.result(timeout=5)['text'])
        self.assertEqual(self.job(case)['status'], 'COMPLETE')

    def test_different_cases_and_service_instances_still_have_one_running_draft(self):
        first, second = self.case(), self.case()
        peer = Service(self.service.store.path, self.ai)
        entered, release = threading.Event(), threading.Event()

        def waiting_reply(context):
            entered.set()
            self.assertTrue(release.wait(5))
            return 'We’re sorry about the washer fault. What error code is displayed?'

        self.ai.effect = waiting_reply
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.prepare, first)
            try:
                self.assertTrue(entered.wait(5))
                state = jobs.prepare(peer, second['id'], second['revision'], 'Fictional peer', manual=True)
                self.assertEqual(state['status'], 'QUEUED')
                self.assertEqual(len(self.ai.public_calls), 1)
            finally:
                release.set()
            future.result(timeout=5)
        self.ai.effect = None
        jobs.run_next(peer)
        self.assertEqual(len(self.ai.public_calls), 2)
        self.assertEqual(self.job(second)['status'], 'COMPLETE')

    def test_failed_input_does_not_retry_each_tick_and_preserves_saved_draft(self):
        case = self.case()
        case['public_reply_preview'] = {'text': 'Earlier saved draft remains available.'}
        self.save_case(case)

        def fail(context):
            raise RuntimeError('Fictional private provider diagnostic sk-test-secret')

        self.ai.effect = fail
        before_messages, before_outbox = self.rows('message'), self.rows('outbox')
        with self.assertRaises(ValueError):
            self.prepare(case)
        first_job = self.job(case)
        self.assertEqual(first_job['status'], 'FAILED')
        self.assertNotIn('sk-test-secret', str(first_job))
        self.assertEqual(self.saved(case), case)
        for _ in range(3):
            jobs.queue_next(self.service)
            jobs.run_next(self.service)
            self.prepare(case)
        self.assertEqual(len(self.ai.public_calls), 1)
        self.assertEqual(self.rows('message'), before_messages)
        self.assertEqual(self.rows('outbox'), before_outbox)
        self.ai.effect = None
        self.prepare(case, manual=True)
        self.assertEqual(self.job(case)['status'], 'COMPLETE')
        self.assertEqual(len(self.ai.public_calls), 2)

    def test_changed_source_followup_and_assessment_each_allow_a_new_automatic_attempt(self):
        for change in ['source', 'followup', 'assessment']:
            with self.subTest(change=change):
                case = self.case()
                self.prepare(case)
                saved = self.saved(case)
                if change == 'source':
                    saved['source_versions'].append('fixture-new-source-version')
                elif change == 'assessment':
                    saved['analysis']['summary'] += ' The display now shows an error.'
                else:
                    with self.service.store.connect() as db:
                        self.service.store.put(db, 'public_followup', {
                            'id': 'fixture-' + secrets.token_hex(8), 'case_id': case['id'],
                            'text': 'The display shows E20.', 'source_url': '', 'created_at': '2026-11-28',
                        })
                saved['revision'] += 1
                self.save_case(saved)
                calls = len(self.ai.public_calls)
                self.prepare(saved)
                self.assertEqual(len(self.ai.public_calls), calls + 1)
                self.assertEqual(self.job(case)['status'], 'COMPLETE')

    def test_case_change_during_generation_records_stale_and_keeps_the_previous_draft(self):
        case = self.case()
        case['public_reply_preview'] = {'text': 'Earlier staff-reviewed wording.'}
        self.save_case(case)

        def change_assessment(context):
            changed = self.saved(case)
            changed['revision'] += 1
            changed['analysis']['summary'] = 'Updated assessment with a new customer concern.'
            changed['draft'] = 'New staff wording must remain.'
            self.save_case(changed)
            return 'What error code is currently displayed?'

        self.ai.effect = change_assessment
        with self.assertRaisesRegex(ValueError, 'case changed'):
            self.prepare(case)
        self.assertEqual(self.job(case)['status'], 'STALE')
        self.assertEqual(self.saved(case)['public_reply_preview'], case['public_reply_preview'])
        self.assertEqual(self.saved(case)['draft'], 'New staff wording must remain.')
        self.ai.effect = None
        self.prepare(self.saved(case))
        self.assertEqual(self.job(case)['status'], 'COMPLETE')

    def test_stale_caller_revision_does_not_reserve_or_generate(self):
        case = self.case()
        with self.assertRaisesRegex(ValueError, 'Case changed'):
            jobs.prepare(self.service, case['id'], case['revision'] - 1, 'Fictional operator', True)
        self.assertEqual(self.rows(jobs.KIND), [])
        self.assertEqual(self.ai.public_calls, [])

    def test_interrupted_running_job_requires_explicit_retry_without_duplicate_model_calls(self):
        case = self.case()
        jobs.queue(self.service, case['id'], case['revision'], 'Fictional operator')
        job = self.job(case)
        job.update(status='RUNNING', owner_pid=os.getpid())
        with self.service.store.connect() as db:
            self.service.store.put(db, jobs.KIND, job)
        self.assertEqual(jobs.recover(self.service), 1)
        self.assertEqual(self.job(case)['status'], 'FAILED')
        self.assertEqual(self.job(case)['error_code'], 'INTERRUPTED')
        jobs.queue_next(self.service)
        jobs.run_next(self.service)
        self.assertEqual(self.ai.public_calls, [])
        self.prepare(case, manual=True)
        self.assertEqual(len(self.ai.public_calls), 1)

    def test_interruption_after_core_saved_a_current_preview_recovers_as_complete(self):
        case = self.case()
        result = self.prepare(case)
        job = self.job(case)
        job.update(status='RUNNING', owner_pid=os.getpid())
        with self.service.store.connect() as db:
            self.service.store.put(db, jobs.KIND, job)
        jobs.recover(self.service)
        self.assertEqual(self.job(case)['status'], 'COMPLETE')
        self.assertEqual(self.prepare(case), result)
        self.assertEqual(len(self.ai.public_calls), 1)

    def test_backfill_queues_only_one_legacy_case_and_status_is_read_only(self):
        cases = [self.case() for _ in range(4)]
        with self.service.store.connect() as db:
            before = self.service.store.all(db, jobs.KIND)
            state = jobs.status(self.service, db, cases[0])
            self.assertEqual(state['status'], 'QUEUED')
            self.assertEqual(self.service.store.all(db, jobs.KIND), before)
        tasks = Tasks(self.service)
        with patch.object(tasks, 'start', return_value=True) as start:
            tasks.public_drafts(backfill=True)
            tasks.public_drafts(backfill=True)
        self.assertEqual(len(self.rows(jobs.KIND)), 1)
        self.assertEqual(self.rows(jobs.KIND)[0]['status'], 'QUEUED')
        self.assertEqual(self.ai.public_calls, [])
        self.assertTrue(all(call.args[0] == 'public-draft-worker' for call in start.call_args_list))

    def test_batch_assessment_and_api_scan_paths_use_the_same_coordinator(self):
        cases = [self.case(assessed=False) for _ in range(2)]
        tasks = Tasks(self.service)
        with patch.object(tasks, 'start', side_effect=lambda key, fn: fn()), patch('server.threading.Thread') as thread:
            tasks.analyse_batch(cases)
            thread.call_args.kwargs['target']()
        self.assertEqual(len(self.ai.public_calls), 2)
        self.assertTrue(all(self.job(case)['status'] == 'COMPLETE' for case in cases))
        scan_case = self.case(assessed=False)
        with patch('server.scan', return_value=[scan_case['id']]), \
                patch.object(tasks, 'start', side_effect=lambda key, fn: fn()):
            tasks.scan('fixture-source')
        self.assertEqual(self.job(scan_case)['status'], 'COMPLETE')

    def test_backfill_starts_before_first_scheduler_wait_and_prefers_recent_activity(self):
        recent, old = self.case(), self.case()
        recent['updated_at'] = '2026-11-28T12:00:00+00:00'
        old['updated_at'] = '2026-11-20T12:00:00+00:00'
        self.save_case(recent)
        self.save_case(old)
        tasks = Tasks(self.service)
        tasks.stop.set()
        with patch.object(tasks, 'start', side_effect=lambda key, fn: fn()):
            tasks._loop()
        self.assertEqual(self.job(recent)['status'], 'COMPLETE')
        self.assertEqual(len(self.rows(jobs.KIND)), 1)
        self.assertEqual(len(self.ai.public_calls), 1)

    def test_paused_cases_skip_automatic_drafts_but_allow_an_explicit_rewrite(self):
        case = self.case()
        case['automation_paused'] = True
        self.save_case(case)
        self.assertIsNone(self.prepare(case))
        self.assertIsNone(jobs.queue_next(self.service))
        with self.service.store.connect() as db:
            self.assertIsNone(jobs.status(self.service, db, case))
        self.assertEqual(self.ai.public_calls, [])
        self.prepare(case, manual=True)
        self.assertEqual(self.job(case)['status'], 'COMPLETE')
        self.assertEqual(len(self.ai.public_calls), 1)
        queued = self.case()
        jobs.queue(self.service, queued['id'], queued['revision'], 'Fictional operator')
        queued['automation_paused'] = True
        self.save_case(queued)
        self.prepare(queued, manual=True)
        self.assertEqual(self.job(queued)['status'], 'COMPLETE')
        self.assertEqual(len(self.ai.public_calls), 2)

    def test_pausing_an_already_queued_case_cancels_its_auto_call_and_can_resume(self):
        case = self.case()
        jobs.queue(self.service, case['id'], case['revision'], 'Fictional operator')
        case['automation_paused'] = True
        self.save_case(case)
        jobs.run_next(self.service)
        self.assertEqual(self.job(case)['error_code'], 'PAUSED')
        self.assertEqual(self.ai.public_calls, [])
        case['automation_paused'] = False
        self.save_case(case)
        self.prepare(case)
        self.assertEqual(self.job(case)['status'], 'COMPLETE')

    def test_nonpublic_uncertain_enquiry_and_inactive_cases_are_not_automatically_drafted(self):
        for change in ['nonpublic', 'uncertain', 'enquiry', 'closed']:
            with self.subTest(change=change):
                case = self.case()
                if change == 'nonpublic':
                    case.update(platform='INTERNAL', entrypoint='TENANT_WEBSITE')
                elif change == 'uncertain':
                    case['analysis']['uncertainty'] = True
                elif change == 'enquiry':
                    case['analysis']['report_type'] = 'ENQUIRY'
                else:
                    case['status'] = 'CLOSED'
                self.save_case(case)
                self.assertIsNone(self.prepare(case))
        self.assertEqual(self.rows(jobs.KIND), [])
        self.assertEqual(self.ai.public_calls, [])

    def test_high_uses_existing_acknowledgement_core_without_changing_staff_or_posting_state(self):
        case = self.case(level='HIGH')
        before_messages, before_outbox = self.rows('message'), self.rows('outbox')
        result = self.prepare(case)
        saved = self.saved(case)
        self.assertEqual(self.ai.public_calls[0]['complaint_level'], 'HIGH')
        self.assertIn('urgent concern', result['text'])
        for field, value in case.items():
            if field not in {'public_reply_preview', 'revision', 'updated_at'}:
                self.assertEqual(saved[field], value, field)
        self.assertEqual(self.rows('message'), before_messages)
        self.assertEqual(self.rows('outbox'), before_outbox)


if __name__ == '__main__':
    unittest.main()
