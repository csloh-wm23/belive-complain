"""Opt-in headless Google capture and native-Hermes public reply rehearsal.

This reads only the selected BeLive sources and writes an isolated private workspace.
It never posts a review response, sends a gateway message or changes the active DB.
"""
import argparse
import copy
import hashlib
import json
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


DEFAULT_REVIEW_URL = 'https://www.google.com/maps/contrib/114279446675905798536/place/ChIJf2EBIq8fMiARfTvF7ZZhmsM/@4.2663822,100.919621,8z/data=!4m6!1m5!8m4!1e1!2s114279446675905798536!3m1!1e1?hl=en&entry=ttu&g_ep=EgoyMDI2MTExNS4wIKXMDSoASAFQAw%3D%3D'


def read_saved(database, review_url=DEFAULT_REVIEW_URL):
    """Discover optional authentic prior captures without creating or copying the active DB."""
    from belive.browser_reviews import review_identity
    result = {'historical': None, 'source_rows': [], 'listing': None, 'alternative_url': None}
    path = Path(database).resolve()
    if not path.is_file():
        return result
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='objects'").fetchone():
            return result
        cases = [json.loads(row[0]) for row in db.execute("SELECT body FROM objects WHERE kind='case'")]
        for case in cases:
            if case.get('platform') != 'GOOGLE':
                continue
            if not result['listing'] and case.get('public_url') and not case.get('review_url'):
                result['listing'] = case['public_url']
            rating = case.get('review_rating')
            if rating not in (1, 2):
                match = re.search(r'\b([12]) stars?\b', case.get('title', ''))
                rating = int(match.group(1)) if match else None
            if not case.get('source_id', '').startswith('google-browser-') or not case.get('review_url') or rating not in (1, 2):
                continue
            if review_identity(case['review_url']) != review_identity(review_url):
                result['alternative_url'] = result['alternative_url'] or case['review_url']
                continue
            versions = case.get('source_versions', [])
            if not versions:
                continue
            rows = [tuple(row) for row in db.execute('SELECT id,platform,source_id,hash,body,created_at FROM sources WHERE id IN (' + ','.join('?' for _ in versions) + ')', versions)]
            if rows:
                result.update(historical=case, source_rows=rows)
    return result


def configured_settings(database):
    from belive import decisions
    from belive.settings import load_settings
    settings = load_settings(database)
    if settings.agent_engine != 'hermes' or settings.llm_provider != 'openai' or settings.llm_model != 'gpt-6-luna' or decisions.enabled(settings):
        raise ValueError('This rehearsal requires native Hermes with the configured OpenAI GPT-6 Luna model and no direct Decisions generation.')
    if not settings.llm_api_key:
        raise ValueError('Save an authorised OpenAI API key in the selected database Connection settings or the private .env before this paid rehearsal.')
    return settings


def isolated_service(database, settings):
    from belive.service import Service
    service = Service(database)
    # Use the selected installation's in-memory model settings; never persist or export its secrets.
    service.settings = settings
    service.ai.settings = settings
    return service


def preview_expectations(service, case_id):
    from belive.workflow import complaint_level
    with service.store.connect() as db:
        case = service.store.get(db, 'case', case_id)
    return complaint_level(case), case.get('staff_destination', 'Support team'), case.get('public_reply_preview', {}).get('text', '')


def safe_error(exc):
    if isinstance(exc,ValueError):return str(exc)[:300]
    return type(exc).__name__+': browser/provider operation did not complete'


