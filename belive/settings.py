"""Project-local settings. Never read another application's credentials."""
import os
from dataclasses import dataclass
from pathlib import Path

from belive.openrouter import DEFAULT_MODEL

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
    llm_provider: str = 'openai'
    llm_model: str = ''
    llm_api_key: str = ''
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_api_key: str = ''
    acknowledgement_minutes: int = 30
    followup_minutes: int = 1440
    scheduler_seconds: int = 30

def load_settings():
    load_env()
    provider = os.getenv('BELIVE_AI_PROVIDER', 'openai').strip().lower()
    model = os.getenv('BELIVE_AI_MODEL', '').strip()
    if provider == 'openrouter' and not model:
        model = DEFAULT_MODEL
    return Settings(llm_provider=provider,
        llm_model=model, llm_api_key=os.getenv('BELIVE_AI_KEY','').strip(),
        ollama_base_url=os.getenv('BELIVE_OLLAMA_URL','http://127.0.0.1:11434'),
        ollama_api_key=os.getenv('BELIVE_OLLAMA_KEY',''),
        acknowledgement_minutes=max(1,int(os.getenv('BELIVE_ACK_MINUTES','30'))),
        followup_minutes=max(1,int(os.getenv('BELIVE_FOLLOWUP_MINUTES','1440'))))
