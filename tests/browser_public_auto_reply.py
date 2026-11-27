"""Headless HTTP/UI integration for automatic drafts and reviewed public sending.

Run manually with --output-dir outside this worktree. All cases, model responses,
credentials and platform receipts are fictional. No native model or external API
is called. The existing CDP helper supplies browser transport, not application
behaviour; the real queue, preview validator, HTTP handlers and publishers run.
"""
import argparse
import copy
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import browser_public_reply_flow as helper
from belive import public_preview
from belive.access import Access
from belive.service import Service
from belive.settings import Settings
from server import Tasks, make_handler

ROOT = helper.ROOT
REPLY = 'I am sorry the shared washer is still not spinning. What is its exact brand and model, and is an error code displayed?'
EDITED = 'I am sorry the shared washer is still not spinning. What brand and model is shown on its label?'


class FixtureAI(helper.FixtureAI):
    def __init__(self, home, release, fail_release):
        super().__init__(home)
        self.release = release
        self.fail_release = fail_release

    def generate(self, role, instruction, context, examples):
        if role == 'Public Reply Preview Agent':
            if context['title'].endswith('THREADS'):
                end = time.monotonic() + 40
                while not self.release.exists() and time.monotonic() < end:
                    time.sleep(.05)
                if not self.release.exists():
                    raise AssertionError('Fixture release marker was not written')
            if context['title'].endswith('FAILED'):
                end = time.monotonic() + 40
                while not self.fail_release.exists() and time.monotonic() < end:
                    time.sleep(.05)
                if not self.fail_release.exists():
                    raise AssertionError('Failed fixture release marker was not written')
                self.calls.append({'role': role, 'context': copy.deepcopy(context), 'example_count': len(examples)})
                raise ValueError('AI_UNSAFE_OUTPUT: deliberate fictional generation failure')
        return super().generate(role, instruction, context, examples)


