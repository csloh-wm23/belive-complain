"""Genuine Hermes work-status relay and worker reuse; all WhatsApp sends simulated."""
import json,secrets,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from belive.service import Service
from belive.settings import load_settings
from belive.workspace import selected_database
from belive import whatsapp as wa
from belive.hermes_native import close_workers
from rehearse_autonomous_support import seed_approved

def main():
    src=selected_database();settings=load_settings(src);assert settings.agent_engine=='hermes' and settings.llm_provider=='openai'
    folder=ROOT/'data/support-experience-native'/secrets.token_hex(4);folder.mkdir(parents=True)
    s=Service(folder/'qa.db');s.settings=settings;s.ai.settings=settings;seed_approved(s,src)
    def cmd(action,**p):return s.command(action,p,secrets.token_hex(16))
    def rows(kind):
        with s.store.connect() as db:return s.store.all(db,kind)
    def stage(state):
        r=rows('wa_staff')[0];return cmd('maintenance_progress',request_id=r['id'],request_revision=r['revision'],state=state,note='Fictional checked stage for isolated rehearsal; no real dispatch or repair.',confirmed=True)
    def send(text):
        r=cmd('wa_simulate',customer='work-progress-qa',text=text);wa.process_thread(s,r['thread_id']);out=rows('wa_outgoing')[0];assert out['status']=='SIMULATED';return out
    try:
        first=send('公共洗衣房洗衣机的启动按钮掉下来了，现在没法启动。没有漏水、焦味或冒烟，位置是测试屋 QA-WORK-HOUSE 的公共洗衣区。怎么办？')
        request=rows('wa_staff')[0];assert request.get('maintenance') and request.get('location_complete')
        stage('ACCEPTED')
        progress=send('刚刚那个洗衣机的问题，现在有进展了吗？')
        stage('IN_PROGRESS');stage('WORK_DONE')
        assert rows('wa_staff')[0]['status']!='CLOSED'
        completed=send('洗衣机那边最新是什么情况？')
        request=rows('wa_staff')[0]
        cmd('wa_staff_complete',thread_id=request['thread_id'],request_id=request['id'],request_revision=request['revision'],outcome='TEST_COMPLETED',note='Genuine native Hermes internal work-state relay rehearsal complete; no real repair or dispatch.',confirmed=True)
        runs=rows('native_execution');assert all(r['engine']=='hermes-native' and r['agent_class']=='run_agent.AIAgent' and r['api_calls']>0 for r in runs)
        report={'first':{k:first.get(k) for k in ('text','handling','steps')},'accepted_update':{k:progress.get(k) for k in ('text','handling','delivery_kind','request_id','decision_trace')},'work_done_update':{k:completed.get(k) for k in ('text','handling','delivery_kind','request_id','decision_trace')},
            'final_test_status':rows('wa_staff')[0]['closure_reason'],'warm_native_runs':[{k:r.get(k) for k in ('role','reused_worker','api_calls','elapsed_ms')} for r in runs], 'customer_records':len(rows('customer_profile'))}
        (folder/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True))
    finally:close_workers()

if __name__=='__main__':main()
