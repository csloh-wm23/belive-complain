"""Connected Threads account monitoring: bounded reads, future posts and honest intake."""
import json
import tempfile
import threading
import unittest
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from belive import connectors
from belive.service import Service
from server import Tasks, make_handler


def reply(reply_id, text='TEST: The shared washing machine has been broken for five days.', **extra):
    return dict(id=str(reply_id), text=text,
                permalink='https://www.threads.com/@fixture/post/reply' + str(reply_id),
                timestamp='2026-11-26T12:00:00+0000', **extra)


class ThreadsAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.tmp.name) / 'test.db', Mock())
        self.source = self.service.command('source', {
            'platform':'THREADS', 'resource':'123/threads', 'account_name':'fixture',
            'authorised':True,
        }, 'fixture-account-source')

    def tearDown(self):
        self.tmp.cleanup()

    def source_record(self):
        return self.source

    def transport(self, posts, replies):
        def read(url, token='', *args, **kwargs):
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme, 'https')
            self.assertEqual(parsed.netloc, 'graph.threads.com')
            self.assertEqual(token, 'fixture-token')
            self.assertFalse(args)
            self.assertNotIn('payload', kwargs)
            self.assertNotEqual(kwargs.get('method'), 'POST')
            self.assertEqual(parse_qs(parsed.query).get('limit'), ['25'])
            if parsed.path == '/v1.0/123/threads':
                return {'data':posts, 'paging':{'next':'https://evil.example/never-follow'}}
            parent = parsed.path.removeprefix('/v1.0/').removesuffix('/replies')
            self.assertTrue(parent.isdigit(), url)
            value = replies.get(parent, [])
            if isinstance(value, Exception):
                raise value
            return {'data':value, 'paging':{'next':'https://evil.example/never-follow'}}
        return read

    def scan(self, posts, replies):
        source = self.source_record()
        with patch.object(connectors, 'get_value', return_value='fixture-token'), \
                patch.object(connectors, 'request_json', side_effect=self.transport(posts, replies)) as request:
            result = connectors.scan(self.service, source['id'])
        return result, request

    def snapshot(self):
        with self.service.store.connect() as db:
            return (self.service.store.all(db, 'case'),
                    self.service.store.get(db, 'source', self.source_record()['id']))

    def test_validation_accepts_account_and_preserves_single_post(self):
        for resource in ('123/threads', '123/replies'):
            saved = connectors.validate_source({'platform':'THREADS','resource':resource,'authorised':True})
            self.assertEqual(saved['resource'], resource)
        for resource in ('me/threads', '@fixture/threads', 'https://threads.com/@fixture',
                         '123/threads?access_token=secret', '123/feed', '123/../456/replies'):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                connectors.validate_source({'platform':'THREADS','resource':resource,'authorised':True})
        with self.assertRaises(ValueError):
            connectors.validate_source({'platform':'THREADS','resource':'123/threads','authorised':False})

    def test_connected_account_is_resolved_from_saved_token_and_pinned(self):
        payload = {'platform':'THREADS','resource':'me/threads','authorised':True,'enabled':True}
        with patch.object(connectors, 'get_value', return_value='fixture-token'), \
                patch.object(connectors, 'request_json', return_value={'id':'123','username':'fixture'}) as request:
            resolved = connectors.resolve_threads_account(payload)
        self.assertEqual(resolved['resource'], '123/threads')
        self.assertEqual(resolved['account_name'], 'fixture')
        self.assertTrue(resolved['authorised'])
        self.assertEqual(payload['resource'], 'me/threads')
        parsed = urlsplit(request.call_args.args[0])
        self.assertEqual((parsed.netloc, parsed.path), ('graph.threads.com','/v1.0/me'))
        self.assertEqual(set(parse_qs(parsed.query)['fields'][0].split(',')), {'id','username'})
        self.assertEqual(request.call_args.args[1], 'fixture-token')

    def test_account_resolution_requires_authorisation_before_read(self):
        with patch.object(connectors, 'request_json') as request:
            with self.assertRaises(ValueError):
                connectors.resolve_threads_account({'platform':'THREADS','resource':'me/threads','authorised':False})
        request.assert_not_called()

    def test_reader_collects_replies_only_from_selected_accounts_posts(self):
        posts = [{'id':'400','text':'A parent announcement, not a tenant complaint.'}, {'id':'500'}]
        data = {'400':[reply(401)], '500':[reply(501, 'TEST: The shared air conditioner is leaking water.') ]}
        with patch.object(connectors, 'get_value', return_value='fixture-token'), \
                patch.object(connectors, 'request_json', side_effect=self.transport(posts, data)) as request:
            rows = connectors.read_source(self.source_record())
        self.assertEqual({row['id'] for row in rows}, {'401','501'})
        self.assertEqual(request.call_count, 3)
        self.assertFalse(any(row['id'] in {'400','500'} for row in rows))

    def test_future_posts_are_discovered_and_unchanged_replies_do_not_duplicate(self):
        posts = [{'id':'400'}]
        replies = {'400':[reply(401)]}
        first, _ = self.scan(posts, replies)
        second, _ = self.scan(posts, replies)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        cases, source = self.snapshot()
        self.assertEqual(len(cases), 1)
        self.assertEqual(source['last_new_count'], 0)
        posts.insert(0, {'id':'500'})
        replies['500'] = [reply(501, 'TEST: The shared refrigerator has stopped cooling.')]
        future, _ = self.scan(posts, replies)
        self.assertEqual(len(future), 1)
        self.assertNotEqual(first, future)
        cases, source = self.snapshot()
        self.assertEqual(len(cases), 2)
        self.assertEqual(source['status'], 'COMPLETED')
        self.assertEqual(source['last_new_count'], 1)
        self.assertEqual(source['last_seen_count'], 2)
        self.assertEqual({case['source_id'] for case in cases}, {'401','501'})

    def test_reply_provenance_is_preserved_without_replacing_stable_id(self):
        item = reply(401)
        self.scan([{'id':'400'}], {'400':[item]})
        cases, _ = self.snapshot()
        case = cases[0]
        self.assertEqual(case['source_id'], '401')
        self.assertEqual(case['public_url'], item['permalink'])
        self.assertEqual(case['source_created_at'], item['timestamp'])
        self.assertEqual(case['parent_source_id'], '400')
        self.assertEqual(case['platform'], 'THREADS')
        self.assertFalse(self.service.ai.analyse.called)
        with self.service.store.connect() as db:
            self.assertFalse(self.service.store.all(db, 'outbox'))

    def test_changed_reply_retains_an_immutable_version_and_can_be_reassessed(self):
        item = reply(401)
        first, _ = self.scan([{'id':'400'}], {'400':[item]})
        changed = dict(item, text='TEST: The washing machine is still broken after seven days and three reports.')
        second, _ = self.scan([{'id':'400'}], {'400':[changed]})
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first, second)
        with self.service.store.connect() as db:
            versions = [json.loads(row[0]) for row in db.execute('SELECT body FROM sources WHERE platform=? AND source_id=?', ('THREADS','401'))]
        self.assertEqual(len(versions), 2)
        self.assertEqual({version['text'] for version in versions}, {item['text'],changed['text']})

    def test_each_scan_imports_at_most_25_and_defers_remaining_unseen_replies(self):
        posts = [{'id':'400'}, {'id':'500'}]
        replies = {'400':[reply(4000 + i) for i in range(25)],
                   '500':[reply(5000 + i) for i in range(5)]}
        first, _ = self.scan(posts, replies)
        self.assertEqual(len(first), 25)
        cases, source = self.snapshot()
        self.assertEqual(len(cases), 25)
        self.assertEqual(source['last_deferred_count'], 5)
        self.assertEqual(source['last_seen_count'], 30)
        second, _ = self.scan(posts, replies)
        self.assertEqual(len(second), 5)
        cases, source = self.snapshot()
        self.assertEqual(len(cases), 30)
        self.assertEqual(source['last_deferred_count'], 0)
        self.assertEqual(self.scan(posts, replies)[0], [])

    def test_account_reader_bounds_post_and_reply_pages_and_never_follows_paging(self):
        posts = [{'id':str(400 + i)} for i in range(26)]
        replies = {str(400 + i):[reply((400+i)*100+j) for j in range(26)] for i in range(26)}
        with patch.object(connectors, 'get_value', return_value='fixture-token'), \
                patch.object(connectors, 'request_json', side_effect=self.transport(posts, replies)) as request:
            rows = connectors.read_source(self.source_record())
        self.assertEqual(request.call_count, 26)
        self.assertEqual(len(rows), 625)

    def test_partial_account_read_failure_is_not_reported_as_success(self):
        result, _ = self.scan([{'id':'400'}, {'id':'500'}], {
            '400':[reply(401)], '500':RuntimeError('Fixture transport failure'),
        })
        self.assertEqual(result, [])
        cases, source = self.snapshot()
        self.assertEqual(cases, [])
        self.assertEqual(source['status'], 'FAILED')
        self.assertEqual(source['error'], 'CONNECTOR_READ_FAILED')
        self.assertGreater(source['next_scan'], source['last_scan'])

    def test_malformed_success_payload_is_not_misreported_as_an_empty_account(self):
        source = self.source_record()
        for malformed in ({}, {'error':{'message':'Fixture API error'}}, {'data':{}}, {'data':None}):
            for stage in ('posts','replies'):
                with self.subTest(payload=malformed, stage=stage), \
                        patch.object(connectors, 'get_value', return_value='fixture-token'), \
                        patch.object(connectors, 'request_json', side_effect=(
                            [malformed] if stage=='posts' else [{'data':[{'id':'400'}]}, malformed])):
                    self.assertEqual(connectors.scan(self.service, source['id']), [])
                    cases, saved = self.snapshot()
                    self.assertEqual(cases, [])
                    self.assertEqual(saved['status'], 'FAILED')
                    self.assertEqual(saved['error'], 'CONNECTOR_READ_FAILED')

    def test_valid_empty_account_completes_without_creating_a_case(self):
        result, request = self.scan([], {})
        self.assertEqual(result, [])
        self.assertEqual(request.call_count, 1)
        cases, source = self.snapshot()
        self.assertEqual(cases, [])
        self.assertEqual(source['status'], 'COMPLETED')
        self.assertEqual(source['last_seen_count'], 0)


class ThreadsAccountHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.tmp.name) / 'test.db', Mock())
        self.tasks = Tasks(self.service)
        self.server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.service, self.tasks))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.cookie = ''
        self.csrf = self.call('/api/auth')[1]['csrf_token']
        status, _ = self.call('/api/setup', {
            'username':'threads-admin','name':'Fixture Threads Admin','password':'Threads-fixture-password-123',
        })
        self.assertEqual(status, 200)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def call(self, path, payload=None, key='fixture-threads-http-request'):
        headers = {'Content-Type':'application/json','Cookie':self.cookie,
                   'Idempotency-Key':key,'X-CSRF-Token':getattr(self,'csrf','')}
        request = Request(self.base + path,
                          data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            if response.headers.get('Set-Cookie'):
                cookies = SimpleCookie(self.cookie)
                for value in response.headers.get_all('Set-Cookie'):
                    cookies.load(value)
                self.cookie = '; '.join(name + '=' + value.value for name,value in cookies.items())
            return response.code, json.loads(response.read())

    def test_account_source_save_pins_account_and_reuses_source_on_retry_and_resave(self):
        payload = {'platform':'THREADS','resource':'me/threads','authorised':True,'enabled':True}
        with patch.object(connectors, 'get_value', return_value='fixture-token'), \
                patch.object(connectors, 'request_json', return_value={'id':'123','username':'fixture'}):
            status, first = self.call('/api/source', payload, 'fixture-first-source')
            self.assertEqual(status, 200, first)
            self.assertEqual(first['resource'], '123/threads')
            self.assertEqual(first['account_name'], 'fixture')
            status, repeated = self.call('/api/source', payload, 'fixture-first-source')
            self.assertEqual(status, 200, repeated)
            self.assertEqual(repeated['id'], first['id'])
            status, saved_again = self.call('/api/source', payload, 'fixture-resave-source')
            self.assertEqual(status, 200, saved_again)
            self.assertEqual(saved_again['id'], first['id'])
        with self.service.store.connect() as db:
            self.assertEqual(len(self.service.store.all(db,'source')), 1)

    def test_account_source_save_does_not_read_without_authorisation(self):
        with patch.object(connectors, 'request_json') as request:
            status, _ = self.call('/api/source', {
                'platform':'THREADS','resource':'me/threads','authorised':False,'enabled':True,
            })
        self.assertEqual(status, 400)
        request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
