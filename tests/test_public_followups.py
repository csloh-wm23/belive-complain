"""Observed public replies remain local evidence, not tenant messages or publication."""
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from belive import public_preview
from belive.service import Service


class PublicFollowupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ai = Mock()
        self.ai.readiness.return_value = True
        self.service = Service(Path(self.tmp.name) / 'test.db', self.ai)
        self.case = self.public_case()

    def command(self, name, payload, key=None):
        return self.service.command(name, payload, key or secrets.token_hex(16))

    def public_case(self, platform='GOOGLE'):
        case = self.command('intake', {
            'title': 'Fictional shared washer fault',
            'description': 'The shared washer will not spin despite an earlier report.',
            'platform': platform, 'source_id': 'fixture-' + secrets.token_hex(8),
        })
        case.update(category='MAINTENANCE', severity='MEDIUM', handoff=True,
                    status='HUMAN_REVIEW', staff_destination='Fictional maintenance team',
                    draft='Existing posting draft must remain unchanged.',
                    analysis={'report_type': 'COMPLAINT', 'relevance': 'SUPPORT',
                              'severity': 'MEDIUM', 'requires_human': True, 'uncertainty': False,
                              'summary': 'Reported washer fault with an earlier unresolved report.'})
        case['public_reply_preview'] = {
            'text': 'What brand and model is the washer, and is there a display error?',
            'source_version': case['source_versions'][-1],
            'format_version': public_preview.VERSION,
            'input_fingerprint': public_preview.fingerprint(public_preview.context(case)),
        }
        with self.service.store.connect() as db:
            self.service.store.put(db, 'case', case)
        return case

    def saved_case(self, case_id=None):
        with self.service.store.connect() as db:
            return self.service.store.get(db, 'case', case_id or self.case['id'])

    def payload(self, case=None, **changes):
        case = case or self.case
        return {'id': case['id'], 'revision': case['revision'],
                'text': 'It is a fictional Example W123 washer showing E20.',
                'source_url': '', **changes}

    def evidence_snapshot(self):
        with self.service.store.connect() as db:
            return {
                'objects': [tuple(row) for row in db.execute('SELECT * FROM objects ORDER BY kind,id')],
                'sources': [tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')],
                'events': self.service.store.audit(db),
            }

    def test_observed_public_reply_preserves_original_source_and_operational_state(self):
        before = self.saved_case()
        with self.service.store.connect() as db:
            messages = self.service.store.all(db, 'message')
            outbox = self.service.store.all(db, 'outbox')
            sources = [tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')]
        url = 'https://www.google.com/maps/reviews/fictional-reply'
        with patch('belive.connectors.request_json', side_effect=AssertionError('No platform request')) as request:
            result = self.command('public_followup', self.payload(source_url=url, _actor='Fictional reviewer'))
        request.assert_not_called()
        saved = self.saved_case()
        self.assertEqual(result['id'], self.case['id'])
        self.assertEqual(result['revision'], before['revision'] + 1)
        for field, value in before.items():
            if field not in {'revision', 'updated_at'}:
                self.assertEqual(saved[field], value, field)
        with self.service.store.connect() as db:
            replies = self.service.public_followups(db, self.case['id'])
            self.assertEqual(len(replies), 1)
            reply = replies[0]
            self.assertEqual(reply['id'], result['followup_id'])
            self.assertEqual(reply['case_id'], self.case['id'])
            self.assertEqual(reply['text'], self.payload()['text'])
            self.assertEqual(reply['source_url'], url)
            self.assertEqual(reply['recorded_by'], 'Fictional reviewer')
            self.assertEqual(reply['provenance'], 'OPERATOR_RECORDED_PUBLIC_FOLLOWUP')
            self.assertTrue(reply['created_at'])
            self.assertNotIn('tenant_id', reply)
            self.assertEqual(self.service.store.all(db, 'message'), messages)
            self.assertEqual(self.service.store.all(db, 'outbox'), outbox)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')], sources)
            self.assertTrue(any(event['action'] == 'PUBLIC_FOLLOWUP_RECORDED'
                                for event in self.service.store.audit(db)))
        self.ai.generate.assert_not_called()
        self.ai.public_reply_preview.assert_not_called()

    def test_repeat_request_and_duplicate_observation_do_not_create_extra_turns(self):
        payload = self.payload()
        first = self.command('public_followup', payload, 'fixture-followup-idempotency')
        after_first = self.evidence_snapshot()
        self.assertEqual(self.command('public_followup', payload, 'fixture-followup-idempotency'), first)
        self.assertEqual(self.evidence_snapshot(), after_first)
        second = self.command('public_followup', {**payload, 'revision': first['revision']})
        self.assertEqual(second, first)
        self.assertEqual(self.evidence_snapshot(), after_first)
        with self.assertRaisesRegex(ValueError, 'Idempotency key reused'):
            self.command('public_followup', {**payload, 'text': 'Different observed reply.'},
                         'fixture-followup-idempotency')
        self.assertEqual(self.evidence_snapshot(), after_first)

    def test_stale_case_revision_rejects_followup_without_writing_evidence(self):
        first = self.command('public_followup', self.payload())
        before = self.evidence_snapshot()
        with self.assertRaisesRegex(ValueError, 'Case changed'):
            self.command('public_followup', self.payload(text='A newer reply says there is no error code.'))
        self.assertEqual(self.evidence_snapshot(), before)
        self.assertEqual(self.saved_case()['revision'], first['revision'])

    def test_followup_is_attached_only_to_the_selected_case_and_invalidates_its_preview(self):
        other = self.public_case()
        shown = next(item for item in self.service.snapshot()['cases'] if item['id'] == self.case['id'])
        self.assertTrue(shown['public_preview_current'])
        self.command('public_followup', self.payload())
        snapshots = {item['id']: item for item in self.service.snapshot()['cases']}
        self.assertFalse(snapshots[self.case['id']]['public_preview_current'])
        self.assertEqual(len(snapshots[self.case['id']]['public_followups']), 1)
        self.assertEqual(snapshots[other['id']]['public_followups'], [])
        self.assertTrue(snapshots[other['id']]['public_preview_current'])
        self.assertEqual(self.saved_case(other['id']), other)

    def test_reply_link_must_be_an_https_link_from_the_cases_platform(self):
        links = [
            ('GOOGLE', 'https://www.google.com/maps/reviews/fictional-reply'),
            ('FACEBOOK', 'https://www.facebook.com/fictional/posts/123?comment_id=456'),
            ('THREADS', 'https://www.threads.com/@fictional/post/Fixture001'),
        ]
        for platform, link in links:
            with self.subTest(platform=platform):
                case = self.public_case(platform)
                self.command('public_followup', self.payload(case, source_url=link))
                with self.service.store.connect() as db:
                    self.assertEqual(self.service.public_followups(db, case['id'])[0]['source_url'], link)
        for link in ['https://www.facebook.com/fictional/posts/123',
                     'https://example.invalid/public-reply',
                     'http://www.google.com/maps/reviews/fictional-reply',
                     'https://www.google.com.attacker.invalid/maps/reviews/reply']:
            with self.subTest(link=link):
                before = self.evidence_snapshot()
                with self.assertRaises(ValueError):
                    self.command('public_followup', self.payload(source_url=link))
                self.assertEqual(self.evidence_snapshot(), before)

    def test_invalid_followup_fields_are_rejected_without_partial_writes(self):
        for changes in [{'text': ''}, {'text': ' '}, {'text': 'x' * 3001}, {'text': None},
                        {'source_url': ['not a URL']}, {'source_url': 'x' * 2001}]:
            with self.subTest(changes=changes):
                before = self.evidence_snapshot()
                with self.assertRaises(ValueError):
                    self.command('public_followup', self.payload(**changes))
                self.assertEqual(self.evidence_snapshot(), before)

    def test_private_contact_details_are_redacted_in_the_observed_reply(self):
        text = 'The washer shows E20. My fictional email is test-user@example.invalid and phone +60125551234.'
        self.command('public_followup', self.payload(text=text))
        with self.service.store.connect() as db:
            saved = self.service.public_followups(db, self.case['id'])[0]
            self.assertIn('E20', saved['text'])
            self.assertIn('[email removed]', saved['text'])
            self.assertIn('[number removed]', saved['text'])
            self.assertNotIn('test-user@example.invalid', str(saved))
            self.assertNotIn('+60125551234', str(saved))

    def test_inactive_and_nonpublic_cases_cannot_accept_an_observed_public_reply(self):
        for change in ['CLOSED', 'SKIPPED', 'VERIFIED', 'ANSWERED', 'nonpublic']:
            with self.subTest(change=change):
                case = self.public_case()
                if change == 'nonpublic':
                    case.update(platform='INTERNAL', entrypoint='TENANT_WEBSITE')
                else:
                    case['status'] = change
                with self.service.store.connect() as db:
                    self.service.store.put(db, 'case', case)
                before = self.evidence_snapshot()
                with self.assertRaises(ValueError):
                    self.command('public_followup', self.payload(case))
                self.assertEqual(self.evidence_snapshot(), before)

    def test_new_danger_in_public_followup_queues_a_local_staff_alert(self):
        with self.service.store.connect() as db:
            messages = self.service.store.all(db, 'message')
            previous_outbox = self.service.store.all(db, 'outbox')
        with patch('belive.connectors.request_json', side_effect=AssertionError('No external send')) as request:
            self.command('public_followup', self.payload(text='The washer now has sparks coming from its socket.'))
        request.assert_not_called()
        saved = self.saved_case()
        self.assertEqual(saved['severity'], 'CRITICAL')
        self.assertEqual(saved['status'], 'HUMAN_REVIEW')
        self.assertTrue(saved['handoff'])
        self.assertEqual(saved['draft'], self.case['draft'])
        self.assertEqual(saved['source_versions'], self.case['source_versions'])
        with self.service.store.connect() as db:
            self.assertEqual(self.service.store.all(db, 'message'), messages)
            alerts = [item for item in self.service.store.all(db, 'outbox') if item not in previous_outbox]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]['entity'], self.case['id'])
            self.assertEqual(alerts[0]['kind'], 'STAFF_ALERT')
            self.assertEqual(alerts[0]['status'], 'PENDING_APPROVAL')
            self.assertEqual(len(self.service.public_followups(db, self.case['id'])), 1)
        self.ai.generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
