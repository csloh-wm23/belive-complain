"""Disposable maintenance queue browser flow; no live data, contacts or dispatch."""
import sys,tempfile,threading,secrets
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from belive import whatsapp as wa
from server import make_handler
from test_backend import FakeAI
from test_whatsapp import fixture_assessment,plan

def main():
    reply={**plan(),'needs_staff':True,'needs_maintenance':True,'staff_question':'Inspect the fictional door handle.','maintenance_property':'QA-HOUSE','maintenance_unit':'QA-ROOM','maintenance_location_complete':True}
    with tempfile.TemporaryDirectory() as tmp,patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment),patch('belive.whatsapp_ai.reply',return_value=reply),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.request_json',side_effect=AssertionError('No real sends')):
        s=Service(Path(tmp)/'qa.db',FakeAI());r=s.command('wa_simulate',{'customer':'maintenance-ui-qa','text':'The handle fell off at QA-HOUSE / QA-ROOM.'},secrets.token_hex(16));wa.process_thread(s,r['thread_id'])
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#authUsername').fill('queue-qa');page.locator('#authName').fill('Fictional Queue QA');page.locator('#authPassword').fill('Isolated-test-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view="maintenance-queue"]').click();expect(page.locator('#pageTitle')).to_have_text('Maintenance queue');expect(page.locator('#maintenanceCards')).to_contain_text('Location complete')
                for stage in ['ACCEPTED','IN_PROGRESS','WORK_DONE']:
                    form=page.locator('[data-maintenance-form]');form.locator('[name="state"]').select_option(stage);form.locator('[name="note"]').fill('Checked fictional progress for browser test only.');form.locator('[name="confirmed"]').check();form.get_by_text('Save internal progress',exact=True).click();expect(page.locator('#maintenanceNotice')).to_have_text('Internal progress saved. No external notification was sent.')
                    expect(page.locator('#maintenanceCards')).to_contain_text({'ACCEPTED':'Accepted internally','IN_PROGRESS':'Work in progress','WORK_DONE':'Work reported done'}[stage])
                    with s.store.connect() as db:assert s.store.all(db,'wa_staff')[0]['maintenance_progress']['state']==stage
                expect(page.locator('#maintenanceCards')).to_contain_text('awaiting customer confirmation');expect(page.locator('[data-maintenance-form]')).to_have_count(0)
                page.locator('[data-support-chat]').click();expect(page.locator('#supportQuestionList')).to_contain_text('Work reported done');expect(page.locator('#supportLiveActivity')).to_contain_text('No reply currently processing')
                with s.store.connect() as db:
                    req=s.store.all(db,'wa_staff')[0];assert req['status']!='CLOSED';assert len(s.store.all(db,'wa_outgoing'))==1
                assert not errors,errors
                page.screenshot(path=str(ROOT/'data/support-experience-qa.png'),full_page=True);browser.close();print('PASS: internal acceptance, owner, work stages, pending customer confirmation, conversation progress and navigation; no real dispatch or browser errors.')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
