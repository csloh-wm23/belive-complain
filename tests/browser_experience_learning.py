"""Exercise actual learning UI with approved sample experience and a labelled test AI."""
import sys
import secrets
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from server import make_handler
from test_experience_learning import ExperienceAI


def main():
    with tempfile.TemporaryDirectory() as tmp:
        ai=ExperienceAI();service=Service(Path(tmp)/'test.db',ai)
        def cmd(name,p):return service.command(name,p,secrets.token_hex(16))
        def approve(title,question,answer):
            c=cmd('intake',dict(title=title,description='Fictional sample: '+question))
            c=cmd('case_action',dict(id=c['id'],revision=c['revision'],action='acknowledge',owner='QA staff'))
            cmd('case_action',dict(id=c['id'],revision=c['revision'],action='verify_staff_close',note='Staff checked this fictional sample outcome.',confirmed=True))
            return cmd('feedback',dict(id=c['id'],verdict='CORRECTED',text=answer,public_question=question,publish_public=True))
        wifi=approve('[TEST] Wi-Fi learning sample','What information helps report a Wi-Fi connection problem?','Tell us which devices disconnect and when the connection drops.')
        approve('[TEST] Water pressure sample','What information helps report weak water pressure?','Tell us which taps are affected and when the water pressure drops.')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1360,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url)
                page.locator('#authUsername').fill('experience-qa');page.locator('#authName').fill('Experience QA')
                page.locator('#authPassword').fill('Isolated-browser-password-123');page.locator('#authSubmit').click()
                expect(page.locator('#operatorApp')).to_be_visible()
                page.locator('[data-view=memory]').click()
                expect(page.locator('#memoryExamples')).to_contain_text('Sample / test complaint experience')
                expect(page.locator('#memoryExamples')).to_contain_text('Fictional data, not a real customer outcome')
                page.locator('#learningTopic').select_option('OTHER')
                question='Can you read my message? I have an issue and do not know what to include.'
                page.locator('#learningQuestion').fill(question)
                page.locator('#learningStart button').click()
                expect(page.locator('#learningNoExperience')).to_be_visible(timeout=20000)
                expect(page.locator('#learningImprove')).to_be_hidden()
                expect(page.locator('#learningLesson')).to_have_value('')
                expect(page.locator('#learningComparison')).to_contain_text('What would you like help with?')
                assert 'room number' not in page.locator('#learningComparison').inner_text()
                assert ai.seen[-1][1] is None
                page.locator('#learningExperience').select_option(wifi['id'])
                paraphrase='What should I record about Wi-Fi disconnecting on my phone every evening?'
                page.locator('#learningQuestion').fill(paraphrase)
                page.locator('#learningStart button').click()
                expect(page.locator('#learningImprove')).to_be_visible(timeout=20000)
                expect(page.locator('#learningExperienceSource')).to_contain_text(wifi['case_id'])
                expect(page.locator('#learningExperienceSource')).to_contain_text('Sample / test complaint experience')
                expect(page.locator('#learningLesson')).to_have_value(wifi['text'])
                assert page.locator('#learningLesson').get_attribute('readonly') is not None
                page.locator('#learningImprove button').click()
                expect(page.locator('#learningStatus')).to_contain_text('does not prove',timeout=20000)
                expect(page.locator('#learningComparison')).to_contain_text(wifi['text'])
                assert ai.seen[-1][1]['id']==wifi['id']
                assert 'two numbered' not in page.locator('#learningLessonCard').inner_text().lower()
                output=ROOT/'artifacts';output.mkdir(exist_ok=True)
                for width in (1360,390):
                    page.set_viewport_size({'width':width,'height':1000})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                    page.screenshot(path=str(output/f'approved-experience-{width}.png'),full_page=True)
                customer=context.new_page();customer.on('pageerror',lambda e:errors.append(str(e)))
                customer.goto(url+'/portal?view=make')
                assert not customer.locator('[name=rental_property]').is_visible()
                assert customer.locator('[name=rental_property]').get_attribute('required') is None
                customer.locator('#websiteComplaint [name=title]').fill('General support message')
                customer.locator('#websiteComplaint [name=description]').fill('Can you read my message? I need help understanding the complaint process.')
                with customer.expect_response('**/api/website/complaints') as response:customer.locator('#sendWebsiteComplaint').click()
                assert response.value.ok,response.value.text()
                receipt=response.value.json()
                with service.store.connect() as db:assert not service.store.get(db,'case',receipt['id']).get('reported_location')
                assert not errors,errors
                context.close();browser.close()
                print('PASS: General support has no unrelated lesson or room request; paraphrased Wi-Fi question uses exact approved experience with source and sample label; no fixed writing tip; no duplicate learning; general complaint submits without location; desktop/mobile, no page errors. AI was a labelled test double.')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
