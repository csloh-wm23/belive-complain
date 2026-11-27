"""Per-source time windows using official API-shaped fixtures, never live credentials."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import Mock, patch

from belive import connectors
from belive.service import Service


def ago(days):
    return (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()


def google_review(review_id, age=1, **extra):
    return {'reviewId':str(review_id),'comment':'TEST: The shared washing machine has stopped working.',
            'createTime':ago(age+1),'updateTime':ago(age), **extra}


def thread_reply(reply_id, age=1, **extra):
    return {'id':str(reply_id),'text':'TEST: The shared washing machine has stopped working.',
            'timestamp':ago(age),'permalink':'https://www.threads.com/@fixture/post/reply'+str(reply_id), **extra}


class SourceLookbackTests(unittest.TestCase):
    def test_every_platform_defaults_to_30_and_validates_same_range(self):
        for platform, resource in (('GOOGLE','accounts/123/locations/456'),
                                   ('FACEBOOK','123/feed'),('THREADS','123/threads')):
            payload = {'platform':platform,'resource':resource,'authorised':True}
            with self.subTest(platform=platform):
                self.assertEqual(connectors.validate_source(payload)['lookback_days'], 30)
                for days in (1,7,30,365):
                    self.assertEqual(connectors.validate_source(dict(payload,lookback_days=days))['lookback_days'], days)
                for days in (0,-1,366,True,False,'30',30.5,None):
                    with self.subTest(days=days), self.assertRaises(ValueError):
                        connectors.validate_source(dict(payload,lookback_days=days))

    def test_each_source_saves_its_own_window_without_changing_schedule_or_other_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            service = Service(Path(directory)/'test.db',Mock())
            saved = []
            for platform, resource in (('GOOGLE','accounts/123/locations/456'),
                                       ('FACEBOOK','123/feed'),('THREADS','123/threads')):
                saved.append(service.command('source', {
                    'platform':platform,'resource':resource,'authorised':True,
                }, 'fixture-create-'+platform))
            for index, source in enumerate(saved):
                days = (7,30,365)[index]
                changed = service.command('source', {
                    'platform':source['platform'],'resource':source['resource'],'authorised':True,'lookback_days':days,
                }, 'fixture-update-'+source['platform'])
                self.assertEqual(changed['id'],source['id'])
            with service.store.connect() as db:
                records = service.store.all(db,'source')
                self.assertEqual(len(records),3)
                self.assertEqual({item['platform']:item['lookback_days'] for item in records},
                                 {'GOOGLE':7,'FACEBOOK':30,'THREADS':365})
                self.assertEqual(connectors.scan_interval(service.store,db),15)


class GoogleLookbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ai = Mock()
        self.service = Service(Path(self.tmp.name)/'test.db',self.ai)
        self.source = self.service.command('source', {
            'platform':'GOOGLE','resource':'accounts/123/locations/456','authorised':True,
        }, 'fixture-google-source')

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, reviews, source=None):
        with patch.object(connectors,'get_value',return_value='fixture-only-token'), \
                patch.object(connectors,'request_json',return_value={'reviews':reviews}) as request:
            rows = connectors.read_source(source or self.source)
        self.assertTrue(request.call_args.args[0].startswith('https://mybusiness.googleapis.com/v4/accounts/123/locations/456/reviews?'))
        return rows

    def scan(self, reviews):
        with patch.object(connectors,'get_value',return_value='fixture-only-token'), \
                patch.object(connectors,'request_json',return_value={'reviews':reviews}):
            return connectors.scan(self.service,self.source['id'])

    def test_custom_windows_filter_review_update_times_and_old_sources_default_to_30(self):
        reviews = [google_review(str(age),age) for age in (2,20,200,400)]
        for days, ids in ((7,{'2'}),(30,{'2','20'}),(365,{'2','20','200'})):
            with self.subTest(days=days):
                rows = self.read(reviews,dict(self.source,lookback_days=days))
                self.assertEqual({row['id'].rsplit('/',1)[-1] for row in rows},ids)
        legacy = dict(self.source)
        legacy.pop('lookback_days',None)
        self.assertEqual({row['id'].rsplit('/',1)[-1] for row in self.read(reviews,legacy)}, {'2','20'})

    def test_update_time_has_priority_with_create_time_fallback_only_when_absent_or_invalid(self):
        reviews = [google_review('edited',1,createTime=ago(100)),
                   google_review('old-update',40,createTime=ago(1)),
                   google_review('missing-update',1),google_review('invalid-update',1,updateTime='invalid')]
        reviews[2].pop('updateTime')
        self.assertEqual({row['id'].rsplit('/',1)[-1] for row in self.read(reviews)},
                         {'edited','missing-update','invalid-update'})

    def test_missing_naive_invalid_and_future_review_times_do_not_create_cases(self):
        reviews = [google_review('valid',1),
                   {'reviewId':'missing','comment':'TEST: A fictional reported washer fault.'},
                   {'reviewId':'invalid','comment':'TEST: A fictional reported washer fault.','updateTime':'bad'},
                   {'reviewId':'naive','comment':'TEST: A fictional reported washer fault.','updateTime':'2026-11-28T10:00:00'},
                   {'reviewId':'future','comment':'TEST: A fictional reported washer fault.','updateTime':ago(-2)}]
        self.assertEqual(len(self.scan(reviews)),1)
        with self.service.store.connect() as db:
            cases = self.service.store.all(db,'case')
        self.assertEqual([case['source_id'] for case in cases],['accounts/123/locations/456/valid'])

    def test_google_stable_identifiers_and_creation_update_metadata_survive_intake(self):
        review = google_review('unchanged-review-id',1,createTime=ago(100))
        self.scan([review])
        with self.service.store.connect() as db:
            case = self.service.store.all(db,'case')[0]
        self.assertEqual(case['source_id'],'accounts/123/locations/456/unchanged-review-id')
        self.assertEqual(case['source_created_at'],review['createTime'])
        self.assertEqual(case['source_updated_at'],review['updateTime'])
        self.assertFalse(case.get('public_url'))
        self.ai.analyse.assert_not_called()

    def test_google_owner_reply_is_not_imported_as_another_customer_complaint(self):
        review = google_review('customer-review',1,reviewReply={
            'comment':'Owner fixture response: we have received this report.','updateTime':ago(0.5),
        })
        self.scan([review])
        with self.service.store.connect() as db:
            cases = self.service.store.all(db,'case')
        self.assertEqual(len(cases),1)
        self.assertEqual(cases[0]['description'],review['comment'])
        self.assertNotIn('Owner fixture response',cases[0]['description'])

    def test_timestamp_only_refresh_enriches_same_google_case_without_replacing_saved_work(self):
        review = google_review('same-review',2)
        self.scan([review])
        with self.service.store.connect() as db:
            case = self.service.store.all(db,'case')[0]
            case.update(analysis={'summary':'Saved fixture assessment.'},draft='Saved fixture staff draft.',
                        status='HUMAN_REVIEW',public_reply={'status':'POSTED','receipt_id':'fixture-receipt'})
            self.service.store.put(db,'case',case)
            original = copy.deepcopy(case)
            immutable = [tuple(row) for row in db.execute('SELECT * FROM sources')]
        updated = dict(review,updateTime=ago(1))
        self.scan([updated])
        with self.service.store.connect() as db:
            cases = self.service.store.all(db,'case')
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sources')],immutable)
        self.assertEqual(len(cases),1)
        self.assertEqual(cases[0]['source_updated_at'],updated['updateTime'])
        for field in ('id','source_id','source_versions','description','analysis','draft','status','public_reply'):
            self.assertEqual(cases[0][field],original[field],field)

    def test_changed_google_review_retains_both_immutable_text_versions(self):
        review = google_review('edited-review',2)
        self.scan([review])
        updated = dict(review,comment='TEST: The shared washing machine is still broken after seven days.',updateTime=ago(1))
        self.scan([updated])
        self.scan([updated])
        with self.service.store.connect() as db:
            versions = [json.loads(row[0])['text'] for row in db.execute(
                'SELECT body FROM sources WHERE platform=? AND source_id=?',
                ('GOOGLE','accounts/123/locations/456/edited-review'))]
            self.assertEqual(len(self.service.store.all(db,'case')),2)
        self.assertEqual(set(versions),{review['comment'],updated['comment']})


class ThreadsLookbackTests(unittest.TestCase):
    def setUp(self):
        self.source = connectors.validate_source({'platform':'THREADS','resource':'123/threads','authorised':True})

    def read(self, posts, replies, source=None):
        def api(url,token,*args,**kwargs):
            self.assertEqual(urlsplit(url).netloc,'graph.threads.com')
            self.assertFalse(args)
            self.assertNotEqual(kwargs.get('method'),'POST')
            path = urlsplit(url).path
            if path.endswith('/123/threads'):
                return {'data':posts}
            return {'data':replies.get(path.split('/')[-2],[])}
        with patch.object(connectors,'get_value',return_value='fixture-only-token'), \
                patch.object(connectors,'request_json',side_effect=api) as request:
            rows = connectors.read_source(source or self.source)
        return rows,request

    def test_account_windows_filter_parent_posts_and_their_replies(self):
        posts = [{'id':str(100+index),'timestamp':ago(age)} for index,age in enumerate((2,20,200,400))]
        replies = {item['id']:[thread_reply(1000+index,age)]
                   for index,(item,age) in enumerate(zip(posts,(2,20,200,400)))}
        for days, ids in ((7,{'1000'}),(30,{'1000','1001'}),(365,{'1000','1001','1002'})):
            with self.subTest(days=days):
                rows,_ = self.read(posts,replies,dict(self.source,lookback_days=days))
                self.assertEqual({row['id'] for row in rows},ids)
        legacy = dict(self.source)
        legacy.pop('lookback_days',None)
        self.assertEqual({row['id'] for row in self.read(posts,replies,legacy)[0]},{'1000','1001'})

    def test_missing_invalid_naive_or_future_parent_times_are_not_crawled(self):
        posts = [{'id':'100','timestamp':ago(1)}, {'id':'101'}, {'id':'102','timestamp':'bad'},
                 {'id':'103','timestamp':'2026-11-28T10:00:00'}, {'id':'104','timestamp':ago(-2)}]
        replies = {item['id']:[thread_reply(1000+index)] for index,item in enumerate(posts)}
        rows,request = self.read(posts,replies)
        self.assertEqual([row['id'] for row in rows],['1000'])
        self.assertEqual(request.call_count,2)

    def test_recent_parent_does_not_admit_old_missing_invalid_or_future_replies(self):
        items = [thread_reply(1000,1),thread_reply(1001,40),thread_reply(1002,timestamp='bad'),
                 thread_reply(1003,timestamp='2026-11-28T10:00:00'),thread_reply(1004,age=-2),thread_reply(1005)]
        items[-1].pop('timestamp')
        rows,_ = self.read([{'id':'100','timestamp':ago(2)}],{'100':items})
        self.assertEqual([row['id'] for row in rows],['1000'])

    def test_selected_post_has_no_parent_age_requirement_but_filters_its_reply_dates(self):
        source = connectors.validate_source({'platform':'THREADS','resource':'100/replies','authorised':True,'lookback_days':7})
        rows,request = self.read([],{'100':[thread_reply(1000,2),thread_reply(1001,20)]},source)
        self.assertEqual([row['id'] for row in rows],['1000'])
        self.assertEqual(request.call_count,1)
        self.assertTrue(urlsplit(request.call_args.args[0]).path.endswith('/100/replies'))


if __name__ == '__main__':
    unittest.main()
