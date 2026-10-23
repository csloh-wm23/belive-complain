"""Opt-in real-model evaluation. Never inserts fixtures into the operator database."""
import argparse
import json
import secrets
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from belive.service import Service
from belive.store import now

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live',action='store_true',help='Make real configured-provider calls; provider charges may apply')
    parser.add_argument('--limit',type=int,default=24);parser.add_argument('--output',type=Path,default=ROOT/'artifacts/ai-evaluation.json')
    args=parser.parse_args();cases=json.loads((ROOT/'evals/tenant_support.json').read_text(encoding='utf-8'))[:max(1,min(args.limit,24))]
    if not args.run_live:
        print(f'{len(cases)} fictional evaluation cases ready (English, Malay and Chinese). No AI requests were made. Use --run-live to evaluate the configured provider.');return
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'evaluation.db')
        if not service.ai.readiness():raise SystemExit('AI_NOT_CONFIGURED: configure this project before running live evaluation')
        def command(name,p):return service.command(name,p,secrets.token_hex(16))
        command('condo',dict(id='EVAL',name='Fictional evaluation property',rules='No verified quiet-hours schedule is supplied in this fixture. Ask staff for confirmed rules.',confirmed=True))
        command('tenant',dict(id='TEST-TENANT',condo_id='EVAL',unit_ref='TEST-ROOM',verified_by='Evaluation fixture',evidence='Fictional test tenancy, not a real customer.',confirmed=True))
        results=[]
        for case in cases:
            record=command('intake',dict(title='Fictional evaluation '+case['id'],description=case['text'],tenant_id='TEST-TENANT'))
            job=None
            if record['status']!='HUMAN_REVIEW':job=service.analyse(record['id'])
            with service.store.connect() as db:current=service.store.get(db,'case',record['id'])
            valid=job is None or job['status']=='COMPLETED'
            category_ok=case['critical'] or current['category']==case['expected_category']
            handoff_ok=case['handoff_required'] is not True or current['status']=='HUMAN_REVIEW'
            results.append({'id':case['id'],'language':case['language'],'valid_output':valid,'category_correct':category_ok,'required_handoff_correct':handoff_ok,
                            'passed':valid and category_ok and handoff_ok,'category':current['category'],'severity':current['severity'],'status':current['status'],
                            'response':current['draft'],'needs_human_language_and_factual_review':True})
        report={'at':now(),'fixture_only':True,'model':service.settings.llm_model,'count':len(results),'passed':sum(x['passed'] for x in results),'results':results,
                'limits':'Automated checks cover schema, expected category and required handover. A human must review language quality, factual claims and usefulness.'}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"Completed {len(results)} real-provider evaluation cases: {report['passed']} passed automated checks. Human review is still required. Report: {args.output}")
if __name__=='__main__':main()
