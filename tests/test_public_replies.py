"""Official publishing transport fixtures. No live platform writes or credentials."""
import io
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from belive import public_preview, public_replies as replies
from belive.store import Store, digest, now


class PublicRepliesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = SimpleNamespace(store=Store(Path(self.tmp.name) / 'fixture.db'), lock=threading.RLock())
        self.case = self.seed('THREADS')
        self.requests = []
        self.fail_write = None
        self.statuses = ['FINISHED']
        self.account = '111'
        self.parent_owner = '111'
        self.source_text = self.case['description']
        self.profile_hook = None
        self.net = patch('belive.public_replies.request_json', side_effect=self.api).start()
        patch('belive.public_replies.time.sleep').start()
        patch('belive.public_replies.get_value', side_effect=lambda name, **kw: 'v27.0' if name == 'BELIVE_FACEBOOK_VERSION' else 'fixture-token-not-a-real-secret').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.tmp.cleanup)

    def seed(self, platform, comment=False):
        target = '333' if platform == 'THREADS' else '777' if comment else '111_333'
        if platform == 'GOOGLE': target = 'accounts/111/locations/222/reviews/fixtureReview'
        source = '111/threads' if platform == 'THREADS' else '111_222/comments' if comment else '111/feed'
        if platform == 'GOOGLE': source = 'accounts/111/locations/222'
        case = dict(id='FIXTURE-' + platform, platform=platform, source_id=target, entrypoint='PUBLIC_SOURCE',
            title='Synthetic fixture complaint', description='This is a fictional complaint about a broken shared appliance.',
            status='HUMAN_REVIEW', severity='MEDIUM', category='MAINTENANCE', revision=1,
            tenant_id='', handoff=True, owner='Fixture staff', staff_destination='Support team',
            analysis=dict(report_type='COMPLAINT', relevance='SUPPORT', uncertainty=False, summary='Synthetic fixture assessment.'))
        if platform == 'THREADS': case['parent_source_id'] = '222'
        if comment: case['parent_source_id'] = '111_222'
        with self.service.store.connect() as db:
            row = db.execute('INSERT INTO sources(platform,source_id,hash,body,created_at) VALUES(?,?,?,?,?)',
                (platform, target, digest(case['description']), '{}', now())).lastrowid
            case['source_versions'] = [row]
            inputs = public_preview.context(case, [])
            case['public_reply_preview'] = dict(text='A fictional reviewed reply.', source_version=row,
                input_fingerprint=public_preview.fingerprint(inputs), format_version=public_preview.VERSION)
            self.service.store.put(db, 'case', case)
            self.service.store.put(db, 'source', dict(id='SRC-' + platform, platform=platform, resource=source, authorised=True, enabled=True))
        return case

    def current(self):
        with self.service.store.connect() as db:
            return self.service.store.get(db, 'case', self.case['id'])

    def change(self, **values):
        with self.service.store.connect() as db:
            case = self.service.store.get(db, 'case', self.case['id']);case.update(values)
            self.service.store.put(db, 'case', case)

    def payload(self, **values):
        return dict(id=self.case['id'], revision=self.current()['revision'], text='Thank you for reporting this specific issue.', confirmed=True, **values)

    def send(self, payload=None, key='fixture-request-01'):
        return replies.publish(self.service, payload or self.payload(), 'fixture-staff', key)

    def api(self, url, token, payload=None, method=None, **kwargs):
        self.requests.append((url, payload, method))
        path = urlsplit(url).path
        if payload is not None:
            if self.fail_write: raise self.fail_write
            if path.endswith('/threads_publish'): return {'id': '555'}
            if path.endswith('/threads'): return {'id': '444'}
            if path.endswith('/comments'): return {'id': '111_999'}
            raise AssertionError('Unexpected fixture write path: ' + path)
        if path.endswith('/me'):
            if self.profile_hook: self.profile_hook()
            return {'id': self.account, 'name': 'Fixture Page', 'username': 'fixture', 'category': 'Fictional test Page'}
        if path.endswith('/444'):
            state = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return {'id': '444', 'status': state}
        if path.endswith('/222'): return {'id': '222', 'owner': {'id': self.parent_owner}}
        if path.endswith('/111_222'): return {'id': '111_222', 'from': {'id': self.parent_owner}}
        if path.endswith('/222/replies'): return {'data': [{'id': '333', 'text': self.source_text}]}
        if path.endswith('/111_222/comments'):
            return {'data': [{'id': '777', 'message': self.source_text, 'can_comment': True, 'from': {'id': '999'}}]}
        if path.endswith('/111_333'):
            return {'id': '111_333', 'message': self.source_text, 'from': {'id': self.parent_owner}}
        raise AssertionError('Unexpected fixture read path: ' + path)

    def writes(self):
        return [x for x in self.requests if x[1] is not None]

    def test_eligibility_is_local_and_does_not_claim_token_is_verified_permission(self):
        result = replies.eligibility(self.service, self.current())
        self.assertTrue(result['ready']);self.assertFalse(result['publishing_verified'])
        self.assertEqual(result['target_label'], 'Threads');self.net.assert_not_called()

    def test_threads_uses_exact_reply_target_then_publishes_saved_container(self):
        before = self.current()
        result = self.send()
        writes = self.writes()
        self.assertEqual(result['status'], 'POSTED');self.assertEqual(result['receipt_id'], '555')
        self.assertEqual(writes[0][0], 'https://graph.threads.com/v1.0/111/threads')
        self.assertEqual(writes[0][1]['reply_to_id'], '333')
        self.assertIs(writes[0][1]['auto_publish_text'], False)
        self.assertEqual(writes[1][0], 'https://graph.threads.com/v1.0/111/threads_publish')
        self.assertEqual(writes[1][1], {'creation_id': '444'})
        after = self.current()
        for field in ['status', 'severity', 'owner', 'handoff', 'staff_destination', 'source_versions', 'description']:
            self.assertEqual(before[field], after[field])

    def test_facebook_feed_replies_to_original_post_as_verified_company_page(self):
        self.case = self.seed('FACEBOOK');self.source_text = self.case['description']
        result = self.send()
        self.assertEqual(result['status'], 'POSTED')
        self.assertEqual(self.writes()[0][0], 'https://graph.facebook.com/v27.0/111_333/comments')
        self.assertEqual(self.writes()[0][1], {'message': self.payload()['text']})

    def test_facebook_comment_replies_to_comment_id_not_its_parent_post(self):
        self.case = self.seed('FACEBOOK', comment=True);self.source_text = self.case['description']
        result = self.send()
        self.assertEqual(result['status'], 'POSTED')
        self.assertTrue(self.writes()[0][0].endswith('/777/comments'))

    def feed_comment_fixture(self):
        self.case = self.seed('FACEBOOK', comment=True)
        with self.service.store.connect() as db:
            source = self.service.store.get(db, 'source', 'SRC-FACEBOOK')
            source['resource'] = '111/feed'
            self.service.store.put(db, 'source', source)
            case = self.service.store.get(db, 'case', self.case['id'])
            case.update(public_source_kind='FACEBOOK_COMMENT', parent_source_id='111_222',
                        parent_public_url='https://www.facebook.com/111/posts/222',
                        public_url='https://www.facebook.com/111/posts/222?comment_id=777')
            case['public_reply_preview']['input_fingerprint'] = public_preview.fingerprint(public_preview.context(case, []))
            self.service.store.put(db, 'case', case)
        self.source_text = self.case['description']

    def test_page_monitored_comment_publishes_only_to_exact_comment_after_parent_verification(self):
        self.feed_comment_fixture()
        result = self.send()
        self.assertEqual(result['status'], 'POSTED')
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0][0], 'https://graph.facebook.com/v27.0/777/comments')
        self.assertEqual(self.writes()[0][1], {'message':self.payload()['text']})
        reads = [url for url,body,_ in self.requests if body is None]
        self.assertTrue(any(urlsplit(url).path.endswith('/111_222') for url in reads))
        self.assertTrue(any(urlsplit(url).path.endswith('/111_222/comments') for url in reads))

    def test_page_monitored_comment_cannot_publish_under_another_pages_post(self):
        self.feed_comment_fixture()
        self.parent_owner = '999'
        result = self.send()
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(self.writes(), [])

    def test_page_monitored_comment_requires_exact_live_membership_and_unchanged_text(self):
        self.feed_comment_fixture()
        original = self.api
        def different_comment(url, token, payload=None, **kwargs):
            if urlsplit(url).path.endswith('/111_222/comments'):
                return {'data':[{'id':'888','message':self.source_text,'can_comment':True,'from':{'id':'999'}}]}
            return original(url,token,payload=payload,**kwargs)
        self.net.side_effect = different_comment
        result = self.send()
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(self.writes(), [])
        self.net.side_effect = self.api
        self.source_text = 'Changed fixture customer text after the saved assessment.'
        result = self.send(key='fixture-updated-comment')
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(self.writes(), [])

    def test_page_monitored_comment_without_parent_does_not_fall_back_to_post_publication(self):
        self.feed_comment_fixture()
        self.change(parent_source_id=None)
        with self.assertRaises(ValueError):
            self.send()
        self.assertEqual(self.writes(), [])

    def test_single_facebook_comment_source_fallback_requires_exact_live_membership(self):
        self.case = self.seed('FACEBOOK', comment=True);self.source_text = self.case['description']
        self.change(parent_source_id=None)
        original = self.api
        def different_comment(url, token, payload=None, **kw):
            if '/111_222/comments?' in url: return {'data': [{'id': '999', 'message': self.source_text, 'can_comment': True}]}
            return original(url, token, payload=payload, **kw)
        self.net.side_effect = different_comment
        result = self.send()
        self.assertEqual(result['status'], 'FAILED');self.assertEqual(self.writes(), [])
        self.net.side_effect = self.api
        result = self.send(key='fixture-request-02')
        self.assertEqual(result['status'], 'POSTED')
        self.assertTrue(self.writes()[0][0].endswith('/777/comments'))

    def test_user_profile_token_cannot_be_used_as_a_facebook_page(self):
        self.case = self.seed('FACEBOOK');self.source_text = self.case['description']
        original = self.api
        def user_profile(url, token, payload=None, **kw):
            if urlsplit(url).path.endswith('/me'): return {'id': '111', 'name': 'Synthetic personal profile'}
            return original(url, token, payload=payload, **kw)
        self.net.side_effect = user_profile
        result = self.send()
        self.assertEqual(result['status'], 'FAILED');self.assertEqual(self.writes(), [])

    def test_google_delegates_to_existing_official_publisher(self):
        self.case = self.seed('GOOGLE')
        with patch('belive.public_replies.google_replies.readiness', return_value={'ready': True, 'reason': 'Synthetic configured resource.'}), \
             patch('belive.public_replies.google_replies.publish', return_value={'status': 'POSTED', 'detail': 'Synthetic confirmed Google receipt.'}) as publish:
            result = self.send()
        self.assertEqual(result['status'], 'POSTED');self.assertEqual(result['target_label'], 'Google')
        publish.assert_called_once();self.net.assert_not_called()

    def test_google_maximum_request_key_is_hashed_before_legacy_delegation(self):
        self.case = self.seed('GOOGLE')
        with patch('belive.public_replies.google_replies.readiness', return_value={'ready': True, 'reason': 'Fixture'}), \
             patch('belive.public_replies.google_replies.publish', return_value={'status': 'POSTED', 'detail': 'Fixture'}) as publish:
            self.send(key='k' * 150)
        self.assertLessEqual(len(publish.call_args.args[3]), 150)

    def test_browser_google_case_has_no_official_reply_resource(self):
        self.case = self.seed('GOOGLE')
        self.change(source_id='google-browser-fixture')
        result = replies.eligibility(self.service, self.current())
        self.assertFalse(result['ready']);self.net.assert_not_called()

    def test_unapproved_stale_revision_or_cross_source_never_reaches_transport(self):
        for override in [dict(confirmed=False), dict(revision=999), dict(platform='FACEBOOK'), dict(source_id='999')]:
            with self.subTest(override=override):
                payload = {**self.payload(), **override}
                with self.assertRaises(ValueError): self.send(payload)
        self.net.assert_not_called()

    def test_closed_or_stale_preview_or_missing_provenance_blocks_send(self):
        for override in [dict(status='CLOSED'), dict(public_reply_preview={}), dict(source_versions=[]), dict(description='A changed source body.')]:
            with self.subTest(override=override):
                original = self.current();self.change(**override)
                with self.assertRaises(ValueError): self.send()
                self.change(**original)
        self.net.assert_not_called()

    def test_wrong_company_account_or_parent_owner_blocks_all_writes(self):
        for account, owner in [('999', '111'), ('111', '999')]:
            with self.subTest(account=account, owner=owner):
                self.account, self.parent_owner = account, owner
                result = self.send(key='fixture-owner-' + account + owner)
                self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(self.writes(), [])

    def test_live_source_edit_prevents_posting(self):
        self.source_text = 'The platform text changed after collection.'
        result = self.send()
        self.assertEqual(result['status'], 'FAILED');self.assertEqual(self.writes(), [])

    def test_case_revision_change_during_preflight_prevents_posting(self):
        self.profile_hook = lambda: self.change(revision=self.current()['revision'] + 1)
        result = self.send()
        self.assertEqual(result['status'], 'FAILED');self.assertEqual(self.writes(), [])

    def test_idempotent_replay_and_duplicate_button_do_not_publish_twice(self):
        payload = self.payload();first = self.send(payload)
        self.assertEqual(self.send(payload), first)
        self.assertEqual(self.send(key='fixture-request-02'), first)
        self.assertEqual(len(self.writes()), 2)
        with self.assertRaisesRegex(ValueError, 'Idempotency mismatch'):
            self.send({**payload, 'text': 'Different approved wording.'})

    def test_concurrent_approval_during_preflight_cannot_create_a_second_send(self):
        blocked = []
        def concurrent_approval():
            self.profile_hook = None
            try: self.send(key='fixture-concurrent-request')
            except ValueError: blocked.append(True)
        self.profile_hook = concurrent_approval
        result = self.send()
        self.assertEqual(result['status'], 'POSTED');self.assertEqual(blocked, [True])
        self.assertEqual(len(self.writes()), 2)

    def test_unknown_write_is_never_retried_by_same_or_new_request(self):
        self.fail_write = TimeoutError('Synthetic timeout; no actual API request.')
        payload = self.payload();first = self.send(payload)
        self.assertEqual(first['status'], 'UNKNOWN')
        self.assertEqual(self.send(payload), first)
        with self.assertRaisesRegex(ValueError, 'unconfirmed'): self.send(key='fixture-request-02')
        self.assertEqual(len(self.writes()), 1)

    def test_unknown_publish_retains_container_and_never_republishes(self):
        original = self.api
        def timeout(url, token, payload=None, **kw):
            if url.endswith('/threads_publish'):
                self.requests.append((url, payload, 'POST'));raise TimeoutError('Synthetic timeout')
            return original(url, token, payload=payload, **kw)
        self.net.side_effect = timeout
        first = self.send()
        self.assertEqual(first['status'], 'UNKNOWN');self.assertEqual(first['container_id'], '444')
        with self.assertRaisesRegex(ValueError, 'unconfirmed'): self.send(key='fixture-request-02')
        self.assertEqual(sum(x[0].endswith('/threads_publish') for x in self.writes()), 1)

    def test_in_progress_container_is_saved_and_resumed_without_recreation(self):
        self.statuses = ['IN_PROGRESS', 'IN_PROGRESS', 'IN_PROGRESS']
        first = self.send();self.assertEqual(first['status'], 'PENDING')
        self.assertEqual(first['stage'], 'WAIT_CONTAINER')
        self.statuses = ['FINISHED']
        second = self.send(key='fixture-request-02')
        self.assertEqual(second['status'], 'POSTED')
        self.assertEqual(sum(x[0].endswith('/threads') for x in self.writes()), 1)
        self.assertEqual(sum(x[0].endswith('/threads_publish') for x in self.writes()), 1)

    def test_pending_key_cannot_resume_after_reviewed_inputs_change(self):
        self.statuses = ['IN_PROGRESS']
        self.send()
        case = self.current();case['title'] = 'Updated fixture source label'
        case['public_reply_preview']['input_fingerprint'] = public_preview.fingerprint(public_preview.context(case, []))
        self.change(**case)
        before = len(self.requests)
        with self.assertRaisesRegex(ValueError, 'Idempotency mismatch'):
            self.send()
        self.assertEqual(len(self.requests), before)

    def test_interrupted_unpublished_container_status_check_resumes_same_container(self):
        self.statuses = ['IN_PROGRESS']
        first = self.send()
        with self.service.store.connect() as db:
            case = self.service.store.get(db, 'case', self.case['id'])
            case['public_reply']['stage'] = 'CHECK_CONTAINER'
            self.service.store.put(db, 'case', case)
            attempt = self.service.store.get(db, 'public_reply_attempt', first['attempt_id'])
            attempt['result']['stage'] = 'CHECK_CONTAINER'
            self.service.store.put(db, 'public_reply_attempt', attempt)
        self.statuses = ['FINISHED']
        result = self.send(key='fixture-request-02')
        self.assertEqual(result['status'], 'POSTED')
        self.assertEqual(sum(x[0].endswith('/threads') for x in self.writes()), 1)

    def test_new_approval_supersedes_old_unposted_container_without_reviving_old_key(self):
        self.statuses = ['IN_PROGRESS']
        old_payload = self.payload();first = self.send(old_payload)
        self.assertEqual(first['status'], 'PENDING')
        self.statuses = ['FINISHED']
        second = self.send({**self.payload(), 'text': 'New explicitly reviewed fixture wording.'}, key='fixture-request-02')
        self.assertEqual(second['status'], 'POSTED')
        count = len(self.requests)
        old = self.send(old_payload)
        self.assertEqual(old['status'], 'FAILED');self.assertEqual(old['stage'], 'SUPERSEDED_BEFORE_PUBLISH')
        self.assertEqual(len(self.requests), count)

    def test_unexpected_published_container_state_is_not_published_again(self):
        self.statuses = ['PUBLISHED']
        result = self.send()
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(sum(x[0].endswith('/threads_publish') for x in self.writes()), 0)

    def test_definite_publish_rejection_can_reuse_same_container_on_new_approval(self):
        original = self.api;reject = [True]
        def rejected(url, token, payload=None, **kw):
            if url.endswith('/threads_publish') and reject[0]:
                reject[0] = False
                self.requests.append((url, payload, 'POST'))
                raise HTTPError(url, 403, 'Synthetic rejected request', {}, io.BytesIO(b'{}'))
            return original(url, token, payload=payload, **kw)
        self.net.side_effect = rejected
        first = self.send();self.assertEqual(first['status'], 'FAILED');self.assertTrue(first['retryable_container'])
        second = self.send(key='fixture-request-02');self.assertEqual(second['status'], 'POSTED')
        self.assertEqual(sum(x[0].endswith('/threads') for x in self.writes()), 1)

    def test_long_threads_reply_is_rejected_without_truncation_or_network(self):
        with self.assertRaisesRegex(ValueError, '500'): self.send({**self.payload(), 'text': 'x' * 501})
        self.net.assert_not_called()

    def test_chinese_threads_reply_is_counted_as_characters_not_utf8_bytes(self):
        text = '谢谢反馈。' * 90
        self.assertGreater(len(text.encode('utf-8')), 500)
        result = self.send({**self.payload(), 'text': text})
        self.assertEqual(result['status'], 'POSTED')
        self.assertEqual(self.writes()[0][1]['text'], text)

    def test_provider_errors_do_not_store_raw_secrets(self):
        self.fail_write = TimeoutError('fixture-private-provider-message')
        result = self.send()
        self.assertNotIn('fixture-private-provider-message', str(result))
        self.assertNotIn('fixture-token-not-a-real-secret', str(result))

    def test_graph_error_object_is_a_rejection_not_a_success_receipt(self):
        original = self.api
        def graph_error(url, token, payload=None, **kw):
            if payload is not None:
                self.requests.append((url, payload, 'POST'))
                return {'error': {'message': 'fixture-private-provider-message', 'code': 200}}
            return original(url, token, payload=payload, **kw)
        self.net.side_effect = graph_error
        result = self.send()
        self.assertEqual(result['status'], 'FAILED')
        self.assertNotIn('fixture-private-provider-message', str(result))

    def test_expired_facebook_preflight_token_gives_safe_actionable_reason_without_post(self):
        self.case = self.seed('FACEBOOK')
        body = json.dumps({'error': {'code': 190, 'error_subcode': 463,
                           'message': 'fixture-private-provider-message fixture-token-not-a-real-secret'}}).encode()
        self.net.side_effect = HTTPError('https://graph.facebook.com/v27.0/me', 401,
                                        'Synthetic authentication failure', {}, io.BytesIO(body))
        result = self.send()
        self.assertEqual(result['status'], 'FAILED');self.assertEqual(self.writes(), [])
        self.net.assert_called_once()
        self.assertEqual(self.net.call_args.kwargs['method'], 'GET')
        self.assertIn('Facebook access token expired', result['detail'])
        self.assertIn('new Page access token in Connection settings', result['detail'])
        self.assertNotIn('fixture-private-provider-message', str(result))
        self.assertNotIn('fixture-token-not-a-real-secret', str(result))
        unclassified = HTTPError('https://graph.threads.com/v1.0/me', 401,
            'Synthetic authentication failure', {}, io.BytesIO(b'{"error":{"code":190}}'))
        self.assertNotIn('expired', replies._authentication_detail('THREADS', unclassified))

    def test_facebook_post_permission_errors_explain_required_grant_without_retry_or_raw_secrets(self):
        self.case = self.seed('FACEBOOK');self.source_text = self.case['description']
        original = self.api
        for http_code in [400, 403]:
            with self.subTest(http_code=http_code):
                def permission_error(url, token, payload=None, **kw):
                    if payload is not None:
                        self.requests.append((url, payload, 'POST'))
                        body = json.dumps({'error': {'code': 200,
                            'message': 'fixture-private-provider-message fixture-token-not-a-real-secret'}}).encode()
                        raise HTTPError(url, http_code, 'Synthetic permission failure', {}, io.BytesIO(body))
                    return original(url, token, payload=payload, **kw)
                self.net.side_effect = permission_error
                payload = self.payload();key = 'fixture-permission-' + str(http_code)
                before = len(self.writes())
                result = self.send(payload, key=key)
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual(result['stage'], 'POST_COMMENT')
                self.assertIn('pages_manage_engagement', result['detail'])
                self.assertIn('MODERATE Page task', result['detail'])
                self.assertNotIn('fixture-private-provider-message', str(result))
                self.assertNotIn('fixture-token-not-a-real-secret', str(result))
                self.assertEqual(len(self.writes()), before + 1)
                count = self.net.call_count
                self.assertEqual(self.send(payload, key=key), result)
                self.assertEqual(self.net.call_count, count)

    def test_facebook_preflight_permission_error_names_read_access_and_never_posts(self):
        self.case = self.seed('FACEBOOK')
        body = json.dumps({'error': {'code': 10,
            'message': 'fixture-private-provider-message fixture-token-not-a-real-secret'}}).encode()
        self.net.side_effect = HTTPError('https://graph.facebook.com/v27.0/me', 403,
            'Synthetic read permission failure', {}, io.BytesIO(body))
        payload = self.payload();result = self.send(payload)
        self.assertEqual(result['status'], 'FAILED');self.assertEqual(result['stage'], 'PREFLIGHT')
        self.net.assert_called_once();self.assertEqual(self.net.call_args.kwargs['method'], 'GET')
        self.assertIn('pages_read_engagement', result['detail'])
        self.assertIn('pages_read_user_content', result['detail'])
        self.assertIn('selected Page/source', result['detail'])
        self.assertNotIn('pages_manage_engagement', result['detail'])
        self.assertNotIn('fixture-private-provider-message', str(result))
        self.assertNotIn('fixture-token-not-a-real-secret', str(result))
        self.assertEqual(self.send(payload), result);self.net.assert_called_once()


if __name__ == '__main__':
    unittest.main()