def client():
    prefix = helper.NODE_CLIENT.split('  await selectCase(config.cases.main);')[0]
    prefix = prefix.replace("(public_followup|public-preview)$", "(public_followup|public-preview|public-reply)$")
    prefix = prefix.replace("payload:JSON.parse(p.request.postData||'{}')", "payload:JSON.parse(p.request.postData||'{}'),key:Object.entries(p.request.headers).find(([k])=>k.toLowerCase()==='idempotency-key')?.[1]")
    prefix = prefix.replace("async function shot(name){", "async function shot(name){await evaluate(\"document.querySelector('#caseDetail [data-send-public]')?.closest('section')?.scrollIntoView({block:'start'})\");await delay(100);")
    # Background drafting disables only draft-specific controls. It must not be
    # mistaken for a globally busy page while selecting another source case.
    prefix = prefix.replace("!document.querySelector('#caseDetail [data-public-preview]')?.disabled && !document.querySelector('#caseDetail [data-public-preview]')?.textContent.includes('Checking details')", "!document.querySelector('#authSubmit')?.textContent.includes('Signing')")
    suffix = helper.NODE_CLIENT[helper.NODE_CLIENT.index("}catch(error){results.status='FAIL'"):]
    return prefix + r"""
  await selectCase(config.cases.threads);
  await wait("document.querySelector('#caseDetail [role=status]')?.textContent.includes('preparing') || document.querySelector('#caseDetail').innerText.includes('Preparing')",'automatic running draft');
  check(!await evaluate("!!document.querySelector('#publicReplyText')"),'No editable stale draft while automatic job runs');
  check(await evaluate("document.querySelector('#caseDetail [data-send-public]')?.disabled"),'Send disabled until current draft exists');
  check(!await evaluate("[...document.querySelectorAll('#caseDetail button')].some(b=>b.textContent.trim()==='Prepare reply')"),'Automatic path needs no Prepare click');
  check(await evaluate("!document.querySelector('[data-view=sources]').disabled"),'Background generation does not disable navigation');
  fs.writeFileSync(config.release_file,'release fictional generator');
  await wait("!!document.querySelector('#publicReplyText')",'automatically refreshed draft');
  check(await evaluate("document.querySelector('#publicReplyText').value")===config.reply,'Real preview wrapper saves synthetic draft');
  check(results.requests.filter(x=>x.route==='/api/public-preview').length===0,'Automatic draft appeared without preview POST');
  check(await evaluate("document.querySelector('#caseDetail [data-send-public]').textContent.trim()")==='Send reply to Threads','One destination-specific Send action');
  check(!await evaluate("!!document.querySelector('#googleReplyConfirmed') || !!document.querySelector('#publicReplyConfirmed')"),'No extra approval checkbox');
  check(await evaluate("[...document.querySelectorAll('#caseDetail details')].some(d=>d.querySelector('summary')?.textContent.includes('More reply options')&&!d.open)"),'Rewrite and copy options collapsed');
  fs.writeFileSync(config.send_release_file,'operator is about to press Send');
  await evaluate(`document.querySelector('#publicReplyText').value=${JSON.stringify(config.edited)};document.querySelector('#caseDetail [data-send-public]').click()`);
  await wait("document.querySelector('#caseDetail').innerText.includes('Threads reply: POSTED')",'confirmed Threads fixture receipt');
  await idle('first send');
  let sent=results.requests.filter(x=>x.route==='/api/public-reply');
  check(sent.length===1&&sent[0].payload.text===config.edited&&sent[0].payload.confirmed===true,'Send approves exact edited text');
  check(!!sent[0].key,'Public write includes idempotency key');
  await evaluate(`document.querySelector('#publicReplyText').value=${JSON.stringify(config.edited)};document.querySelector('#caseDetail [data-send-public]').click()`);
  await idle('repeat identical send');
  sent=results.requests.filter(x=>x.route==='/api/public-reply');
  check(sent.length===2&&sent[0].key===sent[1].key,'Identical send reuses stable idempotency key');
  await shot('threads-current-draft-and-receipt');
  for(const [kind,label] of [['facebook','Facebook'],['google','Google']]){
    await selectCase(config.cases[kind]);
    await wait("!!document.querySelector('#publicReplyText')",kind+' automatic draft');
    check(await evaluate("document.querySelector('#caseDetail [data-send-public]').textContent.trim()")==='Send reply to '+label,kind+' destination label');
    await evaluate("document.querySelector('#caseDetail [data-send-public]').click()");
    await wait("document.querySelector('#caseDetail').innerText.includes('confirmed')",kind+' confirmed fixture receipt');
    await idle(kind+' send');
    const last=results.requests.filter(x=>x.route==='/api/public-reply').at(-1);
    check(last.payload.id===config.cases[kind]&&last.response?.status==='POSTED',kind+' selected-case send response');
  }
  await selectCase(config.cases.failed);
  check(!await evaluate("!!document.querySelector('#publicReplyText')"),'Failing job initially has no current draft');
  fs.writeFileSync(config.fail_release_file,'release deliberate fictional failure');
  await wait("[...document.querySelectorAll('#caseDetail [data-public-preview]')].some(b=>b.textContent.trim()==='Retry draft')",'failed generation rendered by polling');
  check(await evaluate("document.querySelector('#caseDetail [data-send-public]').disabled"),'Failed generation cannot be sent');
  check(!await evaluate("!!document.querySelector('#publicReplyText')"),'Failed generation has no current editable draft');
  await shot('automatic-draft-failure');
  check(results.javascript_errors.length===0,'No browser JavaScript errors');
  check(results.external_requests_blocked.length===0,'Browser contacted only isolated localhost');
  results.status='PASS';
""" + suffix


def seed(service, kind):
    platform = kind.upper() if kind != 'failed' else 'GOOGLE'
    target = {'THREADS': '702', 'FACEBOOK': '900_901', 'GOOGLE': 'accounts/111/locations/222/reviews/rev-333'}[platform]
    if kind == 'failed':
        target = 'accounts/111/locations/222/reviews/rev-failed'
    case = service.command('intake', {'title': 'Fictional automatic draft ' + kind.upper(),
        'description': 'The shared washer will not spin after an earlier report.',
        'platform': platform, 'source_id': target}, 'fixture-intake-' + kind)
    case.update(category='MAINTENANCE', severity='MEDIUM',
        analysis={'report_type': 'COMPLAINT', 'relevance': 'SUPPORT', 'severity': 'MEDIUM',
                  'requires_human': True, 'uncertainty': False, 'summary': 'A fictional unresolved washer fault.',
                  'evidence': case['description']})
    if platform == 'THREADS':
        case['parent_source_id'] = '701'
    with service.store.connect() as db:
        service.handoff(db, case, 'Fictional fixture requires staff investigation.')
        case.update(status='HUMAN_REVIEW', draft='Existing staff wording remains unchanged.')
        service.store.put(db, 'case', case)
        resource = {'THREADS': '700/threads', 'FACEBOOK': '900/feed', 'GOOGLE': 'accounts/111/locations/222'}[platform]
        service.store.put(db, 'source', {'id': 'SRC-' + platform, 'platform': platform,
            'resource': resource, 'authorised': True, 'enabled': True})
    return case


