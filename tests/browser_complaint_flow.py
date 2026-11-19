"""Exercise simplified staff handling with anonymous customer UI and isolated data."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from datetime import datetime, timedelta
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from belive.service import Service
from server import make_handler
from test_backend import FakeAI


def main():
    with tempfile.TemporaryDirectory() as tmp:
        service = Service(Path(tmp) / 'test.db', FakeAI())
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='chrome', headless=True)
                context = browser.new_context(viewport={'width': 1360, 'height': 900})
                errors = []
                staff, customer = context.new_page(), context.new_page()
                for page in (staff, customer):
                    page.on('pageerror', lambda e: errors.append(str(e)))
                staff.goto(url)
                staff.locator('#authUsername').fill('workflow-qa')
                staff.locator('#authName').fill('Workflow QA')
                staff.locator('#authPassword').fill('Isolated-test-password-123')
                staff.locator('#authSubmit').click()
                expect(staff.locator('#operatorApp')).to_be_visible()
                staff.locator('.system-tools > summary').click()
                staff.locator('[data-view=settings]').click()
                staff.get_by_role('button',name='Staff routing',exact=True).click()
                staff.locator('#closureDays').fill('7')
                staff.locator('#closureForm button').click()
                expect(staff.locator('#closureStatus')).to_contain_text('7 days')
                customer.goto(url + '/portal?view=make')
                form = customer.locator('#websiteComplaint')
                form.locator('[name=rental_property]').fill('QA Fictional Residence')
                form.locator('[name=title]').fill('QA electrical repair workflow')
                form.locator('[name=description]').fill('Smoke and sparks from a socket in the shared laundry room. Fictional QA test.')
                with customer.expect_response('**/api/website/complaints') as response:
                    customer.locator('#sendWebsiteComplaint').click()
                receipt = response.value.json()
                cid = receipt['id']
                expect(customer.locator('[data-case-state=HUMAN_REVIEW]')).to_be_visible()

                # A new page in this browser remembers the submitted case.
                customer.goto(url + '/portal?view=track')
                expect(customer.locator('#requestList')).to_contain_text('QA electrical repair workflow')
                customer.locator(f'[data-open-request="{cid}"]').click()
                expect(customer.locator('#tenantCases')).to_contain_text('QA electrical repair workflow')
                assert 'complaint_code' not in receipt
                stranger=browser.new_page()
                stranger.goto(url + '/portal?view=track&case=' + cid)
                expect(stranger.locator('#requestList')).to_contain_text('No complaints are saved in this browser')
                stranger.close()
                staff.goto(url + '/?case=' + cid)
                expect(staff.locator('#caseDialog')).to_be_visible()
                expect(staff.get_by_role('heading', name='Case progress', exact=True)).to_be_visible()
                assert staff.locator('[data-act=link_tenant],[data-act=workorder],[data-act=queue_response],[data-act=draft],[data-act=verify]').count() == 0
                staff.get_by_role('button', name='Take ownership', exact=True).click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Staff handling')
                reply = 'Please avoid the affected socket. Maintenance is checking it and we will update you here.'
                staff.locator('#caseDraft').fill(reply)
                staff.get_by_role('button', name='Send reply', exact=True).click()
                expect(staff.locator('#caseError')).to_contain_text('Review the reply before sending')
                staff.locator('#caseConfirmed').check()
                staff.get_by_role('button', name='Send reply', exact=True).click()
                expect(staff.locator('#caseDetail .conversation')).to_contain_text(reply)
                customer.locator('#refreshPortal').click()
                expect(customer.locator('#tenantCases')).to_contain_text(reply)
                customer.locator('[data-note]').fill('Thank you. The socket is beside the laundry door.')
                customer.locator('[data-update]').click()
                expect(customer.locator('[data-case-notice]')).to_contain_text('saved')

                def reload_case():
                    staff.locator('[data-more] > summary').click()
                    staff.locator('#reloadCase').click()
                    expect(staff.locator('#caseDialog')).to_be_visible()

                reload_case()
                expect(staff.locator('#caseDetail .conversation')).to_contain_text('beside the laundry door')
                staff.locator('#caseNote').fill('PRIVATE: maintenance repaired and checked the socket.')
                staff.get_by_role('button', name='Mark handled · ask customer to confirm', exact=True).click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Follow-up')
                assert staff.locator('[data-act=verify_close]').count() == 0
                customer.locator('#refreshPortal').click()
                assert 'PRIVATE:' not in customer.locator('#tenantCases').inner_text()
                customer.locator('[data-resolved]').click()
                expect(customer.locator('[data-case-state=FOLLOW_UP]')).to_contain_text('You confirmed')
                reload_case()
                staff.locator('#caseNote').fill('Customer confirmed resolution after the maintenance check.')
                staff.locator('#caseResolutionConfirmed').check()
                staff.get_by_role('button', name='Close complaint', exact=True).click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Closed')
                expect(staff.get_by_role('heading', name='Teach future replies')).to_be_visible()
                customer.locator('#refreshPortal').click()
                expect(customer.locator('[data-case-state=CLOSED]')).to_be_visible()

                # Returning after closure must reopen for staff rather than stay closed.
                customer.locator('[data-note]').fill('The same fault returned. Please ask maintenance to check again.')
                customer.locator('[data-unresolved]').click()
                expect(customer.locator('[data-case-state=HUMAN_REVIEW]')).to_be_visible()
                reload_case()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Needs staff')
                staff.locator('[data-act=acknowledge]').click()
                staff.locator('#caseNote').fill('The returning fault has been repaired and checked again.')
                staff.locator('[data-act=followup]').click()
                customer.locator('#refreshPortal').click()
                customer.locator('[data-resolved]').click()
                expect(customer.locator('[data-case-state=FOLLOW_UP]')).to_contain_text('You confirmed')
                reload_case()
                staff.locator('#caseNote').fill('Customer confirmed the repeat repair solved the issue.')
                staff.locator('#caseResolutionConfirmed').check()
                staff.locator('[data-act=verify_close]').click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Closed')

                # Age only this temporary case to exercise the real scheduler without waiting seven days.
                staff.locator('#caseNote').fill('Reopen the fictional case to test the no-reply policy.')
                staff.locator('[data-act=reopen]').click()
                staff.locator('[data-act=acknowledge]').click()
                staff.locator('#caseNote').fill('Staff completed another fictional check; waiting for customer.')
                staff.locator('[data-act=followup]').click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Follow-up')
                with service.store.connect() as db:
                    case=service.store.get(db,'case',cid)
                expiry=datetime.fromisoformat(case['waiting_since'])+timedelta(days=7)
                with patch('belive.service.now',return_value=expiry.isoformat()):service.tick()
                customer.locator('#refreshPortal').click()
                expect(customer.locator('[data-case-state=CLOSED]')).to_contain_text('Closed after no reply')
                reload_case()
                expect(staff.locator('#caseDetail')).to_contain_text('Resolution was not confirmed')
                assert staff.locator('[data-feedback]').count()==0
                customer.locator('[data-note]').fill('I am back after the waiting period. Please investigate the returning fault.')
                customer.locator('[data-update]').click()
                expect(customer.locator('[data-case-state=HUMAN_REVIEW]')).to_be_visible()
                reload_case()
                staff.locator('[data-act=acknowledge]').click()
                staff.locator('#caseNote').fill('The returning customer request was checked and handled.')
                staff.locator('[data-act=followup]').click()
                customer.locator('#refreshPortal').click()
                customer.locator('[data-resolved]').click()
                expect(customer.locator('[data-case-state=FOLLOW_UP]')).to_contain_text('You confirmed')
                reload_case()
                staff.locator('#caseNote').fill('Staff checked the customer confirmation after the final repair.')
                staff.locator('#caseResolutionConfirmed').check()
                staff.locator('[data-act=verify_close]').click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Closed')
                for width in (1360, 390):
                    staff.set_viewport_size({'width': width, 'height': 900})
                    assert staff.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    output = ROOT / 'artifacts' / f'complaint-simplified-{width}.png'
                    output.parent.mkdir(exist_ok=True)
                    staff.locator('#caseDialog').evaluate('(el) => el.scrollTop = 0')
                    staff.screenshot(path=str(output))
                public=service.command('intake',{
                    'title':'Fictional public review for closure',
                    'description':'A shared washing machine broke down at a fictional property.',
                    'public_url':'https://www.google.com/maps/place/Fictional+Residence'
                },'browser-public-close-fixture')
                staff.goto(url + '/?case=' + public['id'])
                staff.get_by_role('button', name='Take ownership', exact=True).click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Staff handling')
                staff.locator('#caseNote').fill('Fictional maintenance record confirms the washer passed an operating check.')
                staff.get_by_role('button', name='Close complaint', exact=True).click()
                expect(staff.locator('#caseError')).to_contain_text('Confirm resolution against evidence')
                staff.locator('#caseResolutionConfirmed').check()
                staff.get_by_role('button', name='Close complaint', exact=True).click()
                expect(staff.locator('#caseDetail .case-tags')).to_contain_text('Closed')
                assert not errors, errors
                snapshot = service.snapshot()
                assert not any(c['status'] in {'HUMAN_REVIEW', 'FOLLOW_UP', 'IN_PROGRESS'} for c in snapshot['cases'])
                print('PASS: formal anonymous complaint, same-browser tracking and session isolation, take ownership, one-click edited reply, privacy, confirmation gate, private and public closure, reopening, saved seven-day policy, timed inactivity closure, message reopening, desktop/mobile; no page errors; temporary queues empty.')
                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
