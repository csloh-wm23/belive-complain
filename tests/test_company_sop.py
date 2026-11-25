"""Company-source import, retrieval, policy boundaries and withdrawal without real data."""
import json,secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from belive.service import Service
from belive import company_sop as cs,whatsapp as wa,whatsapp_ai
from test_backend import FakeAI
from test_whatsapp import plan,fixture_assessment

class CompanySopTests(unittest.TestCase):
    def setUp(self):
        self.assessment_patch=patch('belive.whatsapp_triage.assess',side_effect=fixture_assessment);self.assessment_patch.start()
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=Service(self.root/'test.db',FakeAI())
        self.pdf=self.root/'company-template.pdf';self.pdf.write_bytes(b'%PDF-1.7\nSynthetic test source only')
        self.pages=['Guests need written permission.','Quiet hours are 10 pm to 8 am. Refund processing may take 30 working days.','Another refund clause says 14 working days.']
        def section(key,title,policy,topics,refs):return {'key':key,'title':title,'policy':policy,'topics':topics,'clauses':'Test clause '+key,'guidance':title+' The supplied template is general guidance; ask staff for decisions or conflicting terms.','quotes':[{'page':p,'text':q} for p,q in refs]}
        self.sections=[section('visitors','Guests need prior written permission','GENERAL_GUIDANCE',['guest','friend'],[(1,self.pages[0])]),
            section('quiet','Quiet hours are 10 pm to 8 am','GENERAL_GUIDANCE',['quiet','noise'],[(2,'Quiet hours are 10 pm to 8 am.')]),
            section('refund','Refund timing has conflicting clauses','CONFLICT_REVIEW',['refund'],[(2,'Refund processing may take 30 working days.'),(3,self.pages[2])])]
        self.issues=[{'title':'Refund conflict','pages':[2,3],'detail':'Company must confirm the applicable term.'}]
    def tearDown(self):self.assessment_patch.stop();self.tmp.cleanup()
    def rows(self,kind):
        with self.s.store.connect() as db:return self.s.store.all(db,kind)
    def cmd(self,name,**p):return self.s.command(name,p,secrets.token_hex(16))
    def imported(self):return cs.import_reviewed(self.s,self.pdf,self.pages,self.sections,self.issues,confirmed=True)
    def test_import_is_private_page_grounded_and_idempotent(self):
        result=self.imported();again=self.imported();self.assertTrue(again['duplicate']);self.assertEqual(len(self.rows('wa_knowledge')),3)
        document=self.rows('sop_document')[0];self.assertTrue(cs.document_path(self.s,document).is_file());self.assertEqual(document['scope'],'COMPANY_TEMPLATE')
        entry=next(x for x in self.rows('wa_knowledge') if x['policy']=='CONFLICT_REVIEW');self.assertEqual(entry['pages'],[2,3]);self.assertIn('pp. 2, 3',entry['source'])
        self.assertNotIn(str(self.root),json.dumps(self.s.snapshot()['whatsapp']))
    def test_bad_quote_or_missing_confirmation_cannot_enable_a_document(self):
        self.sections[0]['quotes'][0]['text']='Invented source sentence.'
        with self.assertRaises(ValueError):self.imported()
        self.assertEqual(self.rows('sop_document'),[]);self.assertEqual(self.rows('wa_knowledge'),[])
        with self.assertRaises(ValueError):cs.import_reviewed(self.s,self.pdf,self.pages,self.sections,self.issues)
    def test_document_disable_excludes_only_its_knowledge_and_reimport_does_not_reenable(self):
        self.imported();self.cmd('wa_knowledge',title='Other approved SOP',text='This is a separate approved support rule.',source='Separate source',confirmed=True)
        d=self.rows('sop_document')[0];self.cmd('wa_document_action',id=d['id'],revision=d['revision'],active=False);self.assertTrue(self.imported()['duplicate'])
        with self.s.store.connect() as db:items=wa.sop(self.s,db,{})
        self.assertEqual(len(items),1);self.assertEqual(items[0]['title'],'Other approved SOP')
    def test_section_toggle_preserves_page_evidence_and_cannot_silently_rewrite_policy(self):
        self.imported();entry=self.rows('wa_knowledge')[0]
        item=self.cmd('wa_knowledge',**{**entry,'active':False,'confirmed':True})
        self.assertEqual(item['document_id'],entry['document_id']);self.assertEqual(item['policy'],entry['policy']);self.assertEqual(item['source_excerpt'],entry['source_excerpt'])
        with self.assertRaises(ValueError):self.cmd('wa_knowledge',**{**item,'text':'Invent a different rule and erase the conflict.','confirmed':True})
    def test_semantic_retrieval_understands_context_and_limits_sources(self):
        self.imported();items=self.rows('wa_knowledge');guest=next(x for x in items if 'Guests' in x['title'])
        with patch('belive.whatsapp_ai.select_sop',return_value=[guest['id']]) as selector:
            selected,uncertain=cs.retrieve(self.s,items,[{'direction':'CUSTOMER','text':'Can my mate crash here?'}])
        self.assertEqual([x['id'] for x in selected],[guest['id']]);self.assertFalse(uncertain);self.assertIn('mate',selector.call_args.args[1][0]['text'])
        with patch('belive.whatsapp_ai.select_sop',return_value=[]):self.assertEqual(cs.retrieve(self.s,items,[{'direction':'CUSTOMER','text':'Hi, thanks!'}])[0],[])
    def test_retrieval_failure_uses_bounded_topic_fallback(self):
        self.imported()
        with patch('belive.whatsapp_ai.select_sop',side_effect=RuntimeError('offline')):
            items,uncertain=cs.retrieve(self.s,self.rows('wa_knowledge'),[{'direction':'CUSTOMER','text':'When is my refund?'}])
        self.assertEqual(len(items),1);self.assertEqual(items[0]['policy'],'CONFLICT_REVIEW');self.assertFalse(uncertain)
    def test_model_cannot_bypass_conflict_with_online_research(self):
        self.imported();entry=next(x for x in self.rows('wa_knowledge') if x['policy']=='CONFLICT_REVIEW')
        draft=plan();draft.update(research='COMPANY',search_query='company deposit return')
        with patch('belive.whatsapp_ai.ask',return_value=draft):r=whatsapp_ai.reply(self.s,{'sop':cs.evidence([entry]),'staff_guidance':[]})
        self.assertTrue(r['needs_staff']);self.assertEqual(r['research'],'NONE');self.assertIn(entry['title'],r['staff_question'])
    def test_staff_confirmed_answer_can_resolve_conflict_without_repeated_escalation(self):
        self.imported();entry=next(x for x in self.rows('wa_knowledge') if x['policy']=='CONFLICT_REVIEW')
        draft=plan();draft['sources_used']=['STAFF-VERIFIED']
        with patch('belive.whatsapp_ai.ask',return_value=draft):r=whatsapp_ai.reply(self.s,{'sop':cs.evidence([entry]),'staff_guidance':[{'id':'STAFF-VERIFIED','verified_solution':'Staff confirmed this case timeline.'}]})
        self.assertFalse(r['needs_staff'])
    def test_reply_records_original_source_pages_and_general_questions_need_no_property(self):
        self.imported();quiet=next(x for x in self.rows('wa_knowledge') if 'Quiet' in x['title']);draft=plan();draft.update(reply='The supplied house rules set quiet hours from 10 pm to 8 am.',sources_used=[quiet['id']])
        r=self.cmd('wa_simulate',customer='test',text='What are the quiet hours?')
        with patch('belive.whatsapp_ai.select_sop',return_value=[quiet['id']]),patch('belive.whatsapp_ai.reply',return_value=draft),patch('belive.whatsapp_ai.review',return_value=True):wa.process_thread(self.s,r['thread_id'])
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['status'],'SIMULATED');self.assertEqual(out['company_evidence'][0]['pages'],[2]);self.assertEqual(self.rows('wa_staff'),[])
    def test_withdrawn_document_cannot_be_sent_from_an_old_queued_reply(self):
        self.imported();entry=next(x for x in self.rows('wa_knowledge') if 'Quiet' in x['title'])
        r=self.cmd('wa_simulate',customer='test',text='What are the quiet hours?')
        draft={**plan(),'reply':'The supplied house rules set quiet hours from 10 pm to 8 am.','sources_used':[entry['id']]}
        # Prepare a genuine queued reply through the current assessment contract, then revoke its source.
        with patch('belive.whatsapp_ai.select_sop',return_value=[entry['id']]),patch('belive.whatsapp_ai.reply',return_value=draft), \
             patch('belive.whatsapp_ai.review',return_value=True),patch('belive.whatsapp.deliver'):
            wa.process_thread(self.s,r['thread_id'])
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['delivery_kind'],'SIMPLE');self.assertEqual(out['status'],'QUEUED')
        d=self.rows('sop_document')[0];self.cmd('wa_document_action',id=d['id'],revision=d['revision'],active=False)
        with patch('belive.whatsapp.request_json',side_effect=AssertionError('No old terms may be sent')):result=wa.deliver(self.s,out['id'])
        self.assertEqual(result['status'],'SUPERSEDED');self.assertTrue(any(x['status']=='PENDING' for x in self.rows('wa_turn')))

if __name__=='__main__':unittest.main()
