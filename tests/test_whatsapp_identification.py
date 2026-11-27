"""Identification search permissions, typed evidence and scoped lookup reuse."""
import base64,os,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import test_whatsapp as fixture
from test_whatsapp import plan,fixture_assessment
from belive import whatsapp as wa,photo_context,wa_research

class IdentificationTests(unittest.TestCase):
    setUp=fixture.WhatsAppTests.setUp;tearDown=fixture.WhatsAppTests.tearDown
    rows=fixture.WhatsAppTests.rows;cmd=fixture.WhatsAppTests.cmd;incoming=fixture.WhatsAppTests.incoming;process=fixture.WhatsAppTests.process
    def found(self):return {'summary':'Official evidence of a possible product family, not confirmed identity.','sources':[{'id':'WEB-QA','url':'https://www.samsung.com/support/','kind':'TECHNICAL','title':'Fictional QA evidence'}]}
    def test_identification_lookup_can_run_before_photo_code_or_device_is_confirmed(self):
        def assess(s,c):
            a=fixture_assessment(s,c);pid=c['current_photo']['message_id']
            a.update(severity='MEDIUM',uncertainty=True,research='TECHNICAL',research_purpose='IDENTIFICATION',search_query='fictional product series official identification',photo_message_id=pid,photo_context_message_ids=[pid],unavailable_details=['BRAND','MODEL','LABEL']);return a
        self.assessment.side_effect=assess
        self.reply.return_value={**plan(),'handling':'ANSWER','reply':'The official source suggests a possible family. Does the programme start or stop immediately?','sources_used':['WEB-QA']}
        image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
        with patch('belive.whatsapp_ai.read_photo',return_value={'observations':'A visible series badge','brand':'','model':'','error_code':'E06','uncertain':True}),patch('belive.whatsapp_ai.research',return_value=self.found()) as search:
            self.process(self.incoming('I cannot find the brand, model or label.',image=image))
        search.assert_called_once_with(self.s,'fictional product series official identification','TECHNICAL',purpose='IDENTIFICATION')
        context=self.review.call_args.args[1]
        self.assertTrue(context['identification_only']);self.assertTrue(context['photo_confirmation_required'])
        self.assertEqual(context['unavailable_details'],['BRAND','MODEL','LABEL'])
        self.assertEqual(self.rows('wa_outgoing')[0]['delivery_kind'],'REVIEWED_GUIDANCE');self.assertEqual(self.rows('wa_staff'),[])
    def test_confirmation_must_be_customer_text_for_this_photo_not_an_ai_guess(self):
        context={'conversation':[{'role':'CUSTOMER','message_id':'old','text':'4C'},{'role':'CUSTOMER','message_id':'photo','text':'What is this?','photo':{'error_code':'E06'}},{'role':'AI','message_id':'ai','text':'F06'},{'role':'CUSTOMER','message_id':'confirmation','text':'The display really says F06.'}]}
        result={'photo_message_id':'photo','photo_context_message_ids':['photo','confirmation'],'confirmed_error_code':'F06','code_confirmation_message_id':'confirmation'}
        photo_context.validate(result,context)
        for change in ({'confirmed_error_code':'4C','code_confirmation_message_id':'old'},{'code_confirmation_message_id':'ai'},{'confirmed_error_code':'F99'}):
            with self.assertRaises(ValueError):photo_context.validate({**result,**change},context)
    def test_followup_reuses_the_photo_and_prior_typed_code_without_old_device_facts(self):
        context={'conversation':[{'role':'CUSTOMER','message_id':'old','text':'Older device is Brand Z 4C.'},{'role':'CUSTOMER','message_id':'photo','text':'What is this?','photo':{'error_code':'E06'}},{'role':'CUSTOMER','message_id':'confirmation','text':'F06'},{'role':'CUSTOMER','message_id':'follow','text':'I cannot find the label.'}], 'support_requests':[],'staff_guidance':[],'photo_confirmation_required':True}
        result={'photo_message_id':'photo','photo_context_message_ids':['photo','confirmation','follow'],'confirmed_error_code':'F06','code_confirmation_message_id':'confirmation','report_type':'COMPLAINT','category':'MAINTENANCE','severity':'MEDIUM','uncertainty':True}
        photo_context.validate(result,context);photo_context.apply(context,result,{'id':'follow','kind':'text'})
        self.assertEqual(context['confirmed_error_code'],'F06');self.assertFalse(context['photo_confirmation_required'])
        self.assertNotIn('old',[m['message_id'] for m in context['conversation']])
    def test_recent_lookup_is_reused_only_for_the_same_photo_query_and_case(self):
        ctx={'research_history':[]}
        with patch('belive.whatsapp_ai.research',return_value=self.found()) as search:
            self.assertFalse(wa_research.lookup(self.s,ctx,'case-qa','photo-qa','Series QA','TECHNICAL','IDENTIFICATION'))
            history=wa_research.history(self.s,'case-qa');self.assertEqual(len(history),1)
            self.assertEqual(wa_research.history(self.s,'other-case'),[])
            ctx={'research_history':history}
            self.assertTrue(wa_research.lookup(self.s,ctx,'case-qa','photo-qa','  series   qa ','TECHNICAL','IDENTIFICATION'))
            self.assertEqual(search.call_count,1)
            self.assertFalse(wa_research.lookup(self.s,ctx,'case-qa','other-photo','Series QA','TECHNICAL','IDENTIFICATION'))
            self.assertEqual(search.call_count,2)
        with patch.dict(os.environ,{'BELIVE_WA_TECH_DOMAINS':'support.apple.com'}):self.assertEqual(wa_research.history(self.s,'case-qa'),[])
        with self.s.store.connect() as db:
            for r in self.s.store.all(db,'wa_research'):
                r['retrieved_at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat();self.s.store.put(db,'wa_research',r)
        self.assertEqual(wa_research.history(self.s,'case-qa'),[])

    def test_selected_photo_and_literal_customer_display_are_preserved(self):
        context={'conversation':[{'role':'CUSTOMER','message_id':'old','text':'Samsung 4C'},
            {'role':'CUSTOMER','message_id':'photo','text':'What happened?','photo':{'error_code':'E06'}},
            {'role':'CUSTOMER','message_id':'code','text':'屏幕就是F06，标签找不到。'},
            {'role':'CUSTOMER','message_id':'follow','text':'只有这张照片。'}], 'support_requests':[],'staff_guidance':[]}
        result={'photo_message_id':'','photo_context_message_ids':['photo','code','follow'],
            'confirmed_error_code':'','code_confirmation_message_id':'','report_type':'COMPLAINT',
            'category':'MAINTENANCE','severity':'MEDIUM','uncertainty':True}
        photo_context.validate(result,context);photo_context.apply(context,result,{'id':'follow','kind':'text'})
        self.assertEqual(result['photo_message_id'],'photo');self.assertEqual(context['confirmed_error_code'],'F06')
        self.assertEqual(context['code_confirmation_message_id'],'code')
        self.assertNotIn('old',[m['message_id'] for m in context['conversation']])

    def test_same_photo_handover_updates_one_open_request(self):
        tid=self.incoming('Unknown appliance needs a team assessment.')['thread_id']
        self.incoming('I still cannot find the model.')
        with self.s.store.connect() as db:
            thread=self.s.store.get(db,'wa_thread',tid)
            messages=[m for m in self.s.store.all(db,'wa_message') if m['thread_id']==tid]
            msg=messages[-1];follow=messages[0]
            context={'current_photo':{'message_id':msg['id']}}
            wa._staff_request(self.s,db,thread,'Identify the appliance.',origin_message_id=msg['id'],context=context)
            wa._staff_request(self.s,db,thread,'Customer still cannot locate its model.',origin_message_id=follow['id'],context=context)
            requests=self.s.store.all(db,'wa_staff')
        self.assertEqual(len(requests),1);self.assertEqual(requests[0]['photo_context_message_id'],msg['id'])

if __name__=='__main__':unittest.main()
