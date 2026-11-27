"""Run the real public-reply UI against an isolated localhost fixture service.

Manual integration check, deliberately outside test_*.py discovery. Requires Node
22+ (built-in WebSocket) and installed Chrome/Edge, not a third-party browser SDK.
All model/research responses are synthetic. No native model or manufacturer call
is made. Artifacts belong outside the worktree and contain fictional cases only.
"""
import argparse
import copy
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from belive.access import Access
from belive.ai import SupportAI
from belive.service import Service
from belive.settings import Settings
from belive import public_preview
from server import Tasks, make_handler


SOURCE_URL = 'https://www.samsung.com/support/fixture-ww80t554dan-4c/'
FOLLOWUP = 'It is a Samsung WW80T554DAN washer showing 4C. I already checked the external tap.'
RESEARCHED_REPLY = (
    'I am sorry the shared washer is still not spinning after your earlier report. '
    'For the Samsung WW80T554DAN showing 4C, the supplied fixture evidence supports '
    'only observing the external hose without moving or opening the machine. '
    'Since you already checked the external tap, is the visible hose kinked?'
)


class FixtureAI(SupportAI):
    """Keep real public reply validation; replace the transport boundary only."""
    def __init__(self, home):
        super().__init__(Settings(llm_model='fixture-no-model', llm_api_key=''), home)
        self.calls = []

    def readiness(self):
        return True

    def generate(self, role, instruction, context, examples):
        self.calls.append({'role': role, 'context': copy.deepcopy(context),
                           'example_count': len(examples)})
        if role == 'Public Diagnostic Details Agent':
            return dict(device='WASHING_MACHINE', brand='Samsung', model='WW80T554DAN',
                        error_code='4C', ready=True)
        if role == 'Public Diagnostic Safety Agent':
            return dict(safe=True, grounded=True, model_compatible=True,
                        uncertainty=False, unsupported_claims=[])
        if role == 'Public Reply Preview Agent':
            if context.get('research_state') == 'STAFF_ONLY':
                return {'reply': 'The reported smoke needs urgent staff attention. Please keep away from the equipment and do not try to inspect or repair it yourself.'}
            if context.get('research_state') == 'RESEARCH_READY':
                return {'reply': RESEARCHED_REPLY}
            return {'reply': 'I am sorry the shared washer is still not spinning. What is its exact brand and model, and is an error code displayed?'}
        raise AssertionError('Unexpected fixture AI role: ' + role)


