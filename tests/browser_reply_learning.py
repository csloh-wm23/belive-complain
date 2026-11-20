"""Exercise dissatisfied customer → reviewed tip → test → later reuse → revoke."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from server import make_handler
from test_reply_learning import FeedbackAI


def main():
    with tempfile.TemporaryDirectory() as tmp:
        ai=FeedbackAI();service=Service(Path(tmp)/'test.db',ai)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1360,'height':1000})
                staff=context.new_page();customer=context.new_page();errors=[]
                for page in (staff,customer):page.on('pageerror',lambda e:errors.append(str(e)))
                staff.goto(url);staff.locator('#authUsername').fill('reply-learning-qa');staff.locator('#authName').fill('Reply Learning QA')
                staff.locator('#authPassword').fill('Isolated-browser-password-123');staff.locator('#authSubmit').click()
                expect(staff.locator('#operatorApp')).to_be_visible()
                # Create the source via service so the first reply is deliberately unhelpful fixture text.
                import secrets
                receipt=service.website_submit(dict(title='[TEST] Unhelpful room question',description='Can you read my message? I need general help with this support page.'),secrets.token_hex(16))
                cid=receipt['id']
                def act(name,**fields):
                    with service.store.connect() as db:c=service.store.get(db,'case',cid)
                    return service.command('case_action',dict(id=cid,revision=c['revision'],action=name,**fields),secrets.token_hex(16))
                act('acknowledge',owner='QA staff');act('send_reply',reviewed_reply='Please provide your room number first.',confirmed=True)
                # Existing Complaint Code access remains usable for this isolated fixture.
                customer.goto(url+'/portal?view=track')
                response=customer.request.post(url+'/api/portal/update',headers={'Authorization':'Bearer '+receipt['complaint_code'],'Idempotency-Key':secrets.token_hex(16)},data={'id':cid,'note':'I already told you I need general help. Your room question does not help.'})
                assert response.ok,response.text()
                staff.locator('[data-view=memory]').click()
                expect(staff.locator('[data-reply-feedback]')).to_have_count(1,timeout=20000)
                row=staff.locator('[data-reply-feedback]').first
                expect(row).to_contain_text('Improvement tip needs your review',timeout=20000)
                expect(row).to_contain_text('Please provide your room number first.')
                expect(row).to_contain_text('I already told you')
                expect(row).to_contain_text('SAMPLE / TEST')
                item_id=row.get_attribute('data-reply-feedback')
                tip='Acknowledge what the customer already said. Ask what help is needed before requesting location, and do not repeat questions already answered.'
                row.locator('[data-feedback-tip]').fill(tip)
                row.get_by_role('button',name='Approve & use writing tip',exact=True).click()
                expect(staff.locator('#replyFeedbackStatus')).to_contain_text('Review this as reusable writing advice')
                row.locator('[data-tip-confirm]').check()
                row.get_by_role('button',name='Approve & use writing tip',exact=True).click()
                expect(row).to_contain_text('Approved for relevant future replies',timeout=20000)
                with service.store.connect() as db:before=service.store.all(db,'message')
                row.get_by_role('button',name='Test improved reply',exact=True).click()
                expect(row).to_contain_text('New draft using the reviewed tip',timeout=20000)
                with service.store.connect() as db:assert service.store.all(db,'message')==before
                staff.locator('#learningTopic').select_option('OTHER')
                staff.locator('#learningQuestion').fill('Can you help me understand this message?')
                staff.locator('#learningStart button').click()
                expect(staff.locator('#learningImprove')).to_be_visible(timeout=20000)
                expect(staff.locator('#learningLesson')).to_have_value(tip)
                expect(staff.locator('#learningExperienceSource')).to_contain_text('Approved writing improvement from customer feedback')
                staff.locator('#learningImprove button').click()
                expect(staff.locator('#learningComparison')).to_contain_text('Approved feedback-derived writing tip',timeout=20000)
                later=service.website_submit(dict(title='[TEST] Later general question',description='Hello, can you understand my message? I need some help.'),secrets.token_hex(16))
                service.analyse(later['id']);assert ai.tips and ai.tips[0]['id']==item_id
                output=ROOT/'artifacts';output.mkdir(exist_ok=True)
                staff.screenshot(path=str(output/'feedback-writing-tips.png'),full_page=True)
                row=staff.locator(f'[data-reply-feedback="{item_id}"]')
                row.get_by_role('button',name='Reject / revoke tip',exact=True).click()
                expect(row).to_contain_text('Tip revoked',timeout=20000)
                from belive.reply_learning import matching
                with service.store.connect() as db:assert matching(service,db,'Can you help me understand this message?')==[]
                assert not errors,errors
                context.close();browser.close()
                print('PASS: real reply/feedback evidence, background proposal, editable tip, explicit approval and safety review, unsent improved draft, general comparison with feedback-derived writing tip, later reply retrieval, sample label, immediate revocation; no page errors. Temporary data and labelled test AI only.')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