def run(output):
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Keep private artifacts outside the worktree')
    output.mkdir(parents=True, exist_ok=True)
    node, browser = shutil.which('node'), helper.browser_executable()
    if not node or not browser:
        raise RuntimeError('Chrome/Edge and Node 22+ are required')
    result = {'status': 'FAIL', 'fixture_only': True, 'real_model_calls': 0, 'real_platform_requests': 0}
    with tempfile.TemporaryDirectory(prefix='belive-auto-ui-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        release, fail_release, send_release = (temp / name for name in ('release-fixture', 'release-failure', 'release-send'))
        ai = FixtureAI(temp / 'memory', release, fail_release)
        settings = Settings(llm_model='fixture-no-model', llm_api_key='')
        platform_calls = []

        def platform_api(url, token='', payload=None, method=None, **kwargs):
            assert send_release.exists(), 'Automatic drafting must not call a publishing platform'
            platform_calls.append({'url': url, 'payload': payload, 'method': method})
            path = urlsplit(url).path
            if 'mybusiness.googleapis.com' in url:
                if payload is not None:
                    assert path.endswith('/reviews/rev-333/reply') and method == 'PUT'
                    return {'comment': payload['comment'], 'updateTime': '2026-11-28T00:00:00Z'}
                return {'name': 'accounts/111/locations/222/reviews/rev-333',
                        'comment': 'The shared washer will not spin after an earlier report.'}
            if payload is not None:
                if path.endswith('/700/threads'):
                    assert payload['reply_to_id'] == '702' and payload['text'] == EDITED
                    return {'id': '710'}
                if path.endswith('/700/threads_publish'):
                    assert payload == {'creation_id': '710'}
                    return {'id': '711'}
                if path.endswith('/900_901/comments'):
                    return {'id': '900_902'}
                raise AssertionError('Unexpected fixture write ' + url)
            if path.endswith('/me'):
                return {'id': '700' if 'threads.com' in url else '900', 'name': 'Fixture Page',
                        'username': 'fixture', 'category': 'Fictional test Page'}
            if path.endswith('/701'):
                return {'id': '701', 'owner': {'id': '700'}}
            if path.endswith('/701/replies'):
                return {'data': [{'id': '702', 'text': 'The shared washer will not spin after an earlier report.'}]}
            if path.endswith('/710'):
                return {'id': '710', 'status': 'FINISHED'}
            if path.endswith('/900_901'):
                return {'id': '900_901', 'from': {'id': '900'}, 'message': 'The shared washer will not spin after an earlier report.'}
            raise AssertionError('Unexpected fixture read ' + url)

        token = lambda name, **kw: 'v27.0' if name == 'BELIVE_FACEBOOK_VERSION' else 'fixture-only-token'
        with patch('belive.service.load_settings', return_value=settings), patch('belive.credentials.apply'), \
             patch('belive.ai.native_request', side_effect=AssertionError('Native model forbidden')), \
             patch('belive.whatsapp_ai.research', side_effect=AssertionError('Manufacturer network forbidden')), \
             patch('belive.public_replies.get_value', side_effect=token), \
             patch('belive.google_replies.get_value', side_effect=token), \
             patch('belive.public_replies.request_json', side_effect=platform_api), \
             patch('belive.google_replies.request_json', side_effect=platform_api), \
             patch.dict(os.environ, {'BELIVE_GOOGLE_REPLY_ENABLED': 'true'}):
            service = Service(temp / 'isolated.db', ai)
            username, password = 'fixture-operator', 'Private-fixture-password-123'
            Access(service).create({'username': username, 'password': password, 'name': 'Fictional UI Operator'}, bootstrap=True)
            cases = {kind: seed(service, kind) for kind in ('threads', 'facebook', 'google', 'failed')}
            with service.store.connect() as db:
                before = {k: copy.deepcopy(service.store.get(db, 'case', c['id'])) for k, c in cases.items()}
                sources = [tuple(r) for r in db.execute('SELECT * FROM sources ORDER BY id')]
                outbox, messages = service.store.all(db, 'outbox'), service.store.all(db, 'message')
            tasks = Tasks(service)
            tasks.analyse(cases['threads'])
            tasks.analyse(cases['facebook'])
            tasks.analyse(cases['google'])
            def pump():
                while not tasks.stop.wait(.2):
                    tasks.public_drafts(backfill=True)
            worker = threading.Thread(target=pump, daemon=True);worker.start()
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service, tasks))
            thread = threading.Thread(target=httpd.serve_forever, daemon=True);thread.start()
            chrome = None
            log = (output / 'chrome-startup.log').open('wb')
            try:
                profile = temp / 'chrome-profile'
                chrome = subprocess.Popen([str(browser), '--headless=new', '--remote-debugging-port=0',
                    '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check',
                    '--disable-background-networking', '--disable-component-update', '--disable-sync',
                    '--disable-extensions', '--disable-default-apps', '--metrics-recording-only',
                    '--disable-features=OptimizationHints,MediaRouter', 'about:blank'], stdout=log,
                    stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                config = dict(base='http://127.0.0.1:' + str(httpd.server_port), username=username,
                    password=password, profile=str(profile), output=str(output), release_file=str(release),
                    fail_release_file=str(fail_release), send_release_file=str(send_release),
                    reply=REPLY, edited=EDITED, cases={k: c['id'] for k, c in cases.items()})
                (temp / 'config.json').write_text(json.dumps(config), encoding='utf-8')
                (temp / 'client.mjs').write_text(client(), encoding='utf-8')
                completed = subprocess.run([node, str(temp / 'client.mjs'), str(temp / 'config.json')],
                    capture_output=True, text=True, timeout=110, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                browser_result = json.loads((output / 'browser-results.json').read_text(encoding='utf-8'))
                result['browser'] = browser_result
                if completed.returncode:
                    raise AssertionError(browser_result.get('error') or completed.stderr)
                with service.store.connect() as db:
                    after = {k: service.store.get(db, 'case', c['id']) for k, c in cases.items()}
                    for kind in cases:
                        allowed = {'revision', 'public_reply_preview', 'public_reply', 'google_reply', 'updated_at'}
                        assert {k: v for k, v in before[kind].items() if k not in allowed} == {k: v for k, v in after[kind].items() if k not in allowed}, kind
                    assert service.store.all(db, 'outbox') == outbox and service.store.all(db, 'message') == messages
                    assert [tuple(r) for r in db.execute('SELECT * FROM sources ORDER BY id')] == sources
                    assert all(after[k]['public_reply']['status'] == 'POSTED' for k in ('threads', 'facebook', 'google'))
                    assert not after['failed'].get('public_reply')
                writes = [c for c in platform_calls if c['payload'] is not None]
                assert len(writes) == 4, writes
                assert writes[0]['payload']['reply_to_id'] == '702'
                assert writes[1]['payload'] == {'creation_id': '710'}
                assert writes[2]['url'].endswith('/900_901/comments')
                assert writes[3]['url'].endswith('/reviews/rev-333/reply')
                result.update(status='PASS', checks=['Automatic current draft via persisted queue and UI polling',
                    'Single operator Send, edited text and stable repeated idempotency key',
                    'Real exact-source Threads/Facebook/Google publisher paths with synthetic transport',
                    'Failed draft retained and Send blocked', 'Staff fields, source versions, messages and outbox preserved'],
                    platform_calls=platform_calls, ai_roles=[c['role'] for c in ai.calls])
            finally:
                release.touch();fail_release.touch();tasks.stop.set();worker.join(3)
                httpd.shutdown();httpd.server_close();thread.join(5)
                if chrome and chrome.poll() is None:
                    chrome.terminate()
                    try: chrome.wait(10)
                    except subprocess.TimeoutExpired: chrome.kill();chrome.wait(5)
                log.close()
                (output / 'platform-fixture-calls.json').write_text(json.dumps(platform_calls, indent=2), encoding='utf-8')
                with service.store.connect() as db:
                    diagnostics = {k: {'case': service.store.get(db, 'case', c['id']),
                        'job': next((j for j in service.store.all(db, 'public_draft_job') if j['id'] == c['id']), None)} for k, c in cases.items()}
                (output / 'fixture-diagnostics.json').write_text(json.dumps(diagnostics, indent=2), encoding='utf-8')
    (output / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent / 'browser-auto-reply-flow')
    args = parser.parse_args()
    try:
        report = run(args.output_dir)
    except Exception as error:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report = {'status': 'FAIL', 'fixture_only': True, 'error': str(error)}
        (args.output_dir / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2));raise SystemExit(1)
    print(json.dumps({'status': report['status'], 'browser_checks': len(report['browser']['checks']), 'output': str(args.output_dir.resolve())}, indent=2))
