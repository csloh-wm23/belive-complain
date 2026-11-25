"""Browser checks of source pages, private downloads and revocation; synthetic AI only."""
import sys,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_company_sop import CompanySopTests
from test_whatsapp import plan
from server import make_handler

def main():
    fixture=CompanySopTests();fixture.setUp();fixture.imported();service=fixture.s
    def select(s,conversation,catalog):return [x['id'] for x in catalog if 'Quiet' in x['title']]
    def reply(s,ctx):
        draft=plan()
        if ctx['sop']:draft.update(reply='The supplied house rules set quiet hours from 10 pm to 8 am.',sources_used=[ctx['sop'][0]['id']])
        else:draft.update(reply='I will ask staff to confirm the applicable rule.',needs_staff=True,staff_question='Please confirm the current quiet-hours rule; the source document is disabled.')
        return draft
    with patch('belive.whatsapp_ai.select_sop',side_effect=select),patch('belive.whatsapp_ai.reply',side_effect=reply),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.request_json',side_effect=AssertionError('No external messages')):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#authUsername').fill('sop-qa');page.locator('#authName').fill('SOP QA');page.locator('#authPassword').fill('Fictional-QA-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view=whatsapp]').click();page.get_by_text('Company-approved SOP',exact=True).click();doc=page.locator('[data-wa-document]');expect(doc).to_contain_text('Company-supplied template');expect(doc).to_contain_text('3 pages')
                with page.expect_download() as download:doc.get_by_role('button',name='Download original PDF').click()
                assert Path(download.value.path()).read_bytes()==fixture.pdf.read_bytes()
                source=page.locator('#waKnowledge article').filter(has_text='Quiet hours').locator('details');source.locator('summary').click();expect(source).to_contain_text('Page 2')
                with page.expect_response(lambda r:'/api/status' in r.url):page.evaluate("window.dispatchEvent(new CustomEvent('belive:refresh'))")
                assert source.evaluate('(e)=>e.open'),'Polling collapsed the source evidence'
                page.get_by_text('Test a conversation safely — never sends to WhatsApp',exact=True).click();form=page.locator('#waSim');form.locator('[name=text]').fill('When should we keep noise down?');form.locator('button').click();expect(page.locator('#waHistory')).to_contain_text('10 pm to 8 am',timeout=20000)
                page.locator('#waEvidence summary').first.click();expect(page.locator('#waEvidence')).to_contain_text('Test clause quiet');expect(page.locator('#waEvidence')).to_contain_text('pp. 2')
                doc.get_by_role('button',name='Disable document').click();expect(doc).to_contain_text('Disabled');form.locator('[name=text]').fill('Can you confirm the quiet-hours rule again?');form.locator('button').click();expect(page.locator('#waTitle')).to_contain_text('WAITING_STAFF',timeout=20000);expect(page.locator('#waHistory')).to_contain_text('asking our team to review',timeout=20000);expect(page.locator('#waEvidence')).to_contain_text('ask staff to confirm');expect(page.locator('#waAssessment')).to_contain_text('MODERATE')
                doc.get_by_role('button',name='Enable document').click();expect(doc).to_contain_text('In use for relevant support questions');assert not errors,errors
                page.screenshot(path=str(ROOT/'output/whatsapp-sop-browser-qa.png'),full_page=True);browser.close()
            print('PASS: template/source labels, protected PDF download, original clauses/page numbers, stable evidence during polling, cited reply, document disable and restore; no browser errors. Synthetic AI and temporary data only.')
        finally:server.shutdown();server.server_close();thread.join();fixture.tearDown()
if __name__=='__main__':main()
