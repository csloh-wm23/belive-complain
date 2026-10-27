"""Direct website complaint -> same staff case -> reviewed tenant reply, in an isolated test DB."""
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
                errors=[];external=[];attempts=[]
                def observe(page):
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:external.append(r.url) if not r.url.startswith(url) else None)
                tenant=context.new_page();observe(tenant)
                tenant.on('request',lambda r:attempts.append(r.headers.get('idempotency-key')) if r.url.endswith('/api/website/complaints') else None)
                tenant.goto(url+'/belive')
                expect(tenant.get_by_role('heading',level=1)).to_contain_text('Your home.')
                assert tenant.locator('.site-topic').count()==6
                assert tenant.evaluate('document.documentElement.scrollWidth <= innerWidth')
                tenant.screenshot(path=str(output/'belive-tenant-website-desktop.png'),full_page=True)
                tenant.get_by_role('link',name='Make a complaint',exact=True).first.click()
                expect(tenant.locator('#websiteComplaintDialog')).to_be_visible()
                expect(tenant).to_have_url(url+'/belive')
                form=tenant.locator('#websiteComplaint')
                title='DEMO complaint from tenant website'
                form.locator('[name=title]').fill(title)
                form.locator('[name=description]').fill('Fictional test: the Wi-Fi in my room drops each evening on two devices.')
                form.locator('[name=access_key]').fill('invalid-key');tenant.locator('#sendWebsiteComplaint').click()
                expect(tenant.locator('#websiteComplaintError')).not_to_be_empty()
                with service.store.connect() as db:assert service.store.all(db,'case')==[]
                form.locator('[name=access_key]').fill(token)
                # Lose the first successful receipt after the backend commits: retry must reuse the key.
                def lose_receipt(route):
                    result=route.fetch();assert result.ok;route.abort()
                tenant.route('**/api/website/complaints',lose_receipt,times=1)
                tenant.locator('#sendWebsiteComplaint').click()
                expect(tenant.locator('#websiteComplaintError')).to_contain_text('Could not confirm submission')
                with service.store.connect() as db:assert len(service.store.all(db,'case'))==1
                tenant.locator('#sendWebsiteComplaint').click()
                expect(tenant.locator('#websiteReceipt')).to_be_visible()
                expect(tenant.locator('#websiteReceiptTitle')).to_be_focused()
                tenant.locator('#websiteReceipt').screenshot(path=str(output/'website-connection-receipt.png'))
                assert attempts[-1]==attempts[-2]
                cid=tenant.locator('#websiteCaseRef').inner_text()
                expect(form.locator('[name=access_key]')).to_have_value('')
                assert tenant.evaluate('sessionStorage.length===0 && localStorage.length===0')
                tenant.screenshot(path=str(output/'belive-website-linked-receipt-desktop.png'),full_page=True)
                with service.store.connect() as db:
                    cases=service.store.all(db,'case');assert len(cases)==1
                    assert cases[0]['id']==cid and cases[0]['tenant_id']=='DEMO-TENANT'
                    assert cases[0]['entrypoint']=='TENANT_WEBSITE'
                dashboard=tenant.locator('#websiteStaffCase').get_attribute('href')
                assert dashboard=='/?case='+cid
                staff=context.new_page();observe(staff);staff.goto(url+dashboard)
                expect(staff.locator('#authGate')).to_be_visible()
                staff.locator('#authUsername').fill('website-qa');staff.locator('#authPassword').fill('Fictional-browser-password-123');staff.locator('#authSubmit').click()
                expect(staff.locator('#caseDialog')).to_be_visible()
                expect(staff.locator('#caseDetail')).to_contain_text(cid)
                expect(staff.locator('#caseRows')).to_contain_text('BeLive website')
                staff.locator('#reloadCase').click()
                expect(staff.locator('#caseDraft')).to_have_value('Could you confirm whether other devices have the same issue?')
                staff.locator('#caseNote').fill('PRIVATE QA note: never visible in the tenant conversation.')
                staff.locator('[data-act=note]').click()
                staff.locator('#caseConfirmed').check();staff.locator('[data-act=publish_response]').click()
                expect(staff.locator('#caseDetail .conversation')).to_contain_text('Could you confirm whether other devices')
                staff.locator('#caseDialog').evaluate('(el)=>el.scrollTop=0')
                staff.locator('#caseDialog').screenshot(path=str(output/'website-connection-dashboard.png'))
                staff.screenshot(path=str(output/'belive-website-linked-case-desktop.png'),full_page=True)
                tenant.locator('#websiteTrackCase').click()
                expect(tenant).to_have_url(url+'/portal?case='+cid+'#conversations')
                expect(tenant.locator('#tenantArea')).to_be_hidden()
                tenant.locator('#accessKey').fill(token);tenant.locator('#connect').click()
                expect(tenant.locator('#portal-case-'+cid+' h3')).to_be_focused()
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
                tenant.get_by_role('link',name='Back to BeLive',exact=False).click()
                tenant.get_by_role('link',name='My requests',exact=False).click()
                tenant.locator('#accessKey').fill(token);tenant.locator('#connect').click()
                expect(tenant.locator('#conversationHeading')).to_be_focused()
                tenant.get_by_role('link',name='Back to BeLive',exact=False).click()
                tenant.locator('.site-topic[href*="topic=wifi"]').click()
                expect(tenant.locator('#websiteComplaint [name=title]')).to_have_value('Wi-Fi support request')
                tenant.locator('#websiteComplaint [name=access_key]').fill(token)
                tenant.locator('#closeWebsiteComplaint').click()
                expect(tenant.locator('#websiteComplaint [name=access_key]')).to_have_value('')
                mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,device_scale_factor=1,timezone_id='Asia/Kuala_Lumpur')
                phone=mobile.new_page();observe(phone);phone.goto(url+'/belive')
                assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                phone.screenshot(path=str(output/'belive-tenant-website-mobile.png'),full_page=True)
                phone.get_by_role('link',name='Make a complaint',exact=True).first.click()
                mf=phone.locator('#websiteComplaint');mf.locator('[name=access_key]').fill(token)
                mf.locator('[name=title]').fill('DEMO mobile website complaint')
                mf.locator('[name=description]').fill('Fictional mobile test: the room Wi-Fi disconnects on my phone.')
                phone.locator('#sendWebsiteComplaint').click();expect(phone.locator('#websiteReceipt')).to_be_visible()
                assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                phone.screenshot(path=str(output/'belive-website-linked-receipt-mobile.png'),full_page=True)
                phone.locator('#websiteTrackCase').click();phone.locator('#accessKey').fill(token);phone.locator('#connect').click()
                expect(phone.locator('#tenantCases')).to_contain_text('DEMO mobile website complaint')
                assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                phone.screenshot(path=str(output/'belive-tenant-complaint-mobile.png'),full_page=True)
                assert not errors,errors
                assert not external,external
                mobile.close();context.close();browser.close()
                print('PASS: website form, real saved receipt, lost-receipt retry without duplicates, matching authenticated dashboard deep link, reviewed tenant reply, privacy, tracking links and desktop/mobile layouts.')
        finally:
            server.shutdown();server.server_close();worker.join()

if __name__=='__main__':main()
