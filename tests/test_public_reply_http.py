"""Real local HTTP intake-to-draft and explicit send dispatch; no platform writes."""
import json
import secrets
import time
import unittest
from unittest.mock import Mock, patch

import test_http as fixtures


class PublicReplyHttpTests(unittest.TestCase):
    setUp = fixtures.HttpTests.setUp
    tearDown = fixtures.HttpTests.tearDown
    request = fixtures.HttpTests.request

    def headers(self):
        return {'X-CSRF-Token': self.csrf, 'Idempotency-Key': secrets.token_hex(16)}

    def test_public_intake_prepares_a_draft_without_a_prepare_request_or_publication(self):
        self.s.ai.public_reply_preview = Mock(return_value=(
            'I am sorry the shared connection keeps dropping. '
            'Does the same problem affect more than one device?'))
        with patch('belive.public_replies.publish') as publish:
            code, body = self.request('/api/intake', {
                'title': 'Fictional shared Wi-Fi report', 'platform': 'THREADS',
                'source_id': '123456789012345',
                'description': 'The shared Wi-Fi connection drops every evening.'}, self.headers())
            self.assertEqual(code, 200)
            case_id = json.loads(body)['id']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with self.s.store.connect() as db:
                    case = self.s.store.get(db, 'case', case_id)
                shown = next(c for c in self.s.snapshot()['cases'] if c['id'] == case_id)
                if case.get('public_reply_preview') and (shown.get('public_reply_job') or {}).get('status') == 'COMPLETE':
                    break
                time.sleep(.02)
            self.assertIn('public_reply_preview', case)
            self.s.ai.public_reply_preview.assert_called_once()
            self.assertTrue(shown['public_preview_current'])
            self.assertEqual(shown['public_reply_job']['status'], 'COMPLETE')
            self.assertNotIn('public_reply', case)
            publish.assert_not_called()

    def test_send_dispatches_approved_text_with_authenticated_actor_and_request_key(self):
        payload = {'id': 'fixture-case', 'revision': 4, 'confirmed': True,
                   'text': 'Reviewed fixture wording for the original Threads item.',
                   '_actor': 'untrusted-client-actor'}
        headers = self.headers()
        receipt = {'status': 'POSTED', 'platform': 'THREADS', 'detail': 'Fixture receipt only.'}
        with patch('belive.public_replies.publish', return_value=receipt) as publish:
            code, body = self.request('/api/public-reply', payload, headers)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), receipt)
        service, sent, actor, key = publish.call_args.args
        self.assertIs(service, self.s)
        self.assertEqual(sent['text'], payload['text'])
        self.assertEqual(sent['_actor'], 'qa-admin')
        self.assertEqual(actor, 'qa-admin')
        self.assertEqual(key, headers['Idempotency-Key'])

    def test_send_requires_a_signed_in_operator_and_current_csrf(self):
        with patch('belive.public_replies.publish') as publish:
            self.assertEqual(self.request('/api/public-reply', {}, {'Cookie': '', **self.headers()})[0], 401)
            self.assertEqual(self.request('/api/public-reply', {}, {'X-CSRF-Token': 'old-token'})[0], 403)
            publish.assert_not_called()

    def test_background_draft_progress_is_exposed_without_claiming_platform_access(self):
        self.s.ai.public_reply_preview = Mock(side_effect=ValueError('AI_INVALID_PLAN'))
        code, body = self.request('/api/intake', {
            'title': 'Fictional Wi-Fi question', 'platform': 'THREADS',
            'source_id': '223456789012345',
            'description': 'The shared Wi-Fi connection drops every evening.'}, self.headers())
        self.assertEqual(code, 200)
        case_id = json.loads(body)['id']
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            case = next(c for c in self.s.snapshot()['cases'] if c['id'] == case_id)
            if (case.get('public_reply_job') or {}).get('status') == 'FAILED':
                break
            time.sleep(.02)
        self.assertEqual(case['public_reply_job']['status'], 'FAILED')
        self.assertTrue(case['public_reply_job']['error'])
        self.assertFalse(case['public_posting']['ready'])
        self.s.ai.public_reply_preview.assert_called_once()
