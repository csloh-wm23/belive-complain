"""Two real local dashboards sharing a temporary knowledge-only hub; no model/network accounts."""
import sys,tempfile,threading,secrets
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from belive import shared_memory as sm
from belive.memory_hub import Hub,serve
from belive.store import now
from server import make_handler
from test_backend import FakeAI
from unittest.mock import patch

def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);a=Service(root/'a'/'a.db',FakeAI());b=Service(root/'b'/'b.db',FakeAI())
        tokens=[secrets.token_urlsafe(36),secrets.token_urlsafe(36)];wid='MEM-'+secrets.token_hex(12)
        hub=serve(Hub(root/'hub'/'memory.db',wid,{tokens[0]:'Host',tokens[1]:'Peer'}),0);url='http://127.0.0.1:'+str(hub.server_port)
        a.command('wa_knowledge',dict(title='Fictional SOP',text='A fictional company-wide support rule.',source='Reviewed QA source',confirmed=True),secrets.token_hex(16))
        case=a.command('intake',dict(title='[TEST] Wi-Fi source',description='A fictional Wi-Fi question for shared-memory QA.'),secrets.token_hex(16))
        with a.store.connect() as db:
            c=a.store.get(db,'case',case['id']);c.update(status='CLOSED',category='WIFI',sample_data=True);a.store.put(db,'case',c)
            a.store.put(db,'feedback',{'id':'EXP-SHARED-QA','case_id':c['id'],'verdict':'CORRECTED','public_question':'What should I check when Wi-Fi disconnects?','text':'Check whether other devices are affected before changing phone settings.','share':False,'at':now()})
        repository='--repository' in sys.argv;archive_patch=None
        if repository:
            from belive import repository_memory as rm
            archive_patch=patch('belive.repository_memory.ARCHIVE',root/'team-memory.enc.json');archive_patch.start();rm.export(a);rm.restore(b,key=rm.read_key(a))
            with a.store.connect() as db:wid=sm.connection(a,db)['workspace_id']
        else:
            for s,token in [(a,tokens[0]),(b,tokens[1])]:sm.configure(s,{'url':url,'token':token,'workspace_id':wid})
        servers=[ThreadingHTTPServer(('127.0.0.1',0),make_handler(s)) for s in (a,b)]
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers]
        for t in threads:t.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True);pages=[browser.new_page(viewport={'width':1440,'height':1000}) for _ in range(2)];errors=[]
                for i,page in enumerate(pages):
                    page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:'+str(servers[i].server_port));page.locator('#authUsername').fill('shared-qa-'+str(i));page.locator('#authName').fill('Shared QA '+str(i));page.locator('#authPassword').fill('Fictional-shared-test-123');page.locator('#authSubmit').click();expect(page.locator('#operatorApp')).to_be_visible();page.locator('[data-view=memory]').click();expect(page.locator('#sharedMemoryState')).to_contain_text(wid);expect(page.locator('#sharedMemoryCounts')).to_contain_text('1 SOP sections');expect(page.locator('#sharedMemoryCounts')).to_contain_text('1 experience records')
                    assert tokens[0] not in page.locator('body').inner_text() and tokens[1] not in page.locator('body').inner_text()
                    expect(page.locator('[data-case="null"]')).to_have_count(0)
                pa,pb=pages
                if repository:
                    expect(pb.locator('#sharedMemoryPanel')).to_contain_text('not live synchronisation');expect(pb.locator('#sharedMemoryPanel')).to_contain_text('GitHub updates contain code only');expect(pb.locator('#sharedMemoryPanel')).to_contain_text('A key alone cannot restore knowledge');expect(pb.locator('#sharedMemoryPanel')).not_to_contain_text('prepared for the next push');pb.get_by_text('Restore on another computer',exact=True).click();pb.locator('#sharedMemoryImportKey').set_input_files(str(rm.key_path(a)));expect(pb.locator('#sharedMemoryNotice')).to_contain_text('Restored 2 knowledge records');expect(pb.locator('#sharedMemoryPanel')).not_to_contain_text('Connect GitHub')
                pa.locator('[data-view=whatsapp]').click();pa.get_by_text('Company-approved SOP',exact=True).click();f=pa.locator('#waSop');f.locator('[name=title]').fill('Second shared SOP');f.locator('[name=text]').fill('Another fictional approved general rule.');f.locator('[name=source]').fill('Reviewed QA source');f.locator('[name=confirmed]').check();f.locator('button').click();pa.locator('[data-view=memory]').click();expect(pa.locator('#sharedMemoryCounts')).to_contain_text('2 SOP sections',timeout=15000)
                if repository:rm.export(a);rm.restore(b)
                else:sm.sync(b)
                pb.evaluate("window.dispatchEvent(new Event('belive:refresh'))");expect(pb.locator('#sharedMemoryCounts')).to_contain_text('2 SOP sections')
                pb.locator('#sharedMemoryLessons').locator('..').locator('summary').click();button=pb.locator('[data-memory-toggle="experience:EXP-SHARED-QA"]');button.click();expect(pb.locator('#sharedMemoryLessons')).to_contain_text('Revoked')
                if repository:rm.export(b);rm.restore(a)
                else:sm.sync(a)
                sm.sync(a);pa.evaluate("window.dispatchEvent(new Event('belive:refresh'))");expect(pa.locator('#memoryExamples')).not_to_contain_text('Check whether other devices')
                button=pb.locator('[data-memory-toggle="experience:EXP-SHARED-QA"]');button.click();expect(pb.locator('#sharedMemoryLessons')).to_contain_text('Enabled')
                if repository:rm.export(b);rm.restore(a)
                else:sm.sync(a)
                pa.evaluate("window.dispatchEvent(new Event('belive:refresh'))");expect(pa.locator('#memoryExamples')).to_contain_text('Check whether other devices')
                assert not errors,errors;pa.screenshot(path=str(ROOT/'output/whatsapp-shared-memory-browser.png'),full_page=True);browser.close()
            print('PASS: two separate dashboards show one workspace and the same approved memory; SOP addition, peer revoke, no resurrection, restore, privacy and shared-source labels; no page errors.')
        finally:
            for s in servers:s.shutdown();s.server_close()
            for t in threads:t.join()
            hub.shutdown();hub.server_close()
            if archive_patch:archive_patch.stop()
if __name__=='__main__':main()
