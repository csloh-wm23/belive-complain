"""Tenant website to portal to operator walkthrough; fictional fixtures and test-only AI."""
import secrets
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from server import make_handler
from belive.service import Service
from belive.access import Access
from test_backend import FakeAI


def main():
    output=ROOT/'artifacts';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'tenant-site-qa.db',FakeAI())
        def command(name,p):return service.command(name,p,secrets.token_hex(16))
        command('condo',dict(id='DEMO-PROPERTY',name='Fictional website test property',rules='Fictional fixture: report Wi-Fi issues privately to support.',confirmed=True))
        command('tenant',dict(id='DEMO-TENANT',condo_id='DEMO-PROPERTY',unit_ref='DEMO-ROOM',verified_by='Fictional browser QA',evidence='Fictional tenancy fixture for an isolated UI test.',confirmed=True))
        token=command('portal_issue',{'tenant_id':'DEMO-TENANT'})['token']
        Access(service).create(dict(username='website-qa',name='Website QA staff',password='Fictional-browser-password-123'),bootstrap=True)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Kuala_Lumpur')
                errors=[];external=[]
                def observe(page):
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:external.append(r.url) if not r.url.startswith(url) else None)
                tenant=context.new_page();observe(tenant)
                tenant.goto(url+'/belive')
                expect(tenant.get_by_role('heading',level=1)).to_contain_text('Your home.')
                assert tenant.locator('.site-topic').count()==6
                assert tenant.evaluate('document.documentElement.scrollWidth <= innerWidth')
                tenant.screenshot(path=str(output/'belive-tenant-website-desktop.png'),full_page=True)
                tenant.get_by_role('link',name='Make a complaint',exact=True).first.click()
                expect(tenant).to_have_url(url+'/portal#report')
                expect(tenant.locator('#tenantIntake')).to_be_hidden()
                tenant.locator('#accessKey').fill('invalid-key');tenant.locator('#connect').click()
                expect(tenant.locator('#portalNotice')).not_to_be_empty()
                expect(tenant.locator('#tenantIntake')).to_be_hidden()
                tenant.locator('#accessKey').fill(token);tenant.locator('#accessKey').press('Enter')
                expect(tenant.locator('#tenantIntake')).to_be_visible()
                expect(tenant.locator('#portalAccessCard')).to_be_hidden()
                expect(tenant.locator('#tenantIntake [name=title]')).to_be_focused()
                title='DEMO complaint from tenant website'
                tenant.locator('#tenantIntake [name=title]').fill(title)
                tenant.locator('#tenantIntake [name=description]').fill('Fictional test: the Wi-Fi in my room drops each evening on two devices.')
                tenant.get_by_role('button',name='Submit support request',exact=True).click()
                expect(tenant.locator('#portalNotice')).to_contain_text('saved. Follow replies')
                expect(tenant.locator('#tenantCases')).to_contain_text(title)
                assert 'Could you confirm whether other devices' not in tenant.locator('#tenantCases').inner_text()
                with service.store.connect() as db:
                    cases=service.store.all(db,'case');assert len(cases)==1
                    assert cases[0]['tenant_id']=='DEMO-TENANT';cid=cases[0]['id']
                staff=context.new_page();observe(staff);staff.goto(url)
                staff.locator('#authUsername').fill('website-qa');staff.locator('#authPassword').fill('Fictional-browser-password-123');staff.locator('#authSubmit').click()
                expect(staff.locator('#operatorApp')).to_be_visible()
                staff.locator('[data-view=cases]').click()
                expect(staff.locator('#caseRows')).to_contain_text(title)
                staff.locator('#caseRows .case-link').filter(has_text=title).click()
                staff.locator('#reloadCase').click()
                expect(staff.locator('#caseDraft')).to_have_value('Could you confirm whether other devices have the same issue?')
                staff.locator('#caseNote').fill('PRIVATE QA note: never visible in the tenant conversation.')
                staff.locator('[data-act=note]').click()
                staff.locator('#caseConfirmed').check();staff.locator('[data-act=publish_response]').click()
                expect(staff.locator('#caseDetail .conversation')).to_contain_text('Could you confirm whether other devices')
                tenant.locator('#refreshPortal').click()
                expect(tenant.locator('#tenantCases')).to_contain_text('Could you confirm whether other devices')
                assert 'PRIVATE QA note' not in tenant.locator('body').inner_text()
                tenant.locator('[data-note]').fill('Fictional test reply: two devices are affected.')
                tenant.locator('[data-update]').click()
                expect(tenant.locator('#portalNotice')).to_contain_text('reply was saved')
                staff.locator('#reloadCase').click()
                expect(staff.locator('#caseDetail .conversation')).to_contain_text('two devices are affected')
                tenant.screenshot(path=str(output/'belive-tenant-complaint-desktop.png'),full_page=True)
                tenant.locator('#portalSignOut').click()
                expect(tenant.locator('#tenantArea')).to_be_hidden();expect(tenant.locator('#tenantCases')).to_be_empty()
                expect(tenant.locator('#accessKey')).to_be_focused()
                assert tenant.evaluate('sessionStorage.length===0 && localStorage.length===0')
                tenant.get_by_role('link',name='Back to BeLive',exact=False).click()
                tenant.get_by_role('link',name='My requests',exact=False).click()
                expect(tenant).to_have_url(url+'/portal#conversations')
                tenant.locator('#accessKey').fill(token);tenant.locator('#connect').click()
                expect(tenant.locator('#conversationHeading')).to_be_focused()
                tenant.get_by_role('link',name='Back to BeLive',exact=False).click()
                tenant.locator('.site-topic[href*="topic=wifi"]').click()
                expect(tenant.locator('#tenantIntake [name=title]')).to_have_value('Wi-Fi support request')
                tenant.locator('#accessKey').fill(token);tenant.locator('#connect').click()
                expect(tenant.locator('#tenantIntake [name=title]')).to_be_focused()
                mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,device_scale_factor=1,timezone_id='Asia/Kuala_Lumpur')
                phone=mobile.new_page();observe(phone);phone.goto(url+'/belive')
                assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                phone.screenshot(path=str(output/'belive-tenant-website-mobile.png'),full_page=True)
                phone.get_by_role('link',name='Make a complaint',exact=True).first.click()
                expect(phone.locator('#portalAccessCard')).to_be_visible()
                phone.locator('#accessKey').fill(token);phone.locator('#connect').click()
                expect(phone.locator('#tenantCases')).to_contain_text(title)
                assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                phone.screenshot(path=str(output/'belive-tenant-complaint-mobile.png'),full_page=True)
                assert not errors,errors
                assert not external,external
                mobile.close();context.close();browser.close()
                print('PASS: desktop/mobile tenant website, complaint/tracking/topic links, private access, tenant intake visible in staff dashboard, reviewed reply, tenant follow-up, navigation and clearing access; no page errors or external requests.')
        finally:
            server.shutdown();server.server_close();worker.join()

if __name__=='__main__':main()
