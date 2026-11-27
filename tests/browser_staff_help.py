"""Separate headless QA browser and temporary database; never touches the user's tabs."""
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
from test_whatsapp import plan,fixture_assessment

def main():
    def reply(service,context):
        target=context.get('target_request')
        if target:
            return {**plan(),'reply':'What date would your visitor stay?' if 'visitor' in target['question'] else 'Please confirm the laundry room for the inspection.', 'sources_used':[target['id']]}
        text=context.get('current_message',{}).get('text','')
        if 'visitor' in text:return {**plan(),'reply':'I am asking staff for the visitor conditions.','needs_staff':True,'staff_question':'Confirm visitor approval conditions.'}
        if 'washer' in text:return {**plan(),'reply':'I am asking staff for an inspection.','needs_staff':True,'staff_question':'Confirm washer inspection arrangements.'}
        return {**plan(),'reply':'Turn Wi-Fi off and on on your own phone.'}
    with tempfile.TemporaryDirectory() as tmp,patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment),patch('belive.whatsapp_ai.reply',side_effect=reply),patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.request_json',side_effect=AssertionError('No real WhatsApp sends')):
        service=Service(Path(tmp)/'qa.db',FakeAI())
        for text in ['Can my visitor stay overnight?','The washer needs an inspection.']:
            result=service.command('wa_simulate',{'customer':'staff-ui-qa','text':text},secrets.token_hex(16));wa.process_thread(service,result['thread_id'])
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#authUsername').fill('staff-qa');page.locator('#authName').fill('Fictional Staff QA');page.locator('#authPassword').fill('Isolated-test-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view="staff-help"]').click();expect(page.locator('#pageTitle')).to_have_text('Staff help');expect(page.locator('#staffHelpCounts')).to_contain_text('2 waiting')
                visitor=page.locator('#staffHelpCards > section').filter(has_text='Confirm visitor approval conditions.')
                expect(visitor.locator('blockquote')).to_have_text('Can my visitor stay overnight?')
                visitor.locator('textarea').fill('Ask for the date and number of nights first; approval is not yet granted.');visitor.locator('[name=confirmed]').check();visitor.locator('button.primary').click()
                expect(page.locator('#staffHelpNotice')).to_contain_text('Guidance saved');expect(page.locator('#staffHelpCounts')).to_contain_text('1 waiting')
                washer=page.locator('#staffHelpCards > section').filter(has_text='Confirm washer inspection arrangements.')
                washer.locator('textarea').fill('Confirmed: maintenance can inspect once the customer supplies the laundry room.');washer.locator('[name=confirmed]').check()
                # New messages may change the thread revision, but do not erase the typed solution.
                page.evaluate("""async()=>{const a=await(await fetch('/api/auth')).json();await fetch('/api/wa_simulate',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':a.csrf_token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({customer:'staff-ui-qa',text:'How can I toggle Wi-Fi on my phone?'})});}""")
                page.wait_for_timeout(1200);expect(washer.locator('textarea')).to_have_value('Confirmed: maintenance can inspect once the customer supplies the laundry room.')
                washer.locator('button.primary').click();expect(page.locator('#staffHelpCounts')).to_contain_text('0 waiting')
                page.locator('#staffHelpFilter').select_option('PROGRESS');expect(page.locator('#staffHelpCards > section')).to_have_count(2)
                page.locator('#staffHelpCards [data-help-chat]').first.click();expect(page.locator('#pageTitle')).to_have_text('Customer Support');expect(page.locator('#waHistory blockquote')).not_to_have_count(0)
                assert not errors,errors
                with service.store.connect() as db:
                    requests=service.store.all(db,'wa_staff');outputs=service.store.all(db,'wa_outgoing')
                assert len(requests)==2 and all(r['status']=='ANSWERED' for r in requests)
                assert all(any(o.get('request_id')==r['id'] and o.get('reply_to_message_id')==r['origin_message_id'] and o['status']=='SIMULATED' for o in outputs) for r in requests)
                page.locator('[data-view="staff-help"]').click()
                visitor=page.locator('#staffHelpCards > section').filter(has_text='Confirm visitor approval conditions.')
                visitor.get_by_text('Finish this issue',exact=True).click();finish=visitor.locator('[data-help-finish]')
                finish.locator('[name=outcome]').select_option('TEST_COMPLETED');finish.locator('[name=note]').fill('Fictional interface test finished; no real visit or repair occurred.')
                finish.locator('[name=outcome_confirmed]').check();finish.locator('button').click()
                expect(page.locator('#staffHelpNotice')).to_contain_text('Issue finished');expect(page.locator('#staffHelpCards > section')).to_have_count(1)
                page.locator('#staffHelpFilter').select_option('CLOSED');expect(page.locator('#staffHelpCards > section')).to_have_count(1)
                expect(page.locator('#staffHelpCards')).to_contain_text('Test completed · no real repair claimed');expect(page.locator('#staffHelpCards form')).to_have_count(0)
                assert not errors,errors
                with service.store.connect() as db:
                    requests=service.store.all(db,'wa_staff');assert sum(r['status']=='CLOSED' for r in requests)==1 and sum(r['status']=='ANSWERED' for r in requests)==1
                    assert service.store.all(db,'case')[0]['status']!='CLOSED'
                (ROOT/'data').mkdir(exist_ok=True);page.screenshot(path=str(ROOT/'data/staff-help-qa.png'),full_page=True)
                browser.close();print('PASS: independent staff guidance, quoted replies, per-issue test closure/history and continuing chat; no page errors.')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
