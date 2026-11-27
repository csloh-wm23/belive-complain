"""Read-only Facebook Page monitoring fixtures; no real accounts or platform writes."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from belive import connectors
from belive.service import Service
from belive.store import now


def post(post_id='111_222', owner='111', **extra):
    return {'id':post_id, 'from':{'id':owner},
            'permalink_url':'https://www.facebook.com/111/posts/' + post_id.split('_')[-1],
            'created_time':now(), **extra}


def comment(comment_id='777', author='999', **extra):
    value = {'id':comment_id, 'message':'TEST: The shared washing machine has been broken for five days.',
             'created_time':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
             'permalink_url':'https://www.facebook.com/111/posts/222?comment_id=' + comment_id}
    if author is not None:
        value['from'] = {'id':author}
    value.update(extra)
    return value


class FacebookCommentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ai = Mock()
        self.service = Service(Path(self.tmp.name) / 'test.db', self.ai)
        self.source = self.service.command('source', {
            'platform':'FACEBOOK','resource':'111/feed','authorised':True,
        }, 'fixture-facebook-page')

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, posts, comments, parent=None):
        def read(url, token='', payload=None, method=None, **kwargs):
            self.assertIsNone(payload, 'Collection must never send a platform write')
            self.assertNotEqual(method, 'POST')
            parsed = urlsplit(url)
            self.assertEqual(parsed.netloc, 'graph.facebook.com')
            self.assertEqual(parsed.scheme, 'https')
            self.assertTrue(parsed.path.startswith('/v27.0/'))
            self.assertEqual(token, 'fixture-facebook-token')
            path = parsed.path.removeprefix('/v27.0/')
            query = parse_qs(parsed.query)
            if path == '111/posts':
                self.assertEqual(query.get('limit'), ['25'])
                self.assertIn('since', query)
                return {'data':posts, 'paging':{'next':'https://evil.example/do-not-follow'}}
            if path.endswith('/comments'):
                self.assertEqual(query.get('limit'), ['25'])
                self.assertEqual(query.get('filter'), ['toplevel'])
                self.assertEqual(query.get('order'), ['reverse_chronological'])
                value = comments.get(path.removesuffix('/comments'), [])
                if isinstance(value, Exception):
                    raise value
                return {'data':value, 'paging':{'next':'https://evil.example/do-not-follow'}}
            return parent or post(path)
        return read

    def patched(self, posts, comments, parent=None):
        return patch.object(connectors, 'request_json', side_effect=self.transport(posts, comments, parent))

    def settings(self):
        return patch.object(connectors, 'get_value', side_effect=lambda name, *args, **kwargs:
                            'v27.0' if name=='BELIVE_FACEBOOK_VERSION' else 'fixture-facebook-token')

    def scan(self, posts, comments, parent=None):
        with self.settings(), self.patched(posts, comments, parent) as read:
            result = connectors.scan(self.service, self.source['id'])
        return result, read

    def current(self):
        with self.service.store.connect() as db:
            return self.service.store.all(db, 'case'), self.service.store.get(db, 'source', self.source['id'])

    def test_facebook_lookback_defaults_and_rejects_invalid_days(self):
        payload = {'platform':'FACEBOOK','resource':'111/feed','authorised':True}
        self.assertEqual(connectors.validate_source(payload)['lookback_days'], 30)
        for days in (1,7,30,365):
            with self.subTest(days=days):
                self.assertEqual(connectors.validate_source(dict(payload,lookback_days=days))['lookback_days'], days)
        for days in (0,366,-1,True,False,'30',30.5,None):
            with self.subTest(days=days), self.assertRaises(ValueError):
                connectors.validate_source(dict(payload,lookback_days=days))

    def test_facebook_page_and_post_resources_have_distinct_identifier_shapes(self):
        payload = {'platform':'FACEBOOK','authorised':True}
        for resource in ('123/feed','123_456/comments','123456/comments'):
            with self.subTest(resource=resource):
                self.assertEqual(connectors.validate_source(dict(payload,resource=resource))['resource'], resource)
        for resource in ('123_456/feed','me/feed','@fixture/feed','123/posts',
                         'https://www.facebook.com/123/feed','123/feed?limit=25'):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                connectors.validate_source(dict(payload,resource=resource))

    def test_resaving_same_page_changes_lookback_without_duplicating_source(self):
        updated = self.service.command('source', {
            'platform':'FACEBOOK','resource':'111/feed','authorised':True,'lookback_days':7,
        }, 'fixture-facebook-lookback-change')
        self.assertEqual(updated['id'], self.source['id'])
        self.assertEqual(updated['lookback_days'], 7)
        with self.service.store.connect() as db:
            self.assertEqual(len(self.service.store.all(db,'source')), 1)
            self.assertEqual(self.service.store.get(db,'source',self.source['id'])['lookback_days'], 7)

    def test_custom_lookback_controls_request_and_defensive_post_filter(self):
        current_time = datetime.now(timezone.utc)
        posts = [post('111_'+str(100+i), created_time=(current_time-timedelta(days=age)).isoformat())
                 for i,age in enumerate((2,20,200,400))]
        comments = {item['id']:[comment(str(1000+i))] for i,item in enumerate(posts)}
        for days, expected in ((7,{'1000'}),(30,{'1000','1001'}),(365,{'1000','1001','1002'})):
            with self.subTest(days=days), self.settings(), self.patched(posts, comments) as read:
                rows = connectors.read_source(dict(self.source,lookback_days=days))
                self.assertEqual({row['id'] for row in rows}, expected)
                since = parse_qs(urlsplit(read.call_args_list[0].args[0]).query)['since'][0]
                try:
                    cutoff = datetime.fromtimestamp(float(since), timezone.utc)
                except ValueError:
                    cutoff = datetime.fromisoformat(since.replace('Z','+00:00'))
                expected_cutoff = current_time-timedelta(days=days)
                self.assertLess(abs((cutoff-expected_cutoff).total_seconds()), 30)

    def test_existing_page_source_without_lookback_uses_30_day_default(self):
        source = dict(self.source)
        source.pop('lookback_days', None)
        current_time = datetime.now(timezone.utc)
        posts = [post(),post('111_333',created_time=(current_time-timedelta(days=31)).isoformat())]
        with self.settings(), self.patched(posts, {'111_222':[comment()],'111_333':[comment('778')]}) as read:
            rows = connectors.read_source(source)
        self.assertEqual([row['id'] for row in rows], ['777'])
        self.assertEqual(read.call_count, 2)

    def test_page_announcements_are_discovery_parents_not_complaint_cases(self):
        self.scan([post(message='We have a washing-machine maintenance announcement.')], {'111_222':[]})
        cases, source = self.current()
        self.assertEqual(cases, [])
        self.assertEqual(source['status'], 'COMPLETED')
        self.ai.analyse.assert_not_called()

    def test_customer_comments_are_collected_under_page_owned_posts_only(self):
        posts = [post(), post('888_333',owner='888'), {'id':'111_444'}]
        with self.settings(), self.patched(posts, {'111_222':[comment()]}) as read:
            rows = connectors.read_source(self.source)
        self.assertEqual([row['id'] for row in rows], ['777'])
        self.assertEqual(read.call_count, 2)
        self.assertEqual(rows[0]['parent_source_id'], '111_222')
        self.assertEqual(rows[0]['public_source_kind'], 'FACEBOOK_COMMENT')

    def test_page_posts_endpoint_allows_omitted_author_but_never_explicit_foreign_author(self):
        parent = post()
        parent.pop('from')
        with self.settings(), self.patched([parent,post('888_333',owner='888')], {'111_222':[comment()]}) as read:
            rows = connectors.read_source(self.source)
        self.assertEqual([row['id'] for row in rows], ['777'])
        self.assertEqual(read.call_count, 2)

    def test_default_page_monitoring_reads_only_valid_recent_posts(self):
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        posts = [post(),post('111_333',created_time=old),post('111_444',created_time='not-a-date'),
                 post('111_555',created_time=future)]
        missing = post('111_666')
        missing.pop('created_time')
        posts.append(missing)
        with self.settings(), self.patched(posts, {'111_222':[comment()]}) as read:
            rows = connectors.read_source(self.source)
        self.assertEqual([row['id'] for row in rows], ['777'])
        self.assertEqual(read.call_count, 2)
        post_request = urlsplit(read.call_args_list[0].args[0])
        self.assertEqual(post_request.path, '/v27.0/111/posts')
        self.assertIn('since', parse_qs(post_request.query))

    def test_page_authored_comments_never_become_customer_cases(self):
        self.scan([post()], {'111_222':[
            comment('777',author='111',message='We have received your washing machine report.'),
            comment('778',author='999'),
        ]})
        cases, _ = self.current()
        self.assertEqual([case['source_id'] for case in cases], ['778'])

    def test_comment_time_window_applies_even_under_a_recent_or_explicit_parent(self):
        items = [comment('777',created_time=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()),
                 comment('778',created_time=(datetime.now(timezone.utc)-timedelta(days=20)).isoformat()),
                 comment('779',created_time=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()),
                 comment('780',created_time='invalid')]
        missing = comment('781')
        missing.pop('created_time')
        items.append(missing)
        for resource in ('111/feed','111_222/comments'):
            with self.subTest(resource=resource), self.settings(), self.patched([post()],{'111_222':items}):
                rows = connectors.read_source(dict(self.source,resource=resource,lookback_days=7))
                self.assertEqual([row['id'] for row in rows],['777'])

    def test_confirmed_published_receipt_ids_are_excluded_even_when_author_is_missing(self):
        previous = self.service.command('intake', {
            'platform':'FACEBOOK','source_id':'700','title':'Earlier fixture case',
            'description':'TEST: An earlier fictional tenant complaint.',
        }, 'fixture-earlier-case')
        with self.service.store.connect() as db:
            previous['public_reply'] = {'status':'POSTED','receipt_id':'790'}
            self.service.store.put(db, 'case', previous)
            self.service.store.put(db, 'public_reply_attempt', {
                'id':'fixture-confirmed-attempt','case_id':previous['id'],
                'result':{'platform':'FACEBOOK','status':'POSTED','receipt_id':'791'},
            })
            self.service.store.put(db, 'public_reply_attempt', {
                'id':'fixture-unconfirmed-attempt','case_id':previous['id'],
                'result':{'platform':'FACEBOOK','status':'UNKNOWN','receipt_id':'792'},
            })
        self.scan([post()], {'111_222':[comment('790',None), comment('791',None),
                                      comment('792','999'), comment('7909','999')]})
        cases, _ = self.current()
        self.assertEqual({case['source_id'] for case in cases}, {'700','792','7909'})

    def test_repeated_reads_do_not_duplicate_and_new_posts_are_discovered(self):
        posts = [post()]
        comments = {'111_222':[comment()]}
        first, _ = self.scan(posts, comments)
        self.scan(posts, comments)
        cases, source = self.current()
        self.assertEqual(len(cases), 1)
        self.assertEqual(source['last_new_count'], 0)
        posts.insert(0, post('111_333'))
        comments['111_333'] = [comment('779',message='TEST: The shared refrigerator is not cooling.',
                                       permalink_url='https://www.facebook.com/111/posts/333?comment_id=779')]
        future, _ = self.scan(posts, comments)
        cases, source = self.current()
        self.assertEqual(len(cases), 2)
        self.assertEqual(len(future), 1)
        self.assertNotEqual(first, future)
        self.assertEqual(source['last_new_count'], 1)
        self.assertEqual({case['source_id'] for case in cases}, {'777','779'})

    def test_changed_comment_keeps_original_evidence_and_adds_an_immutable_version(self):
        original = comment()
        self.scan([post()], {'111_222':[original]})
        changed = dict(original, message='TEST: The washing machine is still broken after seven days.')
        self.scan([post()], {'111_222':[changed]})
        with self.service.store.connect() as db:
            rows = [json.loads(row[0]) for row in db.execute(
                'SELECT body FROM sources WHERE platform=? AND source_id=?', ('FACEBOOK','777'))]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row['text'] for row in rows}, {original['message'],changed['message']})

    def test_contact_redaction_remains_duplicate_safe(self):
        item = comment(message='TEST: Please contact me on 0123456789 or tenant@example.test about the broken washer.')
        self.scan([post()], {'111_222':[item]})
        self.scan([post()], {'111_222':[item]})
        cases, source = self.current()
        self.assertEqual(len(cases), 1)
        self.assertNotIn('0123456789', cases[0]['description'])
        self.assertNotIn('tenant@example.test', cases[0]['description'])
        self.assertIn('[email removed]', cases[0]['description'])
        self.assertIn('[number removed]', cases[0]['description'])
        self.assertEqual(source['last_new_count'], 0)

    def test_new_comments_behind_seen_comments_are_not_starved_by_the_import_cap(self):
        seen = [comment(str(1000+i)) for i in range(25)]
        self.scan([post()], {'111_222':seen})
        posts = [post(), post('111_333')]
        result, _ = self.scan(posts, {'111_222':seen, '111_333':[comment('2000')]})
        cases, source = self.current()
        self.assertEqual(len(result), 1)
        self.assertEqual(len(cases), 26)
        self.assertEqual(source['last_new_count'], 1)

    def test_import_cap_defers_unseen_comments_to_later_scans(self):
        posts = [post(),post('111_333')]
        comments = {'111_222':[comment(str(1000+i)) for i in range(25)],
                    '111_333':[comment(str(2000+i)) for i in range(5)]}
        first, _ = self.scan(posts, comments)
        self.assertEqual(len(first), 25)
        cases, source = self.current()
        self.assertEqual(len(cases), 25)
        self.assertEqual(source['last_seen_count'], 30)
        self.assertEqual(source['last_deferred_count'], 5)
        self.assertEqual(source['last_new_count'], 25)
        second, _ = self.scan(posts, comments)
        cases, source = self.current()
        self.assertEqual(len(second), 5)
        self.assertEqual(len(cases), 30)
        self.assertEqual(source['last_deferred_count'], 0)

    def test_exact_comment_permalink_and_parent_metadata_are_preserved(self):
        url = 'https://www.facebook.com/111/posts/222?comment_id=777&reply_comment_id=778'
        item = comment(permalink_url=url)
        self.scan([post()], {'111_222':[item]})
        cases, _ = self.current()
        case = cases[0]
        self.assertEqual(case['source_id'], '777')
        self.assertEqual(case['public_url'], url)
        self.assertEqual(case['parent_source_id'], '111_222')
        self.assertEqual(case['parent_public_url'], 'https://www.facebook.com/111/posts/222')
        self.assertEqual(case['source_created_at'], item['created_time'])
        self.assertEqual(case['public_source_kind'], 'FACEBOOK_COMMENT')

    def test_missing_or_unsafe_comment_permalink_is_not_guessed(self):
        for url in ('', 'http://www.facebook.com/111/posts/222?comment_id=777',
                    'https://facebook.com.evil.example/111/posts/222?comment_id=777',
                    'https://user:password@www.facebook.com/111/posts/222?comment_id=777',
                    'javascript:alert(1)'):
            with self.subTest(url=url), self.settings(), self.patched([post()], {'111_222':[comment(permalink_url=url)]}):
                rows = connectors.read_source(self.source)
                self.assertEqual(len(rows), 1)
                self.assertFalse(rows[0].get('public_url'))
                self.assertEqual(rows[0]['parent_public_url'], 'https://www.facebook.com/111/posts/222')

    def test_permalink_keeps_comment_target_but_removes_tracking_and_credentials(self):
        url = ('https://www.facebook.com/permalink.php?story_fbid=222&id=111&comment_id=777'
               '&reply_comment_id=778&fbclid=fixture-tracking&access_token=fixture-secret#tracking')
        with self.settings(), self.patched([post()], {'111_222':[comment(permalink_url=url)]}):
            rows = connectors.read_source(self.source)
        parsed = urlsplit(rows[0]['public_url'])
        self.assertEqual(parsed.path, '/permalink.php')
        self.assertEqual(parse_qs(parsed.query), {
            'story_fbid':['222'],'id':['111'],'comment_id':['777'],'reply_comment_id':['778'],
        })
        self.assertEqual(parsed.fragment, '')
        self.assertNotIn('fixture-secret', rows[0]['public_url'])

    def test_legacy_page_post_case_is_not_relabelled_or_replaced_by_comment_collection(self):
        legacy = self.service.command('intake', {
            'platform':'FACEBOOK','source_id':'111_222','title':'Legacy fixture company post',
            'description':'TEST: A previously imported fictional company announcement.',
        }, 'fixture-legacy-post')
        legacy.update(public_source_kind='FACEBOOK_PAGE_POST', public_url='https://www.facebook.com/111/posts/222',
                      analysis={'summary':'Earlier saved assessment.'}, draft='Earlier saved staff draft.')
        with self.service.store.connect() as db:
            self.service.store.put(db,'case',legacy)
        original = copy.deepcopy(legacy)
        self.scan([post()], {'111_222':[comment()]})
        cases, _ = self.current()
        self.assertEqual(len(cases), 2)
        self.assertEqual(next(case for case in cases if case['id']==legacy['id']), original)
        self.assertEqual(next(case for case in cases if case['source_id']=='777')['public_source_kind'], 'FACEBOOK_COMMENT')

    def test_missing_metadata_is_enriched_without_changing_case_or_ai_results(self):
        self.scan([post()], {'111_222':[comment(permalink_url='')]})
        cases, _ = self.current()
        case = cases[0]
        case.update(status='HUMAN_REVIEW', owner='Fixture operator', draft='Reviewed fixture draft.',
                    analysis={'report_type':'COMPLAINT','summary':'Saved fixture AI assessment.'},
                    public_reply_preview={'text':'Saved public preview.'},
                    public_reply={'status':'POSTED','receipt_id':'111_999','text':'Previously approved wording.'})
        with self.service.store.connect() as db:
            self.service.store.put(db, 'case', case)
            versions_before = [tuple(row) for row in db.execute('SELECT * FROM sources')]
        before = copy.deepcopy(case)
        self.scan([post()], {'111_222':[comment()]})
        cases, source = self.current()
        self.assertEqual(len(cases), 1)
        after = cases[0]
        self.assertEqual(after['public_url'], comment()['permalink_url'])
        for key in ('id','source_id','description','source_versions','status','owner','draft','analysis',
                    'public_reply','public_reply_preview'):
            self.assertEqual(after[key], before[key], key)
        with self.service.store.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sources')], versions_before)
        self.assertEqual(source['last_new_count'], 0)
        self.ai.analyse.assert_not_called()

    def test_selected_single_post_comments_still_work(self):
        self.source = self.service.command('source', {
            'platform':'FACEBOOK','resource':'111_222/comments','authorised':True,
        }, 'fixture-facebook-post')
        self.scan([], {'111_222':[comment(),comment('778','111')]}, parent=post())
        cases, _ = self.current()
        self.assertEqual([case['source_id'] for case in cases], ['777'])
        self.assertEqual(cases[0]['parent_source_id'], '111_222')
        self.assertEqual(cases[0]['public_source_kind'], 'FACEBOOK_COMMENT')

    def test_explicit_selected_old_post_is_not_hidden_by_page_discovery_lookback(self):
        self.source = self.service.command('source', {
            'platform':'FACEBOOK','resource':'111_222/comments','authorised':True,'lookback_days':1,
        }, 'fixture-explicit-old-post')
        old = (datetime.now(timezone.utc)-timedelta(days=400)).isoformat()
        self.scan([], {'111_222':[comment()]}, parent=post(created_time=old))
        cases, source = self.current()
        self.assertEqual([case['source_id'] for case in cases], ['777'])
        self.assertEqual(source['status'], 'COMPLETED')

    def test_page_and_comment_pages_are_bounded_without_following_next_links(self):
        posts = [post('111_' + str(100+i)) for i in range(26)]
        comments = {item['id']:[comment(str(10000+i*100+j)) for j in range(26)]
                    for i,item in enumerate(posts)}
        with self.settings(), self.patched(posts, comments) as read:
            rows = connectors.read_source(self.source)
        self.assertEqual(read.call_count, 26)
        self.assertEqual(len(rows), 625)

    def test_partial_comment_read_failure_does_not_claim_success(self):
        result, _ = self.scan([post(),post('111_333')], {
            '111_222':[comment()], '111_333':RuntimeError('Fixture platform read failed'),
        })
        cases, source = self.current()
        self.assertEqual(result, [])
        self.assertEqual(cases, [])
        self.assertEqual(source['status'], 'FAILED')
        self.assertEqual(source['error'], 'CONNECTOR_READ_FAILED')


if __name__ == '__main__':
    unittest.main()
