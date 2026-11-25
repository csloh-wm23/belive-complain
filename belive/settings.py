"""Project-local settings. Never read another application's credentials."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from belive.hosted_ai import DEFAULT_MODELS

ROOT = Path(__file__).resolve().parents[1]

def load_env():
    path = ROOT / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

@dataclass
class Settings:
    agent_engine: str = 'hermes'
    llm_provider: str = 'openai'
    llm_model: str = ''
    llm_api_key: str = field(default='', repr=False)
    decisions_enabled: bool = False
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_api_key: str = field(default='', repr=False)
    acknowledgement_minutes: int = 30
    followup_minutes: int = 1440
    scheduler_seconds: int = 30

def load_settings(database=None):
    load_env()
    from belive.credentials import get_value
    def setting(name, default=''):
        return get_value(name, default, database)
    provider = setting('BELIVE_AI_PROVIDER', 'openai').strip().lower()
    model = setting('BELIVE_AI_MODEL', '').strip() or DEFAULT_MODELS.get(provider, '')
    return Settings(agent_engine=os.getenv('BELIVE_AGENT_ENGINE','hermes').strip().lower(),llm_provider=provider,
        llm_model=model, llm_api_key=setting('BELIVE_AI_KEY','').strip(),
        decisions_enabled=os.getenv('BELIVE_DECISIONS_ENABLED','false').strip().lower()=='true',
        ollama_base_url=setting('BELIVE_OLLAMA_URL','http://127.0.0.1:11434'),
        ollama_api_key=setting('BELIVE_OLLAMA_KEY',''),
        acknowledgement_minutes=max(1,int(os.getenv('BELIVE_ACK_MINUTES','30'))),
        followup_minutes=max(1,int(os.getenv('BELIVE_FOLLOWUP_MINUTES','1440'))))
