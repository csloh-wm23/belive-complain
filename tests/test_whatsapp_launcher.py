"""Launcher recovery, company binding and current-vs-historical proof; no real sends."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

from belive import launch_status
from belive.store import now

spec=importlib.util.spec_from_file_location('start_belive',Path(__file__).resolve().parents[1]/'scripts/start_belive.py')
launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/'qa.db'
        self.credentials={'access_token':'fictional-access','verify_token':'fictional-verify','phone_number_id':'123456'}
        self.profile={'id':'123456','display_phone_number':'+60100000000','is_on_biz_app':True,'platform_type':'CLOUD_API'}
        self.details={'is_valid':True,'app_id':'345678','scopes':['whatsapp_business_management','whatsapp_business_messaging']}
        self.calls=[]
        self.patches=[patch.object(launch,'configuration',return_value=self.credentials),
            patch.object(launch.meta,'config',return_value={'app_id':'345678','app_secret':'fictional-secret'}),
            patch.object(launch.meta,'read_json',return_value={'waba_id':'234567'}),
            patch.object(launch,'company_number',return_value='60100000000'),
            patch.object(launch.meta,'graph',side_effect=self.graph)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def graph(self,path,token='',payload=None,params=None):
        self.calls.append((path,payload))
        if path=='debug_token':return {'data':self.details}
        if path=='234567/phone_numbers':return {'data':[self.profile]}
        if path=='234567/subscribed_apps' and payload is None:return {'data':[{'whatsapp_business_api_data':{'id':'345678'}}]}
        return {'success':True}
    def writes(self):return [(path,p) for path,p in self.calls if p is not None]
    def test_updates_only_verified_existing_phone_and_account(self):
        self.assertTrue(launch.update_meta(self.db,'https://qa.example.test'))
        self.assertEqual([p for p,_ in self.writes()],['123456','234567/subscribed_apps'])
        self.assertEqual(self.writes()[0][1]['webhook_configuration']['override_callback_uri'],'https://qa.example.test/webhooks/whatsapp')
        self.assertFalse(any('/subscriptions' in p or '/register' in p for p,_ in self.calls))
    def test_wrong_app_does_not_write_any_callback(self):
        self.details['app_id']='999999'
        with self.assertRaises(launch.StartupError):launch.update_meta(self.db,'https://qa.example.test')
        self.assertEqual(self.writes(),[])
    def test_wrong_number_or_missing_coexistence_cannot_change_company(self):
        for changes in [{'display_phone_number':'+60200000000'},{'is_on_biz_app':False}]:
            with self.subTest(changes=changes):
                self.calls.clear();old=dict(self.profile);self.profile.update(changes)
                with self.assertRaises(launch.StartupError):launch.update_meta(self.db,'https://qa.example.test')
                self.assertEqual(self.writes(),[]);self.profile.clear();self.profile.update(old)
    def test_failed_meta_save_is_not_ready(self):
        with patch.object(launch.meta,'graph',side_effect=lambda *a,**kw: {'success':False} if kw.get('payload') is not None else self.graph(*a,**kw)):
            with self.assertRaises(launch.StartupError):launch.update_meta(self.db,'https://qa.example.test')
    def test_existing_services_are_reused_without_spawning(self):
        supervisor=launch.Supervisor(self.db)
        with patch.object(launch,'backend_ok',return_value=True),patch.object(launch,'gateway_ok',return_value=True),patch.object(supervisor,'spawn') as spawn:
            supervisor.ensure_local();spawn.assert_not_called();self.assertTrue(supervisor.checks['backend'])
    def test_unrelated_port_owner_is_preserved(self):
        supervisor=launch.Supervisor(self.db)
        with patch.object(launch,'backend_ok',return_value=False),patch.object(launch,'occupied',return_value=True),patch.object(supervisor,'spawn') as spawn,patch.object(supervisor,'status'):
            with self.assertRaisesRegex(launch.StartupError,'BACKEND'):supervisor.ensure_local()
            spawn.assert_not_called()
    def test_existing_https_is_reused_and_dead_https_invalidates_ready(self):
        supervisor=launch.Supervisor(self.db)
        with patch.object(launch.meta,'origin',return_value='https://qa.example.test'),patch.object(launch,'challenge',return_value=True),patch.object(supervisor,'spawn') as spawn:
            supervisor.ensure_tunnel();spawn.assert_not_called();self.assertTrue(supervisor.checks['https'])
        supervisor.checks['meta']=True
        with patch.object(launch,'backend_ok',return_value=True),patch.object(launch,'gateway_ok',return_value=True),patch.object(launch,'challenge',return_value=False),patch.object(supervisor,'status'):
            self.assertFalse(supervisor.monitor());self.assertFalse(supervisor.checks['meta']);self.assertFalse(supervisor.checks['https'])
    def test_duplicate_launcher_lock(self):
        first=launch.lock_launcher(self.root/'launcher.lock')
        self.assertIsNotNone(first)
        try:self.assertIsNone(launch.lock_launcher(self.root/'launcher.lock'))
        finally:first.close()

class LauncherStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'status.json'
        self.patch=patch.object(launch_status,'PATH',self.path);self.patch.start()
        self.row={'state':'READY','checks':{k:True for k in ('backend','hermes','https','meta')},'started_at':now(),'updated_at':now(),'detail':'Ready for test.'}
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def save(self):self.path.write_text(json.dumps(self.row),encoding='utf-8')
    def test_old_receipt_cannot_confirm_new_start(self):
        self.save();result=launch_status.current({'last_customer_message':'2000-01-01','last_reply_delivered':'2000-01-01'})
        self.assertTrue(result['ready']);self.assertFalse(result['live_delivery_this_start'])
        self.assertTrue(launch_status.current({'last_customer_message':now(),'last_reply_delivered':now()})['live_delivery_this_start'])
    def test_missing_receipt_still_displays_connection_checks(self):
        self.save();self.assertTrue(launch_status.current({'last_reply_delivered':None})['ready'])
        self.assertFalse(launch_status.current()['live_delivery_this_start'])
    def test_dead_or_stale_launcher_cannot_show_ready(self):
        self.row['updated_at']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat();self.save()
        self.assertFalse(launch_status.current()['ready']);self.assertEqual(launch_status.current()['state'],'STOPPED')
    def test_failed_component_cannot_claim_delivery(self):
        self.row['checks']['meta']=False;self.save()
        self.assertFalse(launch_status.current({'last_customer_message':now(),'last_reply_delivered':now()})['live_delivery_this_start'])
