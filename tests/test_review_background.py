"""Background review collection and public-only routing regressions; no live requests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from belive import browser_reviews as reviews
from belive.service import Service


LISTING='https://www.google.com/maps/place/Fictional+BeLive'
REVIEW='https://www.google.com/maps/contrib/123456789/place/ChIJFixture/'


class BackgroundReviewTests(unittest.TestCase):
    def test_saved_collector_profile_still_launches_headless(self):
        runtime=MagicMock();runtime.__enter__.return_value=runtime
        context=runtime.chromium.launch_persistent_context.return_value
        with patch('playwright.sync_api.sync_playwright',return_value=runtime):
            with reviews._google_page(headless=True,profile=Path('fixture-profile')) as page:
                self.assertIs(page,context.new_page.return_value)
        self.assertIs(runtime.chromium.launch_persistent_context.call_args.kwargs['headless'],True)
        runtime.chromium.launch.assert_not_called()
        context.close.assert_called_once()

    def test_listing_collection_requests_background_browser_even_with_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            profile=Path(directory);opened=MagicMock();page=opened.return_value.__enter__.return_value
            with patch.object(reviews,'review_chrome_profile',return_value=profile),patch.object(reviews,'_google_page',opened),patch.object(reviews,'_collect_listing',return_value=[]) as collect:
                self.assertEqual(reviews.read_browser_review_batch(LISTING),([],0))
            opened.assert_called_once_with(headless=True,profile=profile)
            collect.assert_called_once_with(page,LISTING)

    def test_individual_link_batch_is_background_and_input_duplicates_read_once(self):
        opened=MagicMock();review={'source_id':'google-browser-fixture','rating':1,'description':'A fixture washing machine complaint.','review_url':REVIEW}
        with patch.object(reviews,'_google_page',opened),patch.object(reviews,'_open_review',return_value=review) as read:
            captured,skipped=reviews.read_browser_review_batch(REVIEW+'\n'+REVIEW)
        opened.assert_called_once_with(headless=True)
        self.assertEqual(captured,[review]);self.assertEqual(skipped,0);self.assertEqual(read.call_count,1)

    def test_importing_same_real_shape_twice_keeps_one_case_and_source_version(self):
        with tempfile.TemporaryDirectory() as directory:
            service=Service(Path(directory)/'qa.db')
            review={'source_id':'google-browser-fixture','rating':1,'description':'The shared washing machine stopped during a wash.','review_url':REVIEW}
            first,created=service.import_browser_review(review,'fixture-reviewer')
            second,repeated=service.import_browser_review(review,'fixture-reviewer')
            self.assertTrue(created);self.assertFalse(repeated);self.assertEqual(first['id'],second['id'])
            with service.store.connect() as db:
                self.assertEqual(len(service.store.all(db,'case')),1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sources').fetchone()[0],1)
                self.assertFalse(service.store.all(db,'outbox'))

    def test_simple_moderate_high_and_outside_support_keep_public_delivery_private(self):
        scenarios=[('LOW','COMPLAINT','SUPPORT','AWAITING_CONTACT',True),('MEDIUM','COMPLAINT','SUPPORT','HUMAN_REVIEW',False),('HIGH','COMPLAINT','SUPPORT','HUMAN_REVIEW',False),('LOW','NON_SUPPORT','NON_SUPPORT','SKIPPED',False)]
        for severity,kind,relevance,status,simple in scenarios:
            with self.subTest(severity=severity,kind=kind),tempfile.TemporaryDirectory() as directory:
                ai=Mock();ai.analyse.return_value={'report_type':kind,'relevance':relevance,'category':'WIFI','severity':severity,'uncertainty':False,'summary':'A fixture support assessment.','evidence':'connection','requires_human':False,'agent_trace':[]}
                ai.classify_public_guidance.return_value={'can_answer':True,'topics':['wifi_checks']}
                service=Service(Path(directory)/'qa.db',ai)
                case=service.command('intake',{'title':'Public connection report','description':'My phone connection keeps failing. What can I check?','public_url':LISTING},'fixture-public-intake')
                service.analyse(case['id'])
                with service.store.connect() as db:
                    saved=service.store.get(db,'case',case['id'])
                    self.assertEqual(saved['status'],status)
                    self.assertEqual(bool(saved.get('public_guidance_prepared')),simple)
                    self.assertFalse(any(x.get('kind')=='TENANT_RESPONSE' for x in service.store.all(db,'outbox')))
                    self.assertFalse(any(x.get('sender') in {'SUPPORT','AI_SUPPORT'} for x in service.store.all(db,'message')))
                if simple:ai.classify_public_guidance.assert_called_once()
                else:ai.classify_public_guidance.assert_not_called()


class PortableRehearsalTests(unittest.TestCase):
    def test_fresh_source_database_has_no_required_historical_case(self):
        from scripts import rehearse_public_review as rehearsal
        with tempfile.TemporaryDirectory() as directory:
            missing=Path(directory)/'new.db'
            self.assertEqual(rehearsal.read_saved(missing),{'historical':None,'source_rows':[],'listing':None,'alternative_url':None})
            self.assertFalse(missing.exists())
            service=Service(missing)
            self.assertIsNone(rehearsal.read_saved(service.store.path)['historical'])

    def test_discovered_fallback_is_matching_browser_capture_not_manual_summary(self):
        from scripts import rehearse_public_review as rehearsal
        with tempfile.TemporaryDirectory() as directory:
            service=Service(Path(directory)/'source.db')
            review={'source_id':'google-browser-unrelated-local-id','rating':1,'description':'A fixture washing machine fault.','review_url':REVIEW}
            case,_=service.import_browser_review(review,'fixture')
            with service.store.connect() as db:
                manual=dict(case,id='LOCAL-MANUAL',source_id='public-link-summary')
                service.store.put(db,'case',manual)
            selected=rehearsal.read_saved(service.store.path,REVIEW)
            self.assertEqual(selected['historical']['id'],case['id'])
            self.assertEqual(len(selected['source_rows']),1)
            other=rehearsal.read_saved(service.store.path,rehearsal.DEFAULT_REVIEW_URL)
            self.assertIsNone(other['historical'])

    def test_database_only_model_settings_apply_without_copying_secret_to_test_db(self):
        import os
        from belive import credentials
        from scripts import rehearse_public_review as rehearsal
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'BELIVE_AI_KEY':'','BELIVE_AI_PROVIDER':'openai','BELIVE_AI_MODEL':'gpt-6-luna','BELIVE_AGENT_ENGINE':'hermes'}):
            active=Service(Path(directory)/'active'/'source.db')
            credentials.save(active,{'version':0,'values':{'BELIVE_AI_PROVIDER':'openai','BELIVE_AI_MODEL':'gpt-6-luna','BELIVE_AI_KEY':'fixture-private-only-database-key'}},'fixture')
            settings=rehearsal.configured_settings(active.store.path)
            service=rehearsal.isolated_service(Path(directory)/'isolated'/'qa.db',settings)
            self.assertEqual(service.settings.llm_api_key,'fixture-private-only-database-key')
            self.assertIs(service.ai.settings,settings)
            self.assertEqual(credentials.load(service.store.path)['values'],{})
            self.assertFalse(credentials.key_path(service.store.path).exists())
            self.assertNotIn(b'fixture-private-only-database-key',service.store.path.read_bytes())

    def test_no_live_or_saved_review_reports_blocked_without_inventing_capture(self):
        import contextlib
        import io
        import json
        from belive.settings import Settings
        from scripts import rehearse_public_review as rehearsal
        with tempfile.TemporaryDirectory() as directory,patch.object(rehearsal,'ROOT',Path(directory)),patch('sys.argv',['rehearse_public_review.py','--run-live']),patch('belive.workspace.selected_database',return_value=Path(directory)/'missing.db'),patch.object(rehearsal,'configured_settings',return_value=Settings(llm_model='gpt-6-luna',llm_api_key='fixture')),patch('belive.hermes_native.runtime_info',return_value={}),patch.object(reviews,'read_browser_review',side_effect=ValueError('Selected page unavailable')),patch.object(reviews,'read_browser_review_batch',side_effect=ValueError('Selected page unavailable')),contextlib.redirect_stdout(io.StringIO()):
            rehearsal.main()
            reports=list(Path(directory).rglob('report.json'))
            self.assertEqual(len(reports),1)
            report=json.loads(reports[0].read_text(encoding='utf-8'))
            self.assertEqual(report['status'],'BLOCKED')
            self.assertNotIn('source',report)
            self.assertFalse(list(Path(directory).rglob('rehearsal.db')))
            self.assertFalse(report['external_publication_attempted'])

    def test_ui_checks_follow_saved_level_and_actual_preview_for_other_topics(self):
        from scripts import rehearse_public_review as rehearsal
        with tempfile.TemporaryDirectory() as directory:
            service=Service(Path(directory)/'qa.db')
            case=service.command('intake',{'title':'Fixture noise concern','description':'Repeated loud noise in the shared corridor.','public_url':LISTING},'fixture-intake')
            with service.store.connect() as db:
                saved=service.store.get(db,'case',case['id'])
                saved.update(severity='HIGH',staff_destination='Building support',public_reply_preview={'text':'We are sorry about the repeated noise you reported.'})
                service.store.put(db,'case',saved)
            self.assertEqual(rehearsal.preview_expectations(service,case['id']),('HIGH','Building support','We are sorry about the repeated noise you reported.'))


if __name__=='__main__':unittest.main()
