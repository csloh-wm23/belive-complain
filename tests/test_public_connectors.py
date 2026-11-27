"""Verify public source ingestion without sending requests to live platforms."""
import copy
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import Mock, patch

from belive import automation, connectors, public_diagnostics, public_preview
from belive.service import Service
from belive.store import now


class PublicConnectorTests(unittest.TestCase):
    def setUp(self):
        diagnostic = patch('belive.public_diagnostics.prepare', return_value={
            'state': 'NEEDS_DETAILS', 'details': {}, 'research_summary': '', 'sources': [],
        })
        self.diagnostic = diagnostic.start()
        self.addCleanup(diagnostic.stop)

    def test_each_source_records_one_case_even_when_polled_twice(self):
        sources = [
            ('GOOGLE', 'accounts/123/locations/456', 'mybusiness.googleapis.com',
             {'reviews': [{'reviewId': 'test-review', 'comment': 'The Wi-Fi disconnects every evening.', 'updateTime':now()}]}),
            ('FACEBOOK', '123_456/comments', 'graph.facebook.com',
             {'data': [{'id': '777', 'message': 'The Wi-Fi disconnects every evening.',
                        'from': {'id': '999'}, 'created_time':now()}]}),
            ('THREADS', '123/replies', 'graph.threads.com',
             {'data': [{'id': 'test-reply', 'text': 'The Wi-Fi disconnects every evening.', 'timestamp':now()}]}),
        ]
        for platform, resource, host, response in sources:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                service = Service(Path(directory) / 'test.db')
                source = service.command('source', {
                    'platform': platform, 'resource': resource, 'authorised': True
                }, 'demo-source')
                env = {f'BELIVE_{platform}_TOKEN': 'fixture-only', 'BELIVE_FACEBOOK_VERSION': 'v23.0'}
                def api(url, token):
                    if platform == 'FACEBOOK' and urlsplit(url).path.endswith('/123_456'):
                        return {'id':'123_456','from':{'id':'123'},
                                'permalink_url':'https://www.facebook.com/123/posts/456'}
                    return response
                with patch.dict('os.environ', env), patch.object(connectors, 'request_json', side_effect=api) as read:
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
            ai.public_reply_preview.return_value = (
                'We’re sorry the washing machine is still not working after your report. '
                'What brand and model is it, and is an error code showing?'
            )
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
                sources = [tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')]
            result = service.prepare_public_preview(case['id'], case['revision'], 'staff')
            self.assertEqual(result['text'], ai.public_reply_preview.return_value)
            self.assertEqual(ai.public_reply_preview.call_args.args[0]['assessment_summary'],
                             ai.analyse.return_value['summary'])
            with service.store.connect() as db:
                self.assertEqual(service.store.all(db, 'message'), messages)
                self.assertEqual(service.store.all(db, 'outbox'), outbox)
                self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')], sources)
                saved = service.store.get(db, 'case', case['id'])
                self.assertEqual(saved['public_reply_preview'], result)
                for key, value in case.items():
                    if key not in {'public_reply_preview', 'revision', 'updated_at'}:
                        self.assertEqual(saved[key], value, key)
                self.assertEqual(saved['revision'], case['revision'] + 1)
            with self.assertRaisesRegex(ValueError, 'Case changed'):
                service.prepare_public_preview(case['id'], case['revision'], 'staff')

    def preview_fixture(self, directory, level='MODERATE'):
        ai = Mock()
        ai.public_reply_preview.return_value = (
            'We’re sorry about the washer problem you reported. '
            'What brand and model is it, and is an error code showing?'
        )
        service = Service(Path(directory) / 'test.db', ai)
        case = service.command('intake', {
            'title': 'Fictional washer report', 'description': 'The shared washer will not spin after an earlier report.',
            'platform': 'GOOGLE', 'source_id': 'fixture-public-preview',
        }, 'fixture-preview-intake')
        severity = {'SIMPLE': 'LOW', 'MODERATE': 'MEDIUM', 'HIGH': 'HIGH'}[level]
        with service.store.connect() as db:
            case = service.store.get(db, 'case', case['id'])
            case.update(category='MAINTENANCE', severity=severity, handoff=level != 'SIMPLE',
                        status='AWAITING_CONTACT' if level == 'SIMPLE' else 'HUMAN_REVIEW',
                        staff_destination='Fictional maintenance team',
                        draft='Original source-posting draft must remain unchanged.',
                        analysis=dict(report_type='COMPLAINT', relevance='SUPPORT', uncertainty=False,
                                      category='MAINTENANCE', severity=severity,
                                      requires_human=level != 'SIMPLE',
                                      summary='Reported washer fault and an unresolved earlier report.',
                                      evidence='The shared washer will not spin'))
            service.store.put(db, 'case', case)
        return service, ai, case

    def test_preview_receives_the_assessment_summary_at_every_complaint_level(self):
        for level in ['SIMPLE', 'MODERATE', 'HIGH']:
            with self.subTest(level=level), tempfile.TemporaryDirectory() as directory:
                service, ai, case = self.preview_fixture(directory, level)
                service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
                ai.public_reply_preview.assert_called_once()
                context = ai.public_reply_preview.call_args.args[0]
                self.assertEqual(context['complaint_level'], level)
                self.assertEqual(context['assessment_summary'], case['analysis']['summary'])
                self.assertEqual(context['report'], case['description'])
                self.assertEqual(context['category'], case['category'])
                for private_field in ['tenant_id', 'conversation', 'verified_records', 'knowledge', 'owner']:
                    self.assertNotIn(private_field, context)
                with service.store.connect() as db:
                    saved = service.store.get(db, 'case', case['id'])
                    for key, value in case.items():
                        if key not in {'public_reply_preview', 'revision', 'updated_at'}:
                            self.assertEqual(saved[key], value, key)
                    self.assertEqual(saved['revision'], case['revision'] + 1)

    def test_case_change_during_generation_preserves_the_newer_decision_and_previous_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            service, ai, case = self.preview_fixture(directory)
            previous = {'text': 'Earlier saved preview for staff review.', 'source_version': case['source_versions'][-1]}
            with service.store.connect() as db:
                case['public_reply_preview'] = previous
                service.store.put(db, 'case', case)
                before_events = service.store.audit(db)

            def staff_changes_case(_context):
                with service.lock, service.store.connect() as db:
                    current = service.store.get(db, 'case', case['id'])
                    current.update(revision=current['revision'] + 1, staff_destination='Fictional updated team',
                                   draft='Newer staff wording must not be overwritten.')
                    service.store.put(db, 'case', current)
                return 'We’re sorry about the washer fault. What error code is displayed?'

            ai.public_reply_preview.side_effect = staff_changes_case
            with self.assertRaisesRegex(ValueError, 'Case changed'):
                service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
            with service.store.connect() as db:
                saved = service.store.get(db, 'case', case['id'])
                self.assertEqual(saved['revision'], case['revision'] + 1)
                self.assertEqual(saved['draft'], 'Newer staff wording must not be overwritten.')
                self.assertEqual(saved['staff_destination'], 'Fictional updated team')
                self.assertEqual(saved['public_reply_preview'], previous)
                self.assertEqual(service.store.audit(db), before_events)

    def test_saved_preview_is_current_without_changing_case_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            service, ai, case = self.preview_fixture(directory)
            service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
            with service.store.connect() as db:
                saved = service.store.get(db, 'case', case['id'])
            self.assertTrue(public_preview.is_current(saved))
            shown = next(item for item in service.snapshot()['cases'] if item['id'] == case['id'])
            self.assertTrue(shown['public_preview_current'])
            self.assertEqual(shown['public_reply_preview']['text'], ai.public_reply_preview.return_value)
            saved.update(owner='Fictional staff member', revision=saved['revision'] + 1,
                         draft='Separate source-posting draft edited by staff.')
            self.assertTrue(public_preview.is_current(saved))

    def test_saved_preview_becomes_outdated_when_its_public_inputs_or_format_change(self):
        with tempfile.TemporaryDirectory() as directory:
            service, ai, case = self.preview_fixture(directory)
            service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
            with service.store.connect() as db:
                saved = service.store.get(db, 'case', case['id'])
            for change in ['report', 'title', 'summary', 'category', 'level', 'source', 'old format', 'followup']:
                with self.subTest(change=change):
                    updated = copy.deepcopy(saved)
                    followups = []
                    if change == 'report':
                        updated['description'] += ' It now shows a display error.'
                    elif change == 'title':
                        updated['title'] = 'Updated public washer complaint'
                    elif change == 'summary':
                        updated['analysis']['summary'] = 'New assessment: a repeated interruption.'
                    elif change == 'category':
                        updated['category'] = 'WIFI'
                    elif change == 'level':
                        updated['severity'] = 'HIGH'
                    elif change == 'source':
                        updated['source_versions'].append('new-fixture-source-version')
                    elif change == 'old format':
                        updated['public_reply_preview'].pop('format_version')
                    else:
                        followups = [{'id': 'Fictional reply', 'text': 'The display shows E20.', 'source_url': ''}]
                    self.assertFalse(public_preview.is_current(updated, followups))

    def test_failed_preview_keeps_the_saved_case_and_previous_wording(self):
        with tempfile.TemporaryDirectory() as directory:
            service, ai, case = self.preview_fixture(directory)
            case['public_reply_preview'] = {
                'text': 'Earlier saved wording for staff review.', 'source_version': case['source_versions'][-1],
            }
            with service.store.connect() as db:
                service.store.put(db, 'case', case)
                messages = service.store.all(db, 'message')
                outbox = service.store.all(db, 'outbox')
            ai.public_reply_preview.side_effect = ValueError('AI_UNSAFE_OUTPUT')
            with self.assertRaisesRegex(ValueError, 'safety check'):
                service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
            with service.store.connect() as db:
                self.assertEqual(service.store.get(db, 'case', case['id']), case)
                self.assertEqual(service.store.all(db, 'message'), messages)
                self.assertEqual(service.store.all(db, 'outbox'), outbox)

    def researched_preview_fixture(self):
        return {
            'state': 'RESEARCH_READY',
            'details': {'device': 'WASHING_MACHINE', 'brand': 'Samsung',
                        'model': 'WW80T554DAW', 'error_code': '4C', 'ready': True},
            'research_summary': 'Fictional captured evidence describes water-supply checks for a model variant.',
            'sources': [{'id': 'WEB-fixture',
                         'url': 'https://www.samsung.com/my/support/model/WW80T554DAW/SP/',
                         'title': 'Fictional captured model evidence WW80T554DAW/SP'}],
        }

    def test_valid_negative_manual_review_saves_only_a_new_clarification(self):
        with tempfile.TemporaryDirectory() as directory:
            service, ai, case = self.preview_fixture(directory)
            diagnostic = self.researched_preview_fixture()
            diagnostic['details']['model'] = 'WW80T554DAW/SP'
            confirmed_details = copy.deepcopy(diagnostic['details'])
            checked_sources = copy.deepcopy(diagnostic['sources'])
            self.diagnostic.return_value = diagnostic
            negative_review = {
                'safe': True, 'grounded': False, 'model_compatible': False, 'uncertainty': True,
                'unsupported_claims': ['The captured evidence does not support the proposed manual advice.'],
            }
            rejected_advice = 'Please check the water supply tap and inlet hose using the manual.'
            clarification = (
                'Thanks for confirming the appliance details. I cannot confirm supported guidance from '
                'the information checked yet. Does the washer fill with water before stopping, and '
                'what checks have you already tried? Your unresolved maintenance report remains with staff.'
            )
            generated_contexts = []
            responses = iter([rejected_advice, clarification])

            def generate_reply(context):
                generated_contexts.append(copy.deepcopy(context))
                return next(responses)

            ai.public_reply_preview.side_effect = generate_reply
            with service.store.connect() as db:
                messages = service.store.all(db, 'message')
                outbox = service.store.all(db, 'outbox')
                sources = [tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')]
            with patch('belive.public_diagnostics.validate_reply',
                       side_effect=public_diagnostics.DiagnosticReviewFailure(negative_review)) as validate:
                result = service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')

            self.assertEqual(ai.public_reply_preview.call_count, 2)
            validate.assert_called_once()
            self.assertEqual(validate.call_args.args[2], rejected_advice)
            self.assertEqual(generated_contexts[0]['research_state'], 'RESEARCH_READY')
            self.assertEqual(generated_contexts[0]['research_sources'], checked_sources)
            retry_context = generated_contexts[1]
            self.assertEqual(retry_context['research_state'], 'NO_RELIABLE_SOURCE')
            self.assertEqual(retry_context['research_summary'], '')
            self.assertEqual(retry_context['research_sources'], [])
            self.assertEqual(retry_context['research_details'], confirmed_details)
            self.assertTrue(retry_context['research_details']['ready'])
            self.assertEqual(retry_context['diagnostic_review_feedback'], negative_review)
            self.assertEqual(retry_context['assessment_summary'], case['analysis']['summary'])
            self.assertEqual(result['text'], clarification)
            self.assertNotIn('inlet hose', result['text'])
            self.assertEqual(result['research_state'], 'NO_RELIABLE_SOURCE')
            self.assertEqual(result['device_details'], confirmed_details)
            self.assertTrue(result['device_details']['ready'])
            self.assertEqual(result['sources'], [])
            self.assertEqual(result['checked_sources'], checked_sources)
            self.assertEqual(result['diagnostic_review'], negative_review)
            with service.store.connect() as db:
                saved = service.store.get(db, 'case', case['id'])
                self.assertEqual(saved['public_reply_preview'], result)
                self.assertTrue(public_preview.is_current(saved))
                for key, value in case.items():
                    if key not in {'public_reply_preview', 'revision', 'updated_at'}:
                        self.assertEqual(saved[key], value, key)
                self.assertEqual(saved['revision'], case['revision'] + 1)
                self.assertEqual(service.store.all(db, 'message'), messages)
                self.assertEqual(service.store.all(db, 'outbox'), outbox)
                self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sources ORDER BY id')], sources)

    def test_malformed_manual_review_keeps_previous_preview_without_clarification_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            service, ai, case = self.preview_fixture(directory)
            self.diagnostic.return_value = self.researched_preview_fixture()
            case['public_reply_preview'] = {
                'text': 'Earlier saved preview must remain available.',
                'source_version': case['source_versions'][-1],
            }
            with service.store.connect() as db:
                service.store.put(db, 'case', case)
                messages = service.store.all(db, 'message')
                outbox = service.store.all(db, 'outbox')
                audit = service.store.audit(db)
            ai.public_reply_preview.return_value = 'Please check the water supply tap and inlet hose using the manual.'
            with patch('belive.public_diagnostics.validate_reply',
                       side_effect=ValueError('AI_UNGROUNDED_GUIDANCE')) as validate:
                with self.assertRaisesRegex(ValueError, 'knowledge and safety review'):
                    service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
            ai.public_reply_preview.assert_called_once()
            validate.assert_called_once()
            with service.store.connect() as db:
                self.assertEqual(service.store.get(db, 'case', case['id']), case)
                self.assertEqual(service.store.all(db, 'message'), messages)
                self.assertEqual(service.store.all(db, 'outbox'), outbox)
                self.assertEqual(service.store.audit(db), audit)

    def test_preview_does_not_generate_for_uncertain_or_inactive_assessments(self):
        for change in ['uncertain', 'enquiry', 'closed']:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                service, ai, case = self.preview_fixture(directory)
                if change == 'uncertain':
                    case['analysis']['uncertainty'] = True
                elif change == 'enquiry':
                    case['analysis']['report_type'] = 'ENQUIRY'
                else:
                    case['status'] = 'CLOSED'
                with service.store.connect() as db:
                    service.store.put(db, 'case', case)
                with self.assertRaisesRegex(ValueError, 'confirmed, active public complaint'):
                    service.prepare_public_preview(case['id'], case['revision'], 'fixture staff')
                ai.public_reply_preview.assert_not_called()

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
            fixture_time = now()
            def read(url, token):
                if 'mybusiness.googleapis.com' in url:
                    return {'reviews':[{'reviewId':'review-1','comment':'The Wi-Fi drops every evening.','updateTime':fixture_time}]}
                return {'data':[{'id':'reply-1','text':'The washing machine is broken.','timestamp':fixture_time}]}

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
