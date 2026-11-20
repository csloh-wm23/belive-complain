"""Test the publish button with a simulated Google API, never a live post."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from server import make_handler
from test_backend import FakeAI


def main():
    with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'BELIVE_GOOGLE_TOKEN':'test-token','BELIVE_GOOGLE_REPLY_ENABLED':'true'}):
        service=Service(Path(tmp)/'test.db',FakeAI())
        service.command('source',dict(platform='GOOGLE',resource='accounts/123/locations/456',authorised=True),'google-source-fixture')
        case=service.command('intake',dict(title='Fictional Google washer complaint',description='The shared washer stopped working.',platform='GOOGLE',source_id='accounts/123/locations/456/review-789'),'google-case-fixture')
        case=service.command('case_action',dict(id=case['id'],revision=case['revision'],action='acknowledge',owner='QA staff'),'google-owner-fixture')
        service.command('case_action',dict(id=case['id'],revision=case['revision'],action='draft',note='Sorry about the washer problem. Please contact BeLive privately.'),'google-draft-fixture')
        name='accounts/123/locations/456/reviews/review-789'
        text='Sorry about the reported washer issue. Please share your location with BeLive privately.'
        responses=[dict(name=name,comment=case['description']),dict(comment=text,updateTime='2026-11-19T12:00:00Z')]
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('belive.google_replies.request_json',side_effect=responses) as google,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport={'width':1280,'height':900});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/?case='+case['id'])
                page.locator('#authUsername').fill('posting-qa');page.locator('#authName').fill('Posting QA')
                page.locator('#authPassword').fill('Isolated-browser-password-123');page.locator('#authSubmit').click()
                expect(page.locator('#caseDialog')).to_be_visible()
                page.locator('#publicReplyText').fill(text)
                page.locator('[data-publish-google]').click()
                expect(page.locator('#caseError')).to_contain_text('confirm public posting')
                assert google.call_count==0
                page.locator('#googleReplyConfirmed').check()
                page.locator('[data-publish-google]').click()
                expect(page.locator('.google-publishing [role=status]')).to_contain_text('POSTED')
                assert google.call_count==2
                assert google.call_args.kwargs==dict(payload={'comment':text},method='PUT')
                assert not errors,errors
                browser.close()
                print('PASS: Google publish button, reviewed exact edited text, confirmation required, official PUT, confirmed status, no page errors. Google API was mocked; no external post sent.')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
