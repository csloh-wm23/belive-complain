"""Local browser QA in an isolated context. No provider or customer calls."""
import sys
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import Handler

def main():
    output=ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1100})
            page=context.new_page()
            errors=[]
            external=[]
            page.on('pageerror',lambda e: errors.append(str(e)))
            page.on('request',lambda req: external.append(req.url) if not req.url.startswith(url) else None)
            page.goto(url)
            page.locator('#recentCases [data-case="BL-1004"]').wait_for()
            assert page.locator('.metric').count()==4
            page.screenshot(path=str(output/'overview-desktop.png'),full_page=True)
            page.locator('[data-metric="OPEN"]').click()
            assert page.locator('#caseRows tr').count()==3
            assert page.locator('#statusFilter').input_value()=='OPEN'
            page.locator('#search').fill('duplicate')
            assert page.locator('#caseRows tr').count()==1
            page.locator('[data-view="workflow"]').click()
            page.screenshot(path=str(output/'workflow-desktop.png'),full_page=True)
            page.locator('#newCase').click()
            page.locator('[name="title"]').fill('A separate prototype test case')
            page.locator('textarea[name="description"]').fill('Test report with private email sample@example.com and +60123456789.')
            page.locator('[name="severity"]').select_option('HIGH')
            page.get_by_role('button',name='Create local case').click()
            page.locator('#caseDialog[open]').wait_for()
            case_id=page.locator('#caseDetail .eyebrow').inner_text().split(' · ')[0]
            assert 'sample@example.com' not in page.locator('.case-description').inner_text()
            page.locator('[data-act="acknowledge"]').click()
            assert 'staff name' in page.locator('#caseError').inner_text()
            page.locator('#caseOwner').fill('Prototype support team')
            page.locator('[data-act="acknowledge"]').click()
            page.locator('#caseDraft').fill('Please explain which step was unclear before trying further changes.')
            page.locator('[data-act="draft"]').click()
            page.locator('#caseNote').fill('The operator recorded a clarification and is waiting for confirmation.')
            page.locator('[data-act="followup"]').click()
            page.locator('[data-act="verify"]').click()
            assert 'meaningful' in page.locator('#caseError').inner_text()
            page.locator('#caseNote').fill('Fictional test verification: the example customer confirmed the clarification.')
            page.locator('[data-act="verify"]').click()
            page.locator('[data-act="close"]').click()
            page.locator('[data-feedback="APPROVED"]').click()
            page.locator('[data-close="caseDialog"]').click()
            page.locator('[data-view="memory"]').click()
            assert page.locator('.example-card').count()==2
            page.screenshot(path=str(output/'memory-desktop.png'),full_page=True)
            page.locator(f'[data-revoke="{case_id}"]').click()
            assert page.locator('.example-card').count()==1
            page.reload()
            page.locator('#recentCases').get_by_text('A separate prototype test case').wait_for()
            page.locator('[data-view="memory"]').click()
            assert page.locator('.example-card').count()==1
            page.locator('[data-view="overview"]').click()
            page.set_viewport_size({'width':390,'height':844})
            for name in ['overview','cases','workflow','memory','activity']:
                page.locator(f'[data-view="{name}"]').click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),name
            page.locator('[data-view="overview"]').click()
            page.screenshot(path=str(output/'overview-mobile.png'),full_page=True)
            # Corrupt saved data must not be silently overwritten by sample data.
            page.evaluate("localStorage.setItem('belive-complaints-prototype:v1', '{broken')")
            page.reload()
            assert 'read-only' in page.locator('#notice').inner_text()
            assert page.evaluate("localStorage.getItem('belive-complaints-prototype:v1')")=='{broken'
            assert errors==[],errors
            assert external==[],external
            browser.close()
        print('PASS: case lifecycle, invalid guards, redaction, memory revocation, persistence, corrupt storage, five mobile views, no JS errors or external requests.')
    finally:
        server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':main()
