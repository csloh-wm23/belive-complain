"""Isolated headless browser; fictional records never touch the live installation."""
import sys,tempfile,threading,secrets
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from belive import customer_directory as directory
from server import make_handler
from test_backend import FakeAI
from test_whatsapp import fixture_assessment,plan

def main():
    with tempfile.TemporaryDirectory() as tmp,patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment),patch('belive.whatsapp_ai.reply',return_value=plan()),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.request_json',side_effect=AssertionError('No real sends')):
        s=Service(Path(tmp)/'qa.db',FakeAI());r=s.command('wa_simulate',{'customer':'directory-browser','text':'The door handle needs checking.'},secrets.token_hex(16))
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#authUsername').fill('record-qa');page.locator('#authName').fill('Fictional QA');page.locator('#authPassword').fill('Isolated-test-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view="customer-records"]').click();expect(page.locator('#pageTitle')).to_have_text('Customer records');expect(page.locator('#customerRecordList')).to_contain_text('No customer data yet.')
                form=page.locator('#customerRecordForm')
                for k,v in {'customer_id':'qa-only','name':'Fictional QA Customer','property_name':'Fictional QA House','unit':'QA-Room','source':'Isolated browser test'}.items():form.locator(f'[name="{k}"]').fill(v)
                form.locator('[name="confirmed"]').check();form.locator('button[type="reset"]').blur();form.get_by_text('Save record',exact=True).click()
                expect(page.locator('#customerRecordNotice')).to_have_text('Private customer record saved.');expect(page.locator('#customerRecordList')).to_contain_text('Fictional QA Customer')
                page.locator('#customerRecordThread').select_option(r['thread_id']);binding=page.locator('#customerRecordBinding');binding.locator('[name="record_id"]').select_option(index=1);binding.locator('[name="confirmed"]').check();binding.get_by_text('Save selection',exact=True).click();expect(page.locator('#customerRecordNotice')).to_have_text('Selection saved for this support case.')
                with s.store.connect() as db:
                    facts=directory.facts(s,db,s.store.get(db,'wa_thread',r['thread_id']));assert facts['property_name']=='Fictional QA House' and 'phone' not in facts
                page.get_by_text('Review / edit',exact=True).click();form.locator('[name="active"]').uncheck();form.locator('[name="confirmed"]').check();form.get_by_text('Save record',exact=True).click();expect(page.locator('#customerRecordList')).to_contain_text('Inactive')
                with s.store.connect() as db:assert directory.facts(s,db,s.store.get(db,'wa_thread',r['thread_id'])) is None
                assert not errors,errors
                page.screenshot(path=str(ROOT/'data/customer-records-qa.png'),full_page=True);browser.close()
                print('PASS: empty state, optional phone, save/edit, explicit selection, safe location facts, deactivation and navigation; no browser errors.')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
