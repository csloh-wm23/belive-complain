"""Customer voice and final public handover review, with no real sends."""
import unittest
from belive.whatsapp_tone import reference
from test_whatsapp import plan
import test_whatsapp as fixtures

class ToneTests(unittest.TestCase):
    setUp=fixtures.WhatsAppTests.setUp;tearDown=fixtures.WhatsAppTests.tearDown
    rows=fixtures.WhatsAppTests.rows;cmd=fixtures.WhatsAppTests.cmd;incoming=fixtures.WhatsAppTests.incoming;process=fixtures.WhatsAppTests.process
    def test_generated_handover_is_reviewed_and_sent_instead_of_form_letter(self):
        self.reply.return_value={**plan(),'reply':'Private suggested steps for staff to check.','needs_staff':True,'staff_question':'Confirm the visitor exception.','handover_reply':'Bro, let me check that overnight visit with the team first.'}
        self.process(self.incoming('bro can my cousin stay over? pls ask staff first'))
        out=self.rows('wa_outgoing')[0]
        self.assertEqual(out['text'],'Bro, let me check that overnight visit with the team first.')
        self.assertEqual(out['staff_draft'],'Private suggested steps for staff to check.')
        self.assertEqual(self.review.call_args.args[2],out['text'])
        self.assertTrue(self.review.call_args.args[1]['acknowledgement_only'])
        self.assertEqual(self.review.call_args.args[1]['private_staff_draft'],out['staff_draft'])
        self.assertEqual(out['status'],'SIMULATED');self.assertEqual(len(self.rows('wa_staff')),1)
    def test_unsafe_casual_handover_is_revised_before_delivery(self):
        unsafe={**plan(),'needs_staff':True,'staff_question':'Confirm safe arrangements.','handover_reply':'Bro, open the electrical panel yourself.'}
        safe={**plan(),'needs_staff':True,'staff_question':'Confirm safe arrangements.','handover_reply':'Bro, I need the team to check this before we go further.'}
        self.reply.side_effect=[unsafe,safe];self.review.side_effect=[False,True]
        self.process(self.incoming('bro can staff help with the washer?'))
        out=self.rows('wa_outgoing')[0];self.assertEqual(out['text'],safe['handover_reply'])
        self.assertNotIn('electrical panel',out['text']);self.assertEqual(self.review.call_count,2)
        self.assertEqual(self.review.call_args.args[2],out['text'])
    def test_deterministic_fallback_is_also_reviewed_as_actual_public_text(self):
        self.reply.return_value={**plan(),'needs_staff':True,'staff_question':'Confirm next steps.'}
        self.process(self.incoming('Can staff confirm this request?'))
        out=self.rows('wa_outgoing')[0];self.assertEqual(self.review.call_args.args[2],out['text'])
    def test_staff_note_language_does_not_replace_customer_voice(self):
        context={'target_request':{'original_message':'bro sy nk tanya sikit'},'current_message':{'role':'STAFF_INTERNAL','text':'Kindly advise the tenant.'},'conversation':[{'role':'AI','text':'Dear valued customer.'}]}
        result=reference(context);self.assertEqual(result['message_to_match'],'bro sy nk tanya sikit')
        self.assertNotIn('Kindly',str(result['recent_customer_messages']))
    def test_latest_customer_style_takes_priority_and_reference_is_bounded(self):
        context={'current_message':{'role':'CUSTOMER','text':'请正式说明处理步骤。'},'conversation':[{'role':'CUSTOMER','text':'bro '+('x'*9000)},{'role':'CUSTOMER','text':'请正式说明处理步骤。'}]}
        result=reference(context);self.assertEqual(result['message_to_match'],'请正式说明处理步骤。')
        self.assertLessEqual(len(str(result)),2400)
