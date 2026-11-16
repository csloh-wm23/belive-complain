"""Verify public source ingestion without sending requests to live platforms."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from belive import connectors
from belive.service import Service


class PublicConnectorTests(unittest.TestCase):
    def test_each_source_records_one_case_even_when_polled_twice(self):
        sources = [
            ('GOOGLE', 'accounts/123/locations/456', 'mybusiness.googleapis.com',
             {'reviews': [{'reviewId': 'test-review', 'comment': 'The Wi-Fi disconnects every evening.'}]}),
            ('FACEBOOK', '123_456/comments', 'graph.facebook.com',
             {'data': [{'id': 'test-comment', 'message': 'The Wi-Fi disconnects every evening.'}]}),
            ('THREADS', '123/replies', 'graph.threads.net',
             {'data': [{'id': 'test-reply', 'text': 'The Wi-Fi disconnects every evening.'}]}),
        ]
        for platform, resource, host, response in sources:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                service = Service(Path(directory) / 'test.db')
                source = service.command('source', {
                    'platform': platform, 'resource': resource, 'authorised': True
                }, 'demo-source')
                env = {f'BELIVE_{platform}_TOKEN': 'fixture-only', 'BELIVE_FACEBOOK_VERSION': 'v23.0'}
                with patch.dict('os.environ', env), patch.object(connectors, 'request_json', return_value=response) as read:
                    first = connectors.scan(service, source['id'])
                    second = connectors.scan(service, source['id'])
                self.assertEqual(len(first), 1)
                self.assertEqual(first, second)
                self.assertIn('https://' + host + '/', read.call_args.args[0])
                self.assertEqual(read.call_args.args[1], 'fixture-only')
                with service.store.connect() as db:
                    cases = service.store.all(db, 'case')
                    self.assertEqual(len(cases), 1)
                    self.assertEqual(cases[0]['platform'], platform)
                    self.assertEqual(cases[0]['description'], 'The Wi-Fi disconnects every evening.')
                    self.assertEqual(service.store.get(db, 'source', source['id'])['status'], 'COMPLETED')
