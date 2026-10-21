"""Local UI integration QA. Fixtures and FakeAI exist only inside a temporary database."""
import sys
import tempfile
import threading
from datetime import datetime,timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from server import make_handler
from belive.service import Service,MY
from test_backend import FakeAI

def main():
    output=ROOT/'artifacts';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'browser.db',FakeAI())
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1100})
                page=context.new_page();errors=[];external=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:external.append(r.url) if not r.url.startswith(url) else None)
                page.goto(url);expect(page.locator('.metric')).to_have_count(4)
                assert page.locator('[data-view="marketing"], [data-view="sales"], [data-view="owners"]').count()==0
                page.locator('[data-view="settings"]').click()
                def submit(form_id,values,checks=()):
                    form=page.locator('#'+form_id)
                    for name,value in values.items():
                        el=form.locator('[name="'+name+'"]')
                        if el.evaluate('(e)=>e.tagName')=='SELECT':el.select_option(value)
                        else:el.fill(value)
                    for name in checks:form.locator('[name="'+name+'"]').check()
                    with page.expect_response(lambda r:'/api/' in r.url and r.request.method=='POST') as result:form.locator('button').last.click()
                    assert result.value.ok,result.value.text()
                    expect(form.locator('input').first).to_have_value('') if form_id not in ['moveForm'] else None
                submit('condoForm',dict(id='C-QA',name='Fictional QA condo',days='0,1,2,3,4,5,6',start='08:00',end='18:00',rules='Fictional QA rules: reserve the lift during the recorded window.',checklist='Keys checked\nRoom condition recorded'),['confirmed'])
                submit('tenantForm',dict(id='T-QA',condo_id='C-QA',unit_ref='U-QA',verified_by='QA operator',evidence='Fictional test tenancy checked.'),['confirmed'])
                day=(datetime.now(MY)+timedelta(days=2)).strftime('%Y-%m-%d')
                submit('staffForm',dict(id='P-QA',name='QA PIC',condos='C-QA',days='0,1,2,3,4,5,6',from_date=day,until_date=day),['enabled'])
                expect(page.locator('#resources')).to_contain_text('1 verified tenants')
                page.locator('[data-view="moves"]').click()
                form=page.locator('#moveForm');form.locator('[name="tenant_id"]').select_option('T-QA');form.locator('[name="at"]').fill(day+'T10:00')
                form.locator('button').click();expect(page.locator('#movesList')).to_contain_text('P-QA')
                assert len(service.snapshot()['moves'][0]['checklist'])==2
                page.screenshot(path=str(output/'tenant-moves-desktop.png'),full_page=True)
                page.locator('#newCase').click();form=page.locator('#intakeForm')
                form.locator('[name="title"]').fill('Fictional room Wi-Fi enquiry')
                form.locator('[name="description"]').fill('My room Wi-Fi drops each evening. This is a QA fixture.')
                form.locator('[name="tenant_id"]').select_option('T-QA');form.locator('button.primary').click()
                expect(page.locator('#caseDialog')).to_be_visible()
                page.locator('#reloadCase').click()
                expect(page.locator('#caseDraft')).to_have_value('Could you confirm whether other devices have the same issue?')
                page.locator('#caseOwner').fill('QA support');page.locator('[data-act="acknowledge"]').click()
                expect(page.locator('#caseDetail .case-tags')).to_contain_text('Staff handling')
                page.locator('#caseConfirmed').check();page.locator('[data-act="queue_response"]').click()
                page.locator('#caseNote').fill('Fictional investigation recorded and awaiting tenant confirmation.')
                page.locator('[data-act="followup"]').click();expect(page.locator('#caseDetail .case-tags')).to_contain_text('Follow-up')
                page.locator('#caseNote').fill('Fictional tenant confirmed the issue no longer occurs.')
                page.locator('#caseConfirmed').check();page.locator('[data-act="verify"]').click()
                expect(page.locator('[data-act="close"]')).to_be_visible();page.locator('[data-act="close"]').click()
                expect(page.locator('[data-feedback="APPROVED"]')).to_be_visible();page.locator('[data-feedback="APPROVED"]').click()
                page.locator('[data-close="caseDialog"]').click();page.locator('[data-view="memory"]').click()
                expect(page.locator('#memoryExamples')).to_contain_text('Could you confirm')
                page.locator('[data-revoke]').click();expect(page.locator('#memoryExamples')).to_contain_text('Close a verified case')
                page.locator('[data-view="notifications"]').click()
                page.locator('[data-approve]').first.click();expect(page.locator('[data-deliver]')).to_have_count(1)
                page.locator('[data-deliver]').click();expect(page.locator('#notice')).to_contain_text('Configure an HTTPS notification gateway')
                page.locator('[data-view="settings"]').click();page.locator('#portalIssue').click();page.locator('#issueKey').click()
                expect(page.locator('#portalKey')).to_contain_text('Access key')
                token=page.locator('#portalKey').inner_text().split(': ',1)[1]
                page.locator('[data-close="utilityDialog"]').click()
                portal=context.new_page();portal.on('pageerror',lambda e:errors.append(str(e)));portal.goto(url+'/portal')
                portal.locator('#accessKey').fill(token);portal.locator('#connect').click()
                expect(portal.locator('#tenantCases')).to_contain_text('Fictional room Wi-Fi enquiry')
                expect(portal.locator('#tenantMoves')).to_contain_text('MOVE_IN')
                portal.close()
                page.locator('[data-view="overview"]').click();page.screenshot(path=str(output/'tenant-overview-desktop.png'),full_page=True)
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':1000})
                    for view in ['overview','cases','moves','notifications','sources','memory','settings','activity']:
                        page.locator('[data-view="'+view+'"]').click()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),f'Overflow at {width}/{view}'
                    page.locator('[data-view="overview"]').click()
                    if width==390:page.screenshot(path=str(output/'tenant-overview-mobile.png'),full_page=True)
                assert not errors,errors
                assert not external,external
                context.close();browser.close()
                print('PASS: tenant records, moves, AI draft, closure, revoked memory, notifications, portal, 8 responsive views; no page errors or external requests.')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
