"""Verify public source ingestion without sending requests to live platforms."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from belive import automation, connectors
from belive.service import Service


class PublicConnectorTests(unittest.TestCase):
    def test_each_source_records_one_case_even_when_polled_twice(self):
        sources = [
            ('GOOGLE', 'accounts/123/locations/456', 'mybusiness.googleapis.com',
             {'reviews': [{'reviewId': 'test-review', 'comment': 'The Wi-Fi disconnects every evening.'}]}),
            ('FACEBOOK', '123_456/comments', 'graph.facebook.com',
             {'data': [{'id': 'test-comment', 'message': 'The Wi-Fi disconnects every evening.'}]}),
            ('THREADS', '123/replies', 'graph.threads.com',
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

    def test_public_guidance_requires_simple_assessment_and_preview_stays_private(self):
        with tempfile.TemporaryDirectory() as directory:
            ai = Mock()
            ai.analyse.return_value = dict(report_type='COMPLAINT', relevance='SUPPORT',
                category='MAINTENANCE', severity='MEDIUM', uncertainty=False,
                summary='A repair needs staff follow-up', evidence='washing machine',
                agent_trace=[{'agent':'Complaint Analysis Agent','status':'COMPLETED'}])
            ai.public_reply_preview.return_value = 'Thank you for reporting the washing machine issue. Please contact support privately.'
            service = Service(Path(directory) / 'test.db', ai)
            case = service.command('intake', {
                'title':'Appliance fault', 'description':'The washing machine stopped working.',
                'public_url':'https://www.google.com/maps/place/Fictional+Residence',
            }, 'intake-preview')
            service.analyse(case['id'])
            ai.classify_public_guidance.assert_not_called()
            with service.store.connect() as db:
                case = service.store.get(db, 'case', case['id'])
                self.assertEqual(case['status'], 'HUMAN_REVIEW')
                messages = service.store.all(db, 'message')
                outbox = service.store.all(db, 'outbox')
            result = service.prepare_public_preview(case['id'], case['revision'], 'staff')
            self.assertIn('washing machine', result['text'])
            with service.store.connect() as db:
                self.assertEqual(service.store.all(db, 'message'), messages)
                self.assertEqual(service.store.all(db, 'outbox'), outbox)
                saved = service.store.get(db, 'case', case['id'])
                self.assertEqual(saved['public_reply_preview'], result)
                self.assertEqual(saved['severity'], 'MEDIUM')
            with self.assertRaisesRegex(ValueError, 'Case changed'):
                service.prepare_public_preview(case['id'], case['revision'], 'staff')

    def test_simple_public_complaint_creates_only_an_approved_local_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            ai = Mock()
            ai.analyse.return_value = dict(report_type='COMPLAINT', relevance='SUPPORT',
                category='WIFI', severity='LOW', uncertainty=False,
                summary='Routine device connection trouble', evidence='Wi-Fi')
            ai.classify_public_guidance.return_value = {'can_answer':True, 'topics':['wifi_checks']}
            service = Service(Path(directory) / 'test.db', ai)
            case = service.command('intake', {
                'title':'Wi-Fi on my phone', 'description':'My phone will not connect. What can I check?',
                'public_url':'https://www.google.com/maps/place/Fictional+Residence',
            }, 'intake-simple')
            service.analyse(case['id'])
            ai.classify_public_guidance.assert_called_once()
            with service.store.connect() as db:
                case = service.store.get(db, 'case', case['id'])
                self.assertEqual(case['status'], 'AWAITING_CONTACT')
                self.assertTrue(case['public_guidance_prepared'])
                self.assertEqual(case['draft'], automation.public_guidance_reply(
                    ai.classify_public_guidance.return_value, public_source=True))
                self.assertIn('contact BeLive tenant support privately', case['draft'])
                self.assertNotIn('Still unresolved', case['draft'])
                self.assertFalse(any(m['sender']=='SUPPORT' for m in service.store.all(db, 'message')))
                self.assertFalse(service.store.all(db, 'outbox'))

    def test_scheduler_reads_due_google_and_threads_sources_only(self):
        from server import Tasks

        with tempfile.TemporaryDirectory() as directory:
            service = Service(Path(directory) / 'test.db')
            ids = {}
            for platform, resource, enabled in [
                ('GOOGLE', 'accounts/123/locations/456', True),
                ('THREADS', '123/replies', True),
                ('THREADS', '789/replies', False),
            ]:
                ids[resource] = service.command('source', {
                    'platform':platform, 'resource':resource, 'authorised':True, 'enabled':enabled,
                }, 'schedule-'+resource)['id']
            tasks = Tasks(service)
            tasks.stop = Mock()
            tasks.stop.wait.side_effect = [False, False, True]
            def read(url, token):
                if 'mybusiness.googleapis.com' in url:
                    return {'reviews':[{'reviewId':'review-1','comment':'The Wi-Fi drops every evening.'}]}
                return {'data':[{'id':'reply-1','text':'The washing machine is broken.'}]}

            with patch.dict('os.environ', {'BELIVE_GOOGLE_TOKEN':'fixture','BELIVE_THREADS_TOKEN':'fixture'}), \
                    patch.object(connectors, 'request_json', side_effect=read) as request, \
                    patch.object(tasks, 'start', side_effect=lambda _key, run: run()), \
                    patch.object(tasks, 'analyse'):
                tasks.loop()
            self.assertEqual(request.call_count, 2)
            with service.store.connect() as db:
                scheduled = service.store.all(db, 'source')
                completed = [s for s in scheduled if s['enabled']]
                self.assertEqual({s['platform'] for s in completed}, {'GOOGLE','THREADS'})
                self.assertTrue(all(s['status']=='COMPLETED' and s['last_count']==1
                                    and s['next_scan']>s['last_scan'] for s in completed))
                self.assertIsNone(service.store.get(db, 'source', ids['789/replies'])['last_scan'])
                self.assertEqual(len(service.store.all(db, 'case')), 2)
