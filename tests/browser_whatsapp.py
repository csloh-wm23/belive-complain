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
from test_whatsapp import plan

def main():
    def reply(s,ctx):
        draft=plan()
        if ctx['staff_guidance']:draft['reply']='The team has confirmed a technician will inspect the router tomorrow at 10 am. Please keep messaging here if anything changes.'
        elif 'broken' in str(ctx['conversation']):draft.update(reply='I am asking our team to arrange the next step. You can keep messaging me here.',needs_staff=True,needs_maintenance=True,staff_question='Please confirm the repair arrangements.')
        return draft
    with tempfile.TemporaryDirectory() as tmp,patch('belive.whatsapp_ai.reply',side_effect=reply),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.request_json',side_effect=AssertionError('No real WhatsApp sends')):
        s=Service(Path(tmp)/'test.db',FakeAI());server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#authUsername').fill('whatsapp-qa');page.locator('#authName').fill('WhatsApp QA');page.locator('#authPassword').fill('Isolated-test-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view=whatsapp]').click();expect(page.locator('#pageTitle')).to_have_text('WhatsApp inbox');expect(page.locator('#waConnection')).to_contain_text('not connected')
                page.get_by_text('Company-approved SOP',exact=True).click();f=page.locator('#waSop');f.locator('[name=title]').fill('Fictional SOP');f.locator('[name=text]').fill('For a shared router fault, ask staff for repair arrangements.');f.locator('[name=source]').fill('QA approved fixture');f.locator('[name=confirmed]').check();f.locator('button').click();expect(page.locator('#waKnowledge')).to_contain_text('Fictional SOP')
                page.get_by_text('Test a conversation safely — never sends to WhatsApp',exact=True).click();f=page.locator('#waSim');f.locator('[name=text]').fill('bro the wifi so suck');f.locator('button').click();expect(page.locator('#waHistory')).to_contain_text('Bro, does this affect',timeout=20000)
                f.locator('[name=text]').fill('Actually the router is broken, please get staff');f.locator('button').click();expect(page.locator('#waTitle')).to_contain_text('WAITING_STAFF',timeout=20000);expect(page.locator('#waEvidence')).to_contain_text('confirm the repair')
                staff=page.locator('#waStaff');staff.locator('[name=guidance]').fill('Confirmed: technician will inspect the router tomorrow at 10 am.');staff.locator('[name=confirmed]').check();staff.locator('button').click();expect(page.locator('#waHistory')).to_contain_text('The team has confirmed a technician',timeout=20000);expect(page.locator('#waHistory')).to_contain_text('INTERNAL ONLY');expect(page.locator('#waEvidence')).to_contain_text('SIMULATED')
                f.locator('[name=customer]').fill('second_customer');f.locator('[name=text]').fill('hi');f.locator('button').click();expect(page.locator('[data-wa-thread]')).to_have_count(2,timeout=20000);expect(page.locator('#waHistory')).not_to_contain_text('technician');assert not errors,errors
                page.screenshot(path=str(ROOT/'output/whatsapp-inbox-qa.png'),full_page=True);browser.close()
            print('PASS: inbox navigation, approved SOP, casual reply, staff handoff, internal solution -> AI relay, sender isolation and delivery labels; no browser errors. Temporary fixture data only.')
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':main()