NODE_CLIENT = r"""
import fs from 'node:fs';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const results={checks:[],requests:[],external_requests_blocked:[],javascript_errors:[]};
let ws,chrome;
const pending=new Map(),mutations=new Map(),inflight=new Set();let nextId=0;
function check(condition,name,detail){if(!condition)throw new Error(name+': '+JSON.stringify(detail));results.checks.push({name,status:'PASS',detail});}
function send(method,params={}){
  const id=++nextId;
  return new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout '+method));},15000);
    pending.set(id,{resolve,reject,timeout});ws.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression){
  const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  if(value.exceptionDetails)throw new Error('Browser evaluate: '+JSON.stringify(value.exceptionDetails));
  return value.result.value;
}
async function wait(expression,label){
  const end=Date.now()+20000;
  while(Date.now()<end){if(await evaluate(expression))return;await delay(80);}
  throw new Error('Timed out: '+label+'; case error: '+await evaluate("document.querySelector('#caseError')?.textContent||''")+'; '+await evaluate("document.body.innerText.slice(-1800)"));
}
async function idle(label){
  const end=Date.now()+20000;let quiet=0;
  while(Date.now()<end){
    const ready=await evaluate("!document.querySelector('#caseDetail [data-public-preview]')?.disabled && !document.querySelector('#caseDetail [data-public-preview]')?.textContent.includes('Checking details')");
    quiet=inflight.size===0&&ready?quiet+1:0;
    if(quiet>=2)return;
    await delay(80);
  }
  throw new Error('UI did not settle: '+label+'; pending API requests: '+inflight.size);
}
async function completedPreview(id){
  const end=Date.now()+20000;
  while(Date.now()<end){
    const entry=results.requests.findLast(x=>x.route==='/api/public-preview'&&x.payload.id===id);
    if(entry&&entry.response!==undefined){
      if(entry.status!==200)throw new Error('Preview HTTP failure: '+JSON.stringify(entry));
      return;
    }
    await delay(80);
  }
  throw new Error('Preview response unavailable: '+JSON.stringify(results.requests.at(-1)));
}
async function shot(name){
  const value=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync(path.join(config.output,name+'.png'),Buffer.from(value.data,'base64'));
}
async function selectCase(id){
  await idle('before selecting '+id);
  await evaluate(`document.querySelector('#caseDialog')?.close();document.querySelector('[data-view="sources"]').click()`);
  await wait(`!!document.querySelector('#discoveryFindings [data-case="${id}"]')`,'source card '+id);
  await evaluate(`document.querySelector('#discoveryFindings [data-case="${id}"]').click()`);
  await wait(`document.querySelector('#caseDialog').open && document.querySelector('#caseDetail').innerText.includes('${id}')`,'case detail '+id);
  await idle('selected '+id);
}
async function apiPreview(id){
  return await evaluate(`(async()=>{const h={'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content,'Idempotency-Key':crypto.randomUUID()};const s=await fetch('/api/status',{headers:h}).then(r=>r.json());const c=s.cases.find(c=>c.id===${JSON.stringify(id)});const r=await fetch('/api/public-preview',{method:'POST',headers:h,body:JSON.stringify({id:c.id,revision:c.revision})});return {status:r.status,body:await r.json()};})()`);
}

try{
  // Launch is delegated to Python so Windows never gets an interactive window.
  let devtools;
  for(let i=0;i<200;i++){
    try{const lines=fs.readFileSync(path.join(config.profile,'DevToolsActivePort'),'utf8').trim().split('\n').map(line=>line.trim());devtools=lines;break;}catch{}
    await delay(50);
  }
  if(!devtools)throw new Error('Headless browser did not expose DevToolsActivePort');
  const tabs=await fetch('http://127.0.0.1:'+devtools[0]+'/json/list').then(r=>r.json());
  const tab=tabs.find(t=>t.type==='page');if(!tab)throw new Error('No headless page');
  ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  ws.addEventListener('message',event=>{
    const message=JSON.parse(event.data);
    if(message.id){const p=pending.get(message.id);if(!p)return;clearTimeout(p.timeout);pending.delete(message.id);message.error?p.reject(new Error(JSON.stringify(message.error))):p.resolve(message.result);return;}
    const p=message.params||{};
    if(message.method==='Network.requestWillBeSent'&&p.request.url.startsWith(config.base+'/api/'))inflight.add(p.requestId);
    if(message.method==='Network.loadingFinished'||message.method==='Network.loadingFailed')inflight.delete(p.requestId);
    if(message.method==='Fetch.requestPaused'){
      if(p.request.url.startsWith(config.base+'/')||p.request.url.startsWith('data:'))send('Fetch.continueRequest',{requestId:p.requestId}).catch(()=>{});
      else{results.external_requests_blocked.push(p.request.url);send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'}).catch(()=>{});}
    }
    if(message.method==='Network.requestWillBeSent' && p.request.method==='POST' && /\/api\/(public_followup|public-preview)$/.test(p.request.url)){
      const entry={route:new URL(p.request.url).pathname,payload:JSON.parse(p.request.postData||'{}')};
      results.requests.push(entry);mutations.set(p.requestId,entry);
    }
    if(message.method==='Network.responseReceived'&&mutations.has(p.requestId))mutations.get(p.requestId).status=p.response.status;
    if(message.method==='Network.loadingFinished'&&mutations.has(p.requestId)){
      send('Network.getResponseBody',{requestId:p.requestId}).then(body=>{
        try{mutations.get(p.requestId).response=JSON.parse(body.body);}catch{mutations.get(p.requestId).response=body.body.slice(0,500);}
      }).catch(error=>{mutations.get(p.requestId).response_error=String(error);});
    }
    if(message.method==='Runtime.exceptionThrown')results.javascript_errors.push(p.exceptionDetails);
  });
  await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
  await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:config.base+'/'});
  await wait("!document.querySelector('#authGate')?.hidden && document.querySelector('#authUsername')",'login form');
  await evaluate(`document.querySelector('#authUsername').value=${JSON.stringify(config.username)};document.querySelector('#authPassword').value=${JSON.stringify(config.password)};document.querySelector('#authSubmit').click()`);
  await wait("!document.querySelector('#operatorApp').hidden",'authenticated operator app');
  check(await evaluate("document.querySelector('#authGate').hidden"),'actual HTTP operator login');

  await selectCase(config.cases.main);
  check(await evaluate("document.querySelector('#caseDetail').innerText.includes('This is an earlier draft.')"),'old preview version warning');
  check(await evaluate("document.querySelector('[data-public-preview]').textContent==='Rewrite reply'"),'single Rewrite reply button');
  check(await evaluate("document.querySelector('#caseDetail').innerText.includes('Earlier draft by')"),'earlier draft attribution');
  await shot('01-earlier-draft');
  await evaluate(`document.querySelector('#publicFollowupText').closest('details').open=true;document.querySelector('#publicFollowupText').value=${JSON.stringify(config.followup)};document.querySelector('#publicFollowupText').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#publicFollowupLink').value='https://www.google.com/maps/reviews/fixture-observed-reply';document.querySelector('[data-public-preview]').click()`);
  await completedPreview(config.cases.main);
  await wait("document.querySelector('#publicReplyText')?.value.includes('WW80T554DAN') && document.querySelector('#caseDetail').innerText.includes('Manufacturer sources used')",'researched rewrite');
  await idle('researched rewrite complete');
  const pair=results.requests.slice(0,2);
  check(pair.length===2&&pair[0].route==='/api/public_followup'&&pair[1].route==='/api/public-preview','UI sends follow-up then preview',pair);
  check(pair[0].payload.id===pair[1].payload.id&&pair[1].payload.revision===pair[0].payload.revision+1,'preview uses refreshed follow-up revision',pair.map(x=>x.payload.revision));
  check(pair[0].payload.text===config.followup,'observed follow-up payload');
  check(await evaluate("!document.querySelector('#caseDetail').innerText.includes('This is an earlier draft.') && !document.querySelector('#caseDetail').innerText.includes('Earlier draft by')"),'fresh draft clears earlier labels');
  check(await evaluate(`!!document.querySelector('#caseDetail a[href="${config.source_url}"][target="_blank"][rel="noopener noreferrer"]')`),'manufacturer citation link');
  check(await evaluate("document.querySelector('#caseDetail').innerText.includes('Customer follow-ups (1)')"),'saved follow-up rendered');
  check(await evaluate("document.querySelector('#publicFollowupText').value===''") ,'recorded input cleared');
  await shot('02-researched-rewrite');

  await selectCase(config.cases.fresh);
  check(await evaluate("document.querySelector('[data-public-preview]').textContent==='Prepare reply'"),'fresh case uses Prepare reply');
  const beforeFresh=results.requests.length;
  await evaluate("document.querySelector('[data-public-preview]').click()");
  await completedPreview(config.cases.fresh);
  await wait("document.querySelector('#publicReplyText')?.value.includes('exact brand and model')",'clarifying draft');
  await idle('clarifying draft complete');
  check(results.requests.length===beforeFresh+1&&results.requests.at(-1).route==='/api/public-preview','no follow-up sends only preview');
  check(await evaluate("!document.querySelector('#caseDetail').innerText.includes('Manufacturer sources used')"),'missing details show no manufacturer citations');

  for(const kind of ['closed','verified','uncertain','enquiry']){
    await selectCase(config.cases[kind]);
    check(await evaluate("!document.querySelector('[data-public-preview]')"),'generation hidden for '+kind);
    const denied=await apiPreview(config.cases[kind]);
    check(denied.status===400,'server rejects '+kind,denied.body);
  }

  await selectCase(config.cases.danger);
  check(await evaluate("!!document.querySelector('[data-public-preview]')"),'urgent case permits acknowledgement only');
  await evaluate("document.querySelector('[data-public-preview]').click()");
  await completedPreview(config.cases.danger);
  await wait("document.querySelector('#publicReplyText')?.value.includes('urgent staff attention')",'urgent acknowledgement');
  await idle('urgent acknowledgement complete');
  check(await evaluate("document.querySelector('#caseDetail').innerText.includes('routine troubleshooting is paused')"),'urgent state displays STAFF_ONLY');
  check(await evaluate("!document.querySelector('#caseDetail').innerText.includes('Manufacturer sources used')"),'urgent case has no research citations');
  await shot('03-urgent-acknowledgement');
  check(results.javascript_errors.length===0,'no uncaught browser JavaScript errors',results.javascript_errors);
  results.status='PASS';
}catch(error){results.status='FAIL';results.error=error.stack||String(error);if(ws?.readyState===WebSocket.OPEN){try{await shot('failure');}catch{}}process.exitCode=1;}
finally{
  fs.writeFileSync(path.join(config.output,'browser-results.json'),JSON.stringify(results,null,2));
  // Close this isolated browser through its own CDP connection, not other Chrome processes.
  if(ws?.readyState===WebSocket.OPEN){try{await Promise.race([send('Browser.close'),delay(750)]);}catch{}}
  if(ws)ws.close();
  for(const p of pending.values()){clearTimeout(p.timeout);p.reject(new Error('CDP closed'));}
}
"""


