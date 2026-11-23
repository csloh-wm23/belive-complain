"""Validate Decisions output and staff fallback without network calls."""
import copy
import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from belive import decisions, reply_learning
from belive.ai import SupportAI
from belive.service import Service
from belive.settings import Settings
import test_reply_learning as reply_tests
from test_reply_learning import FeedbackAI


def choice(name, options, selected):
    return {'name':name,'type':'choice','choice':selected,'confidence':.9,
            'probabilities':[{'value':value,'probability':.98 if value==selected else .02/(len(options)-1)}
                             for value in options]}


def fixture():
    return {'model':'gpt-6-luna','answers':[
        choice('message_type', decisions.MESSAGE_TYPES, 'COMPLAINT'),
        choice('category', decisions.CATEGORIES, 'MAINTENANCE'),
        choice('severity', decisions.LEVELS, 'MEDIUM'),
    ]}


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        self.settings=Settings(agent_engine='direct',llm_provider='openai',llm_model='gpt-6-luna',
                               llm_api_key='fixture-only',decisions_enabled=True)
        self.context={'case':{'title':'Washer fault','description':'The shared washer is broken.'},
                      'conversation':[],'tenant_verified':True,'verified_records':[]}

    def test_decisions_classifies_and_keeps_the_regular_response_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            ai=SupportAI(self.settings,Path(directory))
            plan={'plan':'Staff should inspect the washer.','response':'When did the machine stop?',
                  'requires_human':True,'record_ids':[]}
            with patch('belive.decisions.request_json',return_value=fixture()) as decide, \
                 patch('belive.hosted_ai.generate',return_value={'text':json.dumps(plan)}) as generate:
                result=ai.analyse(self.context,[])
            self.assertEqual(result['category'],'MAINTENANCE')
            self.assertEqual(result['complaint_level'],'MODERATE')
            self.assertTrue(result['requires_human'])
            self.assertEqual(result['evidence'],self.context['case']['description'])
            self.assertEqual(result['decision_details']['endpoint'],'/v1/decisions')
            self.assertEqual([s['agent'] for s in result['agent_trace']],
                             ['Complaint Analysis Agent','Support Response Agent'])
            decide.assert_called_once()
            generate.assert_called_once()

    def test_uncertain_options_never_become_certain_simple_guidance(self):
        data=fixture()
        data['answers'][2]['choice']='LOW'
        for row in data['answers'][2]['probabilities']:
            row['probability']=.6 if row['value']=='LOW' else .4/3
        with patch('belive.decisions.request_json',return_value=data):
            result=decisions.triage(self.settings,self.context,'Use the complaint rubric.')
        self.assertTrue(result['uncertainty'])
        self.assertEqual(result['relevance'],'UNCERTAIN')

    def test_refusal_missing_options_and_invalid_probabilities_require_review(self):
        candidates=[None,{'model':'gpt-6-luna','answers':[]}]
        for modification in ('refusal','missing','nan','duplicate'):
            data=fixture();answer=data['answers'][0]
            if modification=='refusal':answer['type']='refusal'
            if modification=='missing':answer['probabilities'].pop()
            if modification=='nan':answer['probabilities'][0]['probability']=float('nan')
            if modification=='duplicate':answer['probabilities'].append(copy.deepcopy(answer['probabilities'][0]))
            candidates.append(data)
        for data in candidates:
            with self.subTest(data=data),patch('belive.decisions.request_json',return_value=data):
                with self.assertRaisesRegex(ValueError,'AI_INVALID_DECISION'):
                    decisions.triage(self.settings,self.context,'Use the complaint rubric.')


class SemanticFeedbackAI(FeedbackAI):
    checks_feedback_reactions=True
    def __init__(self):
        super().__init__()
        self.reaction='DISSATISFIED'
    def reply_improvement(self,*args):
        return {**super().reply_improvement(*args),'reaction':self.reaction,'tone':'FRUSTRATED'}


class SemanticFeedbackTests(reply_tests.ReplyLearningTests):
    def setUp(self):
        super().setUp()
        self.s.ai=self.ai=SemanticFeedbackAI()

    def test_semantic_reaction_catches_sarcasm_outside_the_old_phrase_list(self):
        text='Wow, fantastic service. A room number to read a sentence? Genius.'
        self.assertFalse(reply_learning.negative(text))
        item=self.feedback(text)
        self.assertFalse(item['signal'])
        reply_learning.execute(self.s,item['id'])
        row=self.rows()[0]
        self.assertTrue(row['signal'])
        self.assertEqual(row['reaction'],'DISSATISFIED')
        self.assertEqual(row['status'],'PROPOSED')

    def test_thanks_or_a_new_question_does_not_claim_reply_failure(self):
        self.ai.reaction='POSITIVE'
        self.s.portal_update(self.code,dict(id=self.cid,note='Thank you, that answers my question.'),secrets.token_hex(16))
        item=self.rows()[0]
        reply_learning.execute(self.s,item['id'])
        self.assertEqual(self.rows()[0]['status'],'OBSERVED')
        self.assertFalse(self.rows()[0]['signal'])
        self.assertEqual(self.rows()[0]['tip'],'')
        snapshot=self.s.snapshot()
        self.assertEqual(snapshot['feedback_reactions']['POSITIVE'],1)
        self.assertEqual(snapshot['reply_learning'],[])

    def test_positive_reaction_after_tip_use_is_counted_without_a_failure_signal(self):
        self.approve()
        receipt=self.s.website_submit(dict(title='[TEST] Another general question',
            description='Can you read my message? I need help with this page.'),secrets.token_hex(16))
        self.s.analyse(receipt['id'])
        self.ai.reaction='POSITIVE'
        self.s.portal_update(receipt['complaint_code'],dict(id=receipt['id'],
            note='Thanks, your explanation makes sense now.'),secrets.token_hex(16))
        later=self.rows()[0]
        reply_learning.execute(self.s,later['id'])
        row=next(x for x in self.s.snapshot()['reply_learning'] if x['approved'])
        self.assertEqual(row['positive_after_use'],1)
        self.assertEqual(row['latest_case'],receipt['id'])
        self.assertEqual(row['negative_after_use'],0)
