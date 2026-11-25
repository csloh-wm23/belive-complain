"""Headless admin connection-settings check, temporary DB, no provider requests."""
import json,os,secrets,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from belive import credentials as c
from server import make_handler
from test_backend import FakeAI


def main():
    with tempfile.TemporaryDirectory() as tmp:
        directory=Path(tmp);environment_key=secrets.token_urlsafe(40);saved_key=secrets.token_urlsafe(40)
        with patch('belive.settings.ROOT',directory),patch.dict(os.environ,{'BELIVE_AI_PROVIDER':'openai','BELIVE_AI_MODEL':'fixture-model','BELIVE_AI_KEY':environment_key}):
            service=Service(directory/'test.db',FakeAI());server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(channel='chrome',headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto('http://127.0.0.1:'+str(server.server_port));page.locator('#authUsername').fill('credentials-qa');page.locator('#authName').fill('Credential QA');page.locator('#authPassword').fill('Fictional-QA-password-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible();page.get_by_text('System setup',exact=True).click();page.locator('[data-view=settings]').click()
                    panel=page.locator('#credentialSettingsPanel');expect(panel).to_be_visible();expect(panel).to_contain_text('Using .env / environment')
                    secret=panel.locator('[name=BELIVE_AI_KEY]');expect(secret).to_have_value('');secret.fill(saved_key);panel.get_by_role('button',name='Save connection settings',exact=True).click();expect(page.locator('#credentialNotice')).to_contain_text('Saved encrypted settings')
                    expect(secret).to_have_value('');assert c.get_value('BELIVE_AI_KEY',database=service.store.path)==saved_key
                    text=page.locator('body').inner_text();assert saved_key not in text and environment_key not in text
                    panel.screenshot(path=str(ROOT/'output/whatsapp-credential-settings-qa.png'))
                    panel.get_by_role('button',name='Use .env settings instead',exact=True).click();expect(page.locator('#credentialNotice')).to_contain_text('Stored overrides removed');assert c.get_value('BELIVE_AI_KEY',database=service.store.path)==environment_key
                    assert not errors,errors;browser.close()
                print('PASS: headless settings UI, encrypted save, blank/masked secrets, private source status and explicit environment fallback; no browser errors or provider requests. Temporary database only.')
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