def capture_ui(service, directory, case_id):
    """Inspect the actual saved test case in a headless isolated staff dashboard."""
    import secrets
    import threading
    from http.server import ThreadingHTTPServer
    from playwright.sync_api import sync_playwright, expect
    from belive.access import Access
    from server import make_handler
    expected_level, expected_team, expected_preview = preview_expectations(service, case_id)
    if not expected_preview:
        raise ValueError('The saved case has no public preview to inspect.')
    login={'username':'public-rehearsal-reviewer','name':'Public rehearsal reviewer','password':secrets.token_urlsafe(30)}
    access=Access(service)
    if access.users():
        login=json.loads((directory/'operator-login.json').read_text(encoding='utf-8'))
    else:
        access.create(login,bootstrap=True)
        (directory/'operator-login.json').write_text(json.dumps(login,indent=2),encoding='utf-8')
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:'+str(server.server_port)+'/?case='+case_id+'#cases')
            page.locator('#authUsername').fill(login['username']);page.locator('#authPassword').fill(login['password']);page.locator('#authSubmit').click()
            expect(page.locator('#caseDialog')).to_be_visible()
            expect(page.locator('#caseAssessment')).to_contain_text('Complaint Analysis Agent')
            expect(page.locator('#caseDetail')).to_contain_text(expected_level)
            expect(page.locator('#caseDetail')).to_contain_text(expected_team)
            expect(page.locator('#publicReplyText')).to_have_value(expected_preview)
            assert page.get_by_role('button',name='Publish to Google',exact=True).is_disabled()
            page.locator('#caseAssessment').screenshot(path=str(directory/'public-assessment.png'))
            page.locator('#publicReplyText').locator('..').locator('..').screenshot(path=str(directory/'public-reply-preview.png'))
            page.locator('#caseDialog').screenshot(path=str(directory/'public-case-evidence.png'))
            assert not errors, 'Browser errors detected'
            browser.close()
        return {'passed':True,'headless':True,'page_errors':errors,'public_publish_button_disabled':True,'screenshots':['public-assessment.png','public-reply-preview.png','public-case-evidence.png']}
    finally:
        server.shutdown();server.server_close();thread.join()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true',help='Authorise headless public reads and configured paid native-model calls.')
    parser.add_argument('--review-url',default=DEFAULT_REVIEW_URL,help='Individual permitted Google review URL; defaults to the verified BeLive example.')
    parser.add_argument('--capture-ui',action='store_true',help='Save headless screenshots of the isolated saved case after a successful rehearsal.')
    args=parser.parse_args()
    if not args.run_live:
        print('No live action. Use --run-live to read selected public BeLive reviews headlessly and run native Hermes in an isolated workspace.')
        return
    from belive import browser_reviews as browser_reader
    from belive.store import now,redact
    from belive.workflow import complaint_level
    from belive.hermes_native import runtime_info
    from belive.workspace import selected_database
    active_database=selected_database()
    settings=configured_settings(active_database)
    saved=read_saved(active_database,args.review_url)
    historical,listing,source_rows=saved['historical'],saved['listing'],saved['source_rows']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory=ROOT/'artifacts'/'friday-public-rehearsal'/stamp;directory.mkdir(parents=True)
    report={'started_at':now(),'workspace_type':'ISOLATED_TEST_WORKSPACE','headless':True,'native_runtime':runtime_info(),'direct_decisions_enabled':False,'live_reads':{},'external_publication_attempted':False}
    chosen=None
    def save():
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        one=browser_reader.read_browser_review(args.review_url)
        report['live_reads']['original_individual']={'status':'READ','rating':one['rating'],'characters':len(one['description']),'exact_review_link':bool(one.get('review_url'))}
        if one['rating']<=2:chosen=one
    except Exception as exc:
        report['live_reads']['original_individual']={'status':'UNAVAILABLE','error':safe_error(exc)}
    save();print('Original individual review: '+report['live_reads']['original_individual']['status'],flush=True)
    try:
        links=[args.review_url,args.review_url]
        if saved['alternative_url'] and args.review_url==DEFAULT_REVIEW_URL:links.append(saved['alternative_url'])
        captured,skipped=browser_reader.read_browser_review_batch('\n'.join(links))
        report['live_reads']['individual_batch']={'status':'READ','collected':len(captured),'skipped':skipped,'ratings':[x['rating'] for x in captured],'input_duplicate_links':True}
        if not chosen and captured:chosen=captured[0]
    except Exception as exc:
        report['live_reads']['individual_batch']={'status':'UNAVAILABLE','error':safe_error(exc)}
    save();print('Individual batch: '+report['live_reads']['individual_batch']['status'],flush=True)
    if chosen is None and listing and args.review_url==DEFAULT_REVIEW_URL:
        try:
            captured,skipped=browser_reader.read_browser_review_batch(listing)
            report['live_reads']['listing_batch']={'status':'READ','collected':len(captured),'skipped':skipped,'ratings':[x['rating'] for x in captured],'source_link_kind':'LISTING_ONLY'}
            if captured:chosen=captured[0]
        except Exception as exc:
            report['live_reads']['listing_batch']={'status':'UNAVAILABLE','error':safe_error(exc)}
        save();print('Listing batch: '+report['live_reads']['listing_batch']['status'],flush=True)
    if chosen is None and historical is None:
        report.update(status='BLOCKED',finished_at=now(),blocker='No readable low-rated live review and no matching immutable browser capture in this installation. No review text, rating or model output was invented.')
        save();print(json.dumps({'report':str(directory/'report.json'),'status':report['status'],'blocker':report['blocker']},indent=2),flush=True)
        return
    service=isolated_service(directory/'rehearsal.db',settings)
    if chosen:
        chosen={**chosen,'description':redact(chosen['description'])}
        case,created=service.import_browser_review(chosen,'authorised-local-rehearsal')
        report['source']={'kind':'CURRENT_HEADLESS_BROWSER_CAPTURE','rating':chosen['rating'],'source_id':chosen['source_id'],'review_url':chosen.get('review_url'),'listing_url':chosen.get('listing_url'),'text_sha256':hashlib.sha256(chosen['description'].encode()).hexdigest(),'characters':len(chosen['description'])}
    else:
        # Preserve the authentic immutable browser source; do not re-label the manual summary as a capture.
        case=copy.deepcopy(historical)
        for key in ('public_reply_preview','automatic_answer','owner','verification','resolution_feedback','closure_reason','waiting_since','staff_followup','public_guidance_prepared','ai_draft_original'):
            case.pop(key,None)
        case.update(status='AWAITING_CONTACT',severity='UNASSESSED',category='OTHER',analysis=None,handoff=False,review_reason='',draft='',revision=1,rehearsal_workspace=True)
        with service.store.connect() as db:
            db.executemany('INSERT INTO sources(id,platform,source_id,hash,body,created_at) VALUES(?,?,?,?,?,?)',source_rows)
            service.store.put(db,'case',case)
        title_rating=re.search(r'\b([12]) stars?\b',case['title'])
        rating=case.get('review_rating') or (int(title_rating.group(1)) if title_rating else None)
        report['source']={'kind':'HISTORICAL_IMMUTABLE_BROWSER_CAPTURE','original_case_id':historical['id'],'source_id':case['source_id'],'review_url':case['review_url'],'rating':rating,'rating_evidence':'Historical immutable capture title; old numeric rating field was not saved. Not reverified live.','original_source_created_at':source_rows[0][5],'original_source_hash':source_rows[0][3],'characters':len(case['description']),'fresh_crawl':False}
        chosen={'source_id':case['source_id'],'rating':rating,'description':case['description'],'review_url':case['review_url']}
    with service.store.connect() as db:
        original_sources=db.execute('SELECT COUNT(*) FROM sources').fetchone()[0]
        original_cases=len(service.store.all(db,'case'))
    duplicate,duplicate_created=service.import_browser_review(chosen,'authorised-local-repeat-check')
    with service.store.connect() as db:
        duplicate_check=(not duplicate_created and duplicate['id']==case['id'] and db.execute('SELECT COUNT(*) FROM sources').fetchone()[0]==original_sources and len(service.store.all(db,'case'))==original_cases)
    report['duplicate_check']={'same_case':duplicate['id']==case['id'],'created_new_case':duplicate_created,'source_and_case_counts_unchanged':duplicate_check}
    save();print('Native Hermes assessment starting; source='+report['source']['kind'],flush=True)
    job=service.analyse(case['id'])
    with service.store.connect() as db:case=service.store.get(db,'case',case['id'])
    report['assessment']={k:case.get(k) for k in ('id','category','severity','status','staff_destination','review_reason')}
    report['assessment']['complaint_level']=complaint_level(case)
    report['assessment']['job_status']=job['status']
    report['assessment']['job_error']=job.get('error','')
    report['assessment']['analysis']=case.get('analysis')
    if job['status']=='COMPLETED' and (case.get('analysis') or {}).get('report_type')=='COMPLAINT' and not case['analysis'].get('uncertainty'):
        try:report['preview']=service.prepare_public_preview(case['id'],case['revision'],'authorised-local-rehearsal')
        except Exception as exc:report['preview_error']=safe_error(exc)
    with service.store.connect() as db:
        executions=service.store.all(db,'native_execution')
        outbox=service.store.all(db,'outbox')
        messages=service.store.all(db,'message')
    report['native_executions']=executions
    report['checks']={'all_recorded_executors_native':bool(executions) and all(x.get('engine')=='hermes-native' and x.get('agent_class')=='run_agent.AIAgent' for x in executions),'actual_model_calls':sum(x.get('api_calls') or 0 for x in executions),'analysis_agent_ran':any(x.get('role')=='Complaint Analysis Agent' and (x.get('api_calls') or 0)>0 for x in executions),'public_preview_agent_ran':any(x.get('role')=='Public Reply Preview Agent' and (x.get('api_calls') or 0)>0 for x in executions),'duplicate_protected':duplicate_check,'no_customer_response_queued':not any(x.get('kind')=='TENANT_RESPONSE' for x in outbox),'no_platform_send':all(x.get('status') in {'PENDING_APPROVAL','REJECTED'} for x in outbox),'no_published_support_reply':not any(x.get('sender') in {'SUPPORT','AI_SUPPORT'} for x in messages)}
    report['finished_at']=now();save()
    if args.capture_ui and report.get('preview'):
        report['browser_evidence']=capture_ui(service,directory,case['id']);save()
    print(json.dumps({'report':str(directory/'report.json'),'source_kind':report['source']['kind'],'source_rating':report['source']['rating'],'assessment':{k:report['assessment'].get(k) for k in ('id','category','severity','complaint_level','status','staff_destination','job_status','job_error')},'preview':report.get('preview',{}).get('text'),'preview_error':report.get('preview_error'),'checks':report['checks'],'native_roles':[{'role':x.get('role'),'version':x.get('version'),'commit':x.get('commit'),'api_calls':x.get('api_calls')} for x in executions]},ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':main()
