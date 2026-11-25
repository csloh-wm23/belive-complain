"""Native comparison evidence remains attached to the owning BeLive service."""
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from belive.ai import SupportAI
from belive.service import Service
from belive import learning,relevance
from test_backend import FakeAI


class LearningExecutionEvidenceTests(unittest.TestCase):
    def test_both_comparison_stages_keep_the_native_execution_observer(self):
        with tempfile.TemporaryDirectory() as directory:
            service=Service(Path(directory)/'comparison.db',FakeAI())
            def command(name,payload):
                return service.command(name,payload,secrets.token_hex(16))
            def case(case_id):
                with service.store.connect() as db:return service.store.get(db,'case',case_id)
            def action(case_id,name,**fields):
                return command('case_action',dict(id=case_id,revision=case(case_id)['revision'],action=name,**fields))
            entry=command('intake',dict(title='[TEST] Noise reporting',description='A fictional late-night noise reporting question.'))
            action(entry['id'],'acknowledge',owner='Fictional reviewer')
            action(entry['id'],'verify_staff_close',note='The fictional handling outcome was checked.',confirmed=True)
            experience=command('feedback',dict(id=entry['id'],verdict='CORRECTED',text='Record the approximate times and describe what you observed.',public_question='How should I report repeated late-night noise?',publish_public=True))
            service.ai=SupportAI(service.settings,Path(directory)/'hermes_memory')
            observed=[]
            def generate(ai,question,guidance=None):
                self.assertIs(ai.execution_observer.__self__,service)
                observed.append((question,guidance))
                ai.execution_observer(dict(engine='hermes-native',agent_class='run_agent.AIAgent',role='Mocked comparison stage',api_calls=1,executed_tools=[]))
                return 'Record the approximate times and describe what you observed.'
            with patch.object(SupportAI,'readiness',return_value=True),patch.object(SupportAI,'experience_reply',autospec=True,side_effect=generate):
                run=command('learning_start',dict(category='HOUSE_RULES',question='How should I report repeated late-night noise?',experience_id=experience['id']))
                learning.execute(service,run['id'])
                command('learning_improve',dict(id=run['id'],confirmed=True))
                learning.execute(service,run['id'])
            with service.store.connect() as db:
                saved=service.store.get(db,'learning_run',run['id'])
                executions=service.store.all(db,'native_execution')
            self.assertEqual(saved['status'],'COMPLETE')
            self.assertEqual(len(executions),2)
            self.assertEqual(len(observed),2)
            self.assertIsNone(observed[0][1])
            self.assertEqual(observed[1][1]['id'],experience['id'])


class NoiseLocationPolicyTests(unittest.TestCase):
    def test_shared_corridor_noise_allows_relevant_area_but_not_private_room(self):
        question='How should I report repeated late-night noise in the shared corridor?'
        self.assertEqual(relevance.location_scope(question),'AFFECTED_AREA')
        self.assertFalse(relevance.unnecessary_location('Include the affected shared area and approximate times.',question))
        self.assertTrue(relevance.unnecessary_location('Please provide your room number before reporting the noise.',question))

    def test_general_quiet_hours_question_does_not_require_a_location(self):
        question='What do quiet hours mean?'
        self.assertEqual(relevance.location_scope(question),'NONE')
        self.assertTrue(relevance.unnecessary_location('Which building are you staying in?',question))


if __name__=='__main__':unittest.main()