def browser_executable():
    configured = os.environ.get('BELIVE_TEST_CHROME')
    candidates = [configured] if configured else []
    for base in (os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', '')):
        candidates += [str(Path(base) / 'Google/Chrome/Application/chrome.exe'),
                       str(Path(base) / 'Microsoft/Edge/Application/msedge.exe')]
    candidates += [shutil.which(x) for x in ('google-chrome', 'chromium', 'chromium-browser')]
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


def seed(service, name, *, status='HUMAN_REVIEW', uncertain=False, report_type='COMPLAINT', danger=False, old=False):
    case = service.command('intake', {
        'title': 'Fictional UI ' + name + ' washer case',
        'description': 'Smoke is coming from the fictional washer.' if danger else 'The shared washer will not spin after an earlier report.',
        'platform': 'GOOGLE', 'source_id': 'fictional-ui-' + name,
    }, 'fixture-intake-' + name)
    case.update(category='MAINTENANCE', severity='CRITICAL' if danger else 'MEDIUM',
                analysis={'report_type': report_type, 'relevance': 'SUPPORT',
                          'severity': 'CRITICAL' if danger else 'MEDIUM', 'requires_human': True,
                          'uncertainty': uncertain, 'summary': 'A fictional unresolved washer fault.',
                          'evidence': case['description']})
    with service.store.connect() as db:
        if not danger:
            service.handoff(db, case, 'Fictional UI fixture requires staff investigation.')
        case.update(status=status, draft='Existing suggested wording must remain unchanged.')
        if old:
            case['public_reply_preview'] = {
                'text': 'Old fixture draft: what is the brand and model?',
                'agent': 'Earlier fixture preview', 'source_version': case['source_versions'][-1],
                'format_version': public_preview.VERSION - 1,
                'input_fingerprint': public_preview.fingerprint(public_preview.context(case)),
            }
        service.store.put(db, 'case', case)
    return case


def run(output):
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Keep private browser artifacts outside the worktree')
    output.mkdir(parents=True, exist_ok=True)
    browser = browser_executable()
    node = shutil.which('node')
    if not browser or not node:
        raise RuntimeError('Install Chrome/Edge and Node 22+ or set BELIVE_TEST_CHROME')
    result = {'status': 'FAIL', 'fixture_only': True, 'real_model_calls': 0,
              'real_manufacturer_requests': 0, 'checks': []}
    # Windows Chrome may release cache journals after its parent exits. A leftover
    # temporary fixture file must not replace an assertion failure or successful result.
    with tempfile.TemporaryDirectory(prefix='belive-public-ui-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        ai = FixtureAI(temp / 'memory')
        settings = Settings(llm_model='fixture-no-model', llm_api_key='')
        research_calls = []

        def research(_service, query, kind):
            research_calls.append({'query': query, 'kind': kind})
            return {'summary': 'Synthetic fixture evidence for Samsung WW80T554DAN error 4C: observe only the external hose; no moving or opening equipment.',
                    'sources': [{'id': 'FIXTURE-MANUFACTURER', 'url': SOURCE_URL,
                                 'title': 'Synthetic Samsung WW80T554DAN 4C manufacturer fixture'}]}

        with patch('belive.service.load_settings', return_value=settings), \
             patch('belive.credentials.apply'), \
             patch('belive.whatsapp_ai.research', side_effect=research), \
             patch('belive.ai.native_request', side_effect=AssertionError('Real native transport is forbidden in this fixture test')):
            service = Service(temp / 'isolated.db', ai)
            username, password = 'fixture-operator', 'Private-fixture-password-123'
            Access(service).create({'username': username, 'password': password,
                                    'name': 'Fictional UI Operator'}, bootstrap=True)
            cases = {kind: seed(service, kind, **changes) for kind, changes in {
                'main': {'old': True}, 'fresh': {}, 'closed': {'status': 'CLOSED'},
                'verified': {'status': 'VERIFIED'}, 'uncertain': {'uncertain': True},
                'enquiry': {'report_type': 'ENQUIRY'}, 'danger': {'danger': True},
            }.items()}
            with service.store.connect() as db:
                before = {kind: copy.deepcopy(service.store.get(db, 'case', c['id'])) for kind, c in cases.items()}
                outbox_before = service.store.all(db, 'outbox')
                messages_before = service.store.all(db, 'message')
                sources_before = [tuple(r) for r in db.execute('SELECT * FROM sources ORDER BY id')]
            tasks = Tasks(service)
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service, tasks))
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            chrome = None
            chrome_log = (output / 'chrome-startup.log').open('wb')
            try:
                profile = temp / 'chrome-profile'
                args = [str(browser), '--headless=new', '--remote-debugging-port=0',
                        '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check',
                        '--disable-background-networking', '--disable-component-update', '--disable-sync',
                        '--disable-extensions', '--disable-default-apps', '--metrics-recording-only',
                        '--disable-features=OptimizationHints,MediaRouter', 'about:blank']
                chrome = subprocess.Popen(args, stdout=chrome_log, stderr=subprocess.STDOUT,
                                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                config = {'base': 'http://127.0.0.1:' + str(httpd.server_port),
                          'username': username, 'password': password, 'profile': str(profile),
                          'output': str(output), 'followup': FOLLOWUP, 'source_url': SOURCE_URL,
                          'cases': {kind: c['id'] for kind, c in cases.items()}}
                config_path, client_path = temp / 'config.json', temp / 'client.mjs'
                config_path.write_text(json.dumps(config), encoding='utf-8')
                client_path.write_text(NODE_CLIENT, encoding='utf-8')
                completed = subprocess.run([node, str(client_path), str(config_path)],
                                           capture_output=True, text=True, timeout=100,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                result['browser'] = json.loads((output / 'browser-results.json').read_text(encoding='utf-8'))
                if completed.returncode:
                    raise AssertionError(result['browser'].get('error') or completed.stderr)
                with service.store.connect() as db:
                    after = {kind: service.store.get(db, 'case', c['id']) for kind, c in cases.items()}
                    followups = service.public_followups(db, cases['main']['id'])
                    assert len(followups) == 1 and followups[0]['text'] == FOLLOWUP
                    assert after['main']['public_reply_preview']['text'] == RESEARCHED_REPLY
                    assert after['main']['public_reply_preview']['research_state'] == 'RESEARCH_READY'
                    assert public_preview.is_current(after['main'], followups)
                    assert after['main']['revision'] == before['main']['revision'] + 2
                    for kind in cases:
                        allowed = {'revision', 'public_reply_preview'} if kind in {'fresh', 'danger'} else {'revision', 'public_reply_preview', 'updated_at'} if kind == 'main' else set()
                        assert {k: v for k, v in before[kind].items() if k not in allowed} == {k: v for k, v in after[kind].items() if k not in allowed}, kind
                    assert service.store.all(db, 'outbox') == outbox_before
                    assert service.store.all(db, 'message') == messages_before
                    assert [tuple(r) for r in db.execute('SELECT * FROM sources ORDER BY id')] == sources_before
                    assert after['danger']['public_reply_preview']['research_state'] == 'STAFF_ONLY'
                assert len(research_calls) == 1, research_calls
                expected_roles = ['Public Diagnostic Details Agent', 'Public Reply Preview Agent',
                                  'Public Diagnostic Safety Agent', 'Public Reply Preview Agent',
                                  'Public Reply Preview Agent']
                assert [c['role'] for c in ai.calls] == expected_roles, [c['role'] for c in ai.calls]
                assert ai.calls[0]['context']['public_followups'][0]['text'] == FOLLOWUP
                assert all(c['example_count'] == 0 for c in ai.calls)
                result.update(status='PASS', checks=[
                    'Real HTTP login and operator UI flow', 'Follow-up saved before preview with refreshed revision',
                    'Actual public preview and diagnostic validation with synthetic transport',
                    'Manufacturer sources and current/earlier labels rendered',
                    'Inactive, uncertain and non-complaint generation gated in UI and server',
                    'HIGH safety state uses acknowledgement only without research',
                    'All operational fields, source rows, messages and outbox preserved',
                ], ai_roles=[c['role'] for c in ai.calls], research_calls=research_calls,
                    case_ids={kind: c['id'] for kind, c in cases.items()})
            finally:
                # Preserve fixture diagnostics even if a browser assertion fails.
                diagnostics = {'ai_roles': [call['role'] for call in ai.calls],
                               'research_calls': research_calls, 'cases': {}}
                with service.store.connect() as db:
                    for kind, fixture in cases.items():
                        saved = service.store.get(db, 'case', fixture['id'])
                        diagnostics['cases'][kind] = {
                            'id': saved['id'], 'revision': saved['revision'],
                            'status': saved['status'], 'preview': saved.get('public_reply_preview'),
                        }
                (output / 'python-diagnostics.json').write_text(
                    json.dumps(diagnostics, indent=2), encoding='utf-8')
                tasks.stop.set()
                httpd.shutdown(); httpd.server_close(); thread.join(5)
                if chrome and chrome.poll() is None:
                    chrome.terminate()
                    try: chrome.wait(10)
                    except subprocess.TimeoutExpired: chrome.kill(); chrome.wait(5)
                chrome_log.close()
    (output / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent / 'browser-public-reply-flow')
    args = parser.parse_args()
    try:
        report = run(args.output_dir)
    except Exception as error:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report = {'status': 'FAIL', 'fixture_only': True, 'error': str(error)}
        (args.output_dir / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']),
                      'output': str(args.output_dir.resolve())}, indent=2))
