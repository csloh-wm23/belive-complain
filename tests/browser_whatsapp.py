"""Exercise the new inbox against isolated fixtures; never sends to Meta."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from server import make_handler
from test_backend import FakeAI
from test_whatsapp import plan,fixture_assessment

def main():
    def reply(s,ctx):
        draft=plan()
        if ctx['staff_guidance']:draft['reply']='The team has confirmed a technician will inspect the router tomorrow at 10 am. Please keep messaging here if anything changes.'
        elif 'broken' in str(ctx['conversation']):draft.update(reply='I am asking our team to arrange the next step. You can keep messaging me here.',needs_staff=True,needs_maintenance=True,staff_question='Please confirm the repair arrangements.')
        return draft
    with tempfile.TemporaryDirectory() as tmp,patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment),patch('belive.whatsapp_ai.reply',side_effect=reply),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.request_json',side_effect=AssertionError('No real WhatsApp sends')):
        s=Service(Path(tmp)/'test.db',FakeAI());server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#authUsername').fill('whatsapp-qa');page.locator('#authName').fill('WhatsApp QA');page.locator('#authPassword').fill('Isolated-test-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view=whatsapp]').click();expect(page.locator('#pageTitle')).to_have_text('Customer Support');expect(page.locator('#waConnection')).to_contain_text('not connected')
                channel=page.locator('#waChannel');channel.locator('[name=public_number]').fill('0'+'1'+'0'*8);channel.locator('[name=confirmed]').check();channel.locator('button').click();expect(page.locator('#waNotice')).to_contain_text('entry saved');expect(page.locator('#waChannelProgress')).to_contain_text('not connected')
                page.goto(f'http://127.0.0.1:{server.server_port}/belive');expect(page.locator('[data-whatsapp-report]').first).to_have_attribute('href',__import__('re').compile(r'https://wa\.me/60100000000\?text='));expect(page.locator('#tenantReportStatus')).to_contain_text('still being connected');expect(page.locator('[data-whatsapp-report]').first).to_contain_text('Customer Support');expect(page.locator('.site-lede')).to_contain_text('Ask questions')
                with s.store.connect() as db:assert not s.store.all(db,'case'),'Opening website must not submit a complaint'
                page.route('https://wa.me/**',lambda route:route.fulfill(status=200,content_type='text/plain',body='WhatsApp navigation intercepted for isolated QA'))
                page.locator('.site-topic').filter(has_text='Wi-Fi & internet').click();assert page.url.startswith('https://wa.me/60100000000?text=');assert 'Wi-Fi' in __import__('urllib.parse',fromlist=['unquote']).unquote(page.url)
                page.goto(f'http://127.0.0.1:{server.server_port}/belive');page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(ROOT/'output/whatsapp-tenant-report-mobile.png'),full_page=True);page.set_viewport_size({'width':1440,'height':1050});page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('[data-view=whatsapp]').click()
                page.get_by_text('Company-approved SOP',exact=True).click();f=page.locator('#waSop');f.locator('[name=title]').fill('Fictional SOP');f.locator('[name=text]').fill('For a shared router fault, ask staff for repair arrangements.');f.locator('[name=source]').fill('QA approved fixture');f.locator('[name=confirmed]').check();f.locator('button').click();expect(page.locator('#waKnowledge')).to_contain_text('Fictional SOP')
                page.get_by_text('Test a conversation safely — never sends to WhatsApp',exact=True).click();f=page.locator('#waSim');f.locator('[name=text]').fill('bro the wifi so suck');f.locator('button').click();expect(page.locator('#waHistory')).to_contain_text('Bro, does this affect',timeout=20000)
                f.locator('[name=text]').fill('Actually the router is broken, please get staff');f.locator('button').click();expect(page.locator('#waTitle')).to_contain_text('WAITING_STAFF',timeout=20000);expect(page.locator('#waEvidence')).to_contain_text('confirm the repair');expect(page.locator('#waAssessment')).to_contain_text('MODERATE');expect(page.locator('#waAssessment')).to_contain_text('Staff destination')
                staff=page.locator('#waStaff');staff.locator('[name=guidance]').fill('Confirmed: technician will inspect the router tomorrow at 10 am.');staff.locator('[name=confirmed]').check();staff.locator('button').click();expect(page.locator('#waHistory')).to_contain_text('The team has confirmed a technician',timeout=20000);expect(page.locator('#waHistory')).to_contain_text('INTERNAL ONLY');expect(page.locator('#waEvidence')).to_contain_text('SIMULATED')
                f.locator('[name=customer]').fill('second_customer');f.locator('[name=text]').fill('hi');f.locator('button').click();expect(page.locator('[data-wa-thread]')).to_have_count(2,timeout=20000);expect(page.locator('#waHistory')).not_to_contain_text('technician');assert not errors,errors
                page.screenshot(path=str(ROOT/'output/whatsapp-inbox-qa.png'),full_page=True);browser.close()
            print('PASS: customer website links to the configured WhatsApp with topic text, no premature case creation, responsive mobile entry, honest connection state, inbox, SOP, casual reply, staff guidance -> AI relay, customer isolation and delivery labels. Temporary data; no real Meta sends.')
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':main()
