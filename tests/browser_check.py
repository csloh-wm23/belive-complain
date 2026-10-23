"""Local UI integration QA. Fixtures and FakeAI exist only inside a temporary database."""
import sys
import tempfile
import threading
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from server import make_handler
from belive.service import Service
from test_backend import FakeAI

def main():
    output=ROOT/'artifacts';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'browser.db',FakeAI(),workspace_config=Path(tmp)/'workspace.json')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1100},timezone_id='Asia/Kuala_Lumpur')
                page=context.new_page();errors=[];external=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:external.append(r.url) if not r.url.startswith(url) else None)
                page.goto(url);expect(page.locator('#authGate')).to_be_visible()
                page.locator('#authUsername').fill('qa-admin');page.locator('#authName').fill('QA support');page.locator('#authPassword').fill('Isolated-browser-password-123');page.locator('#authSubmit').click()
                expect(page.locator('#operatorApp')).to_be_visible();expect(page.locator('.metric')).to_have_count(4)
                assert page.locator('[data-view="marketing"], [data-view="sales"], [data-view="owners"], [data-view="moves"]').count()==0
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
                    expect(form.locator('input').first).to_have_value('')
                submit('condoForm',dict(id='C-QA',name='Fictional QA property',rules='Fictional QA guidance: report shared Wi-Fi outages privately.'),['confirmed'])
                submit('tenantForm',dict(id='T-QA',condo_id='C-QA',unit_ref='U-QA',verified_by='QA operator',evidence='Fictional test tenancy checked.'),['confirmed'])
                expect(page.locator('#resources')).to_contain_text('1 verified tenants')
                assert page.locator('#moveForm,#staffForm,[name="checklist"],[name="days"]').count()==0
                assert 'Move-in' not in page.locator('body').inner_text()
                submit('recordForm',dict(tenant_id='T-QA',source='QA support record',text='Verified QA record: shared Wi-Fi support is handled by the support team.'),['confirmed'])
                page.locator('[data-view="database"]').click()
                expect(page.locator('#databaseRecords')).to_contain_text('Fictional QA property')
                expect(page.locator('#databaseRecords')).to_contain_text('T-QA')
                expect(page.locator('#databaseRecords')).to_contain_text('QA support record')
                page.locator('#recordSearch').fill('QA support record')
                expect(page.locator('#databaseRecords .saved-record-group').first).to_contain_text('0 of 1')
                page.locator('#recordSearch').fill('')
                chosen=Path(tmp)/'Selected workspace.db'
                with patch('server.choose_database',return_value=chosen):
                    page.locator('#chooseDatabase').click()
                    expect(page.locator('#databaseLocation')).to_contain_text('Selected workspace.db')
                assert not chosen.exists()
                page.reload();page.locator('[data-view="database"]').click()
                expect(page.locator('#databaseRecords')).to_contain_text('QA support record')
                expect(page.locator('#databaseLocation')).to_contain_text('browser.db')
                expect(page.locator('#databaseLocation')).to_contain_text('Selected workspace.db')
                with patch('server.choose_database',return_value=None):
                    page.locator('#chooseDatabase').click()
                    expect(page.locator('#notice')).to_contain_text('Database selection cancelled')
                page.locator('[data-record]').first.click();page.locator('#recordSource').fill('QA support record v2');page.locator('#recordText').fill('Verified QA correction: contact support for shared Wi-Fi outages.')
                page.locator('#recordReason').fill('QA corrected the source guidance after review.');page.locator('#recordConfirmed').check();page.locator('#correctRecord').click()
                expect(page.locator('#recordManagement')).to_contain_text('v2')
                page.locator('#createBackup').click();expect(page.locator('#backupsList')).to_contain_text('bytes')
                page.screenshot(path=str(output/'database-records-desktop.png'),full_page=True)
                page.locator('[data-view="sources"]').click()
                assert page.locator('#sourceForm [name="enabled"]').count()==0
                submit('sourceForm',dict(platform='GOOGLE',resource='accounts/1/locations/2'),['authorised'])
                expect(page.locator('#sourcesList')).to_contain_text('MONITORING')
                page.get_by_role('button',name='Pause checks',exact=True).click()
                expect(page.locator('#sourcesList')).to_contain_text('PAUSED')
                page.get_by_role('button',name='Resume checks',exact=True).click()
                expect(page.locator('#sourcesList')).to_contain_text('MONITORING')

                page.locator('#newCase').click();form=page.locator('#intakeForm')
                form.locator('[name="title"]').fill('Fictional room Wi-Fi enquiry')
                form.locator('[name="description"]').fill('My room Wi-Fi drops each evening. This is a QA fixture.')
                form.locator('[name="tenant_id"]').select_option('T-QA');form.locator('button.primary').click()
                expect(page.locator('#caseDialog')).to_be_visible()
                page.locator('#reloadCase').click()
                expect(page.locator('#caseDraft')).to_have_value('Could you confirm whether other devices have the same issue?')
                page.locator('[data-act="acknowledge"]').click()
                expect(page.locator('#caseDetail .case-tags')).to_contain_text('Staff handling')
                page.locator('#caseNote').fill('PRIVATE internal support note: fixture audit only.')
                page.locator('[data-act="note"]').click()
                page.locator('#caseConfirmed').check();page.locator('[data-act="publish_response"]').click()
                expect(page.locator('#caseDetail .conversation')).to_contain_text('Could you confirm whether other devices')
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
                page.locator('[data-view="settings"]').click();page.locator('#checkAi').click();page.locator('#refresh').click();expect(page.locator('#aiCheckStatus')).to_contain_text('PASSED')
                submit('userForm',dict(username='qa-support',name='Second Support',password='Support-browser-password-123',role='SUPPORT'))
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
                assert portal.locator('#tenantMoves').count()==0
                assert 'move arrangements' not in portal.locator('body').inner_text().lower()
                expect(portal.locator('#tenantCases')).to_contain_text('Could you confirm whether other devices')
                assert 'PRIVATE internal support note' not in portal.locator('body').inner_text()
                portal.locator('[data-note]').first.fill('The issue returned after the last support action.');portal.locator('#refreshPortal').click();expect(portal.locator('[data-note]').first).to_have_value('The issue returned after the last support action.')
                portal.locator('[data-unresolved]').first.click();expect(portal.locator('#tenantCases')).to_contain_text('HUMAN_REVIEW')
                page.locator('[data-view="cases"]').click();page.locator('#refresh').click();page.locator('#caseRows [data-case]').first.click()
                page.locator('[data-act="acknowledge"]').click();page.locator('#caseNote').fill('Fixture support action completed; awaiting tenant feedback.');page.locator('[data-act="followup"]').click()
                portal.locator('#refreshPortal').click();expect(portal.locator('[data-resolved]')).to_be_visible()
                portal.locator('[data-resolved]').click();expect(portal.locator('#portalNotice')).to_contain_text('outcome feedback')
                page.locator('#reloadCase').click();expect(page.locator('#caseDetail')).to_contain_text('Reported resolved')
                page.locator('#caseNote').fill('Support verified the new tenant outcome feedback.');page.locator('#caseConfirmed').check();page.locator('[data-act="verify"]').click();page.locator('[data-act="close"]').click()
                page.screenshot(path=str(output/'tenant-case-conversation-desktop.png'),full_page=True)
                portal.locator('#refreshPortal').click();expect(portal.locator('#tenantCases')).to_contain_text('CLOSED')
                portal.screenshot(path=str(output/'tenant-portal-conversation-desktop.png'),full_page=True)
                page.locator('[data-close="caseDialog"]').click()

                portal.close()
                page.locator('[data-view="overview"]').click();page.screenshot(path=str(output/'tenant-overview-desktop.png'),full_page=True)
                page.locator('#signOut').click();expect(page.locator('#authGate')).to_be_visible()
                page.locator('#authUsername').fill('qa-support');page.locator('#authPassword').fill('Support-browser-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view="settings"]').click();expect(page.locator('#recordForm')).to_be_hidden();expect(page.locator('#userForm')).to_be_hidden()
                page.locator('[data-view="database"]').click();expect(page.locator('#createBackup')).to_be_hidden()
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':1000})
                    for view in ['overview','cases','notifications','sources','memory','settings','database','activity']:
                        page.locator('[data-view="'+view+'"]').click()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),f'Overflow at {width}/{view}'
                    page.locator('[data-view="overview"]').click()
                    if width==390:
                        page.screenshot(path=str(output/'tenant-overview-mobile.png'),full_page=True)
                        page.locator('[data-view="database"]').click()
                        page.screenshot(path=str(output/'database-records-mobile.png'),full_page=True)
                assert not errors,errors
                assert not external,external
                context.close();browser.close()
                print('PASS: admin setup, support login and restricted controls, portal publishing/privacy/outcome feedback, record correction, backups, connection-check integration, case lifecycle, database selection, source pause/resume and eight responsive views; no page errors or external requests.')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
