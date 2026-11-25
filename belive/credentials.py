"""Database-backed local credentials; only encrypted values persist, never public exports."""
import base64
from contextlib import contextmanager, closing
from contextvars import ContextVar
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3

_DB = ContextVar('belive_credential_database', default=None)
AAD = b'BeLive local credential settings v1'
KEY_FILENAME = '.belive-credentials.key'
FIELDS = {
    'BELIVE_AI_PROVIDER': ('AI provider', False, 'AI'),
    'BELIVE_AI_MODEL': ('Model', False, 'AI'),
    'BELIVE_AI_KEY': ('Model API key', True, 'AI'),
    'BELIVE_OLLAMA_URL': ('Ollama base URL', False, 'AI'),
    'BELIVE_OLLAMA_KEY': ('Ollama API key', True, 'AI'),
    'BELIVE_GOOGLE_TOKEN': ('Google Business Profile access token', True, 'GOOGLE'),
    'BELIVE_FACEBOOK_TOKEN': ('Facebook Page access token', True, 'FACEBOOK'),
    'BELIVE_FACEBOOK_VERSION': ('Facebook Graph API version', False, 'FACEBOOK'),
    'BELIVE_THREADS_TOKEN': ('Threads access token', True, 'THREADS'),
    'BELIVE_WHATSAPP_ACCESS_TOKEN': ('WhatsApp access token', True, 'WHATSAPP'),
    'BELIVE_WHATSAPP_APP_SECRET': ('Meta app secret', True, 'WHATSAPP'),
    'BELIVE_WHATSAPP_VERIFY_TOKEN': ('Webhook verify token', True, 'WHATSAPP'),
    'BELIVE_WHATSAPP_PHONE_NUMBER_ID': ('WhatsApp phone-number ID', False, 'WHATSAPP'),
    'BELIVE_WHATSAPP_GRAPH_VERSION': ('WhatsApp Graph API version', False, 'WHATSAPP'),
    'BELIVE_WHATSAPP_WEBHOOK_HOST': ('Public webhook host', False, 'WHATSAPP'),
    'BELIVE_NOTIFICATION_URL': ('Notification gateway HTTPS URL', False, 'NOTIFICATION'),
    'BELIVE_NOTIFICATION_SECRET': ('Notification gateway signing secret', True, 'NOTIFICATION'),
}


class CredentialStoreError(ValueError):
    pass


@contextmanager
def credential_scope(database):
    token = _DB.set(Path(database).resolve())
    try:
        yield
    finally:
        _DB.reset(token)


def _database(database=None):
    value = database if database is not None else _DB.get()
    return Path(value).resolve() if value is not None else None


def key_path(database):
    return Path(database).resolve().parent / KEY_FILENAME


def _key(database, create=False):
    path = key_path(database)
    if not path.exists() and create:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('x', encoding='ascii') as handle:
                handle.write(base64.b64encode(secrets.token_bytes(32)).decode() + '\n')
        except FileExistsError:
            pass
    try:
        result = base64.b64decode(path.read_text(encoding='ascii').strip(), validate=True)
        if len(result) != 32:
            raise ValueError()
        return result
    except (OSError, ValueError, UnicodeError):
        raise CredentialStoreError('The private credential key is missing or invalid. Restore its private file; stored credentials remain locked.') from None


def _cipher():
    from belive.repository_memory import crypto
    try:
        return crypto()
    except ValueError:
        raise CredentialStoreError('Install the local encryption dependency with knowledge_backup.py runtime.') from None


def load(database=None):
    path = _database(database)
    if path is None or not path.is_file():
        return {'version': 0, 'values': {}, 'updated_at': None}
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='private_credentials'").fetchone()
            row = db.execute('SELECT version,nonce,ciphertext,updated_at FROM private_credentials WHERE id=1').fetchone() if exists else None
        if row is None:
            return {'version': 0, 'values': {}, 'updated_at': None}
        raw = _cipher()(_key(path)).decrypt(base64.b64decode(row[1], validate=True), base64.b64decode(row[2], validate=True), AAD)
        values = json.loads(raw)
        if not isinstance(values, dict) or set(values) - set(FIELDS) or any(not isinstance(v, str) for v in values.values()):
            raise ValueError()
        return {'version': row[0], 'values': values, 'updated_at': row[3]}
    except CredentialStoreError:
        raise
    except Exception:
        raise CredentialStoreError('Stored credentials could not be authenticated. They remain locked; restore the private key or an intact private backup.') from None


def get_value(name, default='', database=None):
    if name not in FIELDS:
        return os.getenv(name, default)
    try:
        values = load(database)['values']
    except CredentialStoreError:
        # Never silently fall back to an old token after the saved store becomes unreadable.
        return '' if FIELDS[name][1] else os.getenv(name, default)
    return values[name] if name in values else os.getenv(name, default)


def status(database):
    error = ''
    try:
        saved = load(database)
    except CredentialStoreError as exc:
        saved = {'version': None, 'values': {}, 'updated_at': None}
        error = str(exc)
    values = saved['values']
    fields = []
    for name, (label, secret, group) in FIELDS.items():
        stored = name in values
        value = values[name] if stored else os.getenv(name, '')
        item = {'name': name, 'label': label, 'secret': secret, 'group': group,
                'configured': bool(value) and not error, 'source': 'locked' if error else 'database' if stored else 'environment' if value else 'unset'}
        if not secret:
            item['value'] = value if not error else ''
        fields.append(item)
    return {'status': 'LOCKED' if error else 'READY', 'version': saved['version'], 'updated_at': saved['updated_at'],
            'message': error or 'Saved credentials are encrypted in this database. Blank secret fields keep their existing values.',
            'fields': fields, 'has_database_settings': bool(values)}


def _validate(name, value):
    if name not in FIELDS or not isinstance(value, str) or len(value) > 8000 or any(ord(c) < 32 for c in value):
        raise ValueError('Use a supported setting with a single-line value.')
    value = value.strip()
    if name == 'BELIVE_AI_PROVIDER' and value not in {'openai', 'openrouter', 'ollama'}:
        raise ValueError('Choose OpenAI, OpenRouter or Ollama.')
    if name == 'BELIVE_AI_MODEL' and not re.fullmatch(r'[A-Za-z0-9_.:/@+\-]{1,160}', value):
        raise ValueError('Enter a valid model ID.')
    if name.endswith(('_VERSION',)) and value and not re.fullmatch(r'v[0-9]+\.[0-9]+', value):
        raise ValueError('Use an API version such as v24.0 supplied by the platform.')
    if name == 'BELIVE_WHATSAPP_PHONE_NUMBER_ID' and value and not re.fullmatch(r'[0-9]{1,60}', value):
        raise ValueError('Enter the numeric phone-number ID from Meta.')
    if name == 'BELIVE_WHATSAPP_WEBHOOK_HOST' and value and not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?', value):
        raise ValueError('Enter the webhook host without a URL path.')
    if name in {'BELIVE_OLLAMA_URL', 'BELIVE_NOTIFICATION_URL'} and value:
        from urllib.parse import urlsplit
        url = urlsplit(value)
        schemes = {'https'} if name == 'BELIVE_NOTIFICATION_URL' else {'https', 'http'}
        if url.scheme not in schemes or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use a valid base URL without embedded credentials, query or fragment.')
    return value


def save(service, payload, actor):
    values = payload.get('values', {})
    remove = payload.get('remove', [])
    version = payload.get('version')
    if not isinstance(values, dict) or not isinstance(remove, list) or type(version) is not int:
        raise ValueError('Refresh settings and submit the saved version, values and optional fallback list.')
    if len(remove) != len(set(remove)) or any(not isinstance(x, str) or x not in FIELDS for x in remove):
        raise ValueError('Choose supported settings for environment fallback.')
    if set(values) & set(remove):
        raise ValueError('Save a value or use environment fallback, not both for the same setting.')
    updates = {name: _validate(name, value) for name, value in values.items()}
    path = service.store.path.resolve()
    cipher = _cipher()
    from belive.store import now
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = load(path)
        if previous['version'] != version:
            raise ValueError('Credential settings changed. Refresh before saving.')
        merged = dict(previous['values'])
        merged.update(updates)
        for name in remove:
            merged.pop(name, None)
        nonce = secrets.token_bytes(12)
        encrypted = cipher(_key(path, create=True)).encrypt(nonce, json.dumps(merged).encode(), AAD)
        db.execute('CREATE TABLE IF NOT EXISTS private_credentials(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,nonce TEXT NOT NULL,ciphertext TEXT NOT NULL,updated_at TEXT NOT NULL)')
        db.execute('INSERT INTO private_credentials VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,nonce=excluded.nonce,ciphertext=excluded.ciphertext,updated_at=excluded.updated_at',
                   (version + 1, base64.b64encode(nonce).decode(), base64.b64encode(encrypted).decode(), now()))
        service.store.event(db, 'credentials', 'CREDENTIAL_SETTINGS_UPDATED', actor + ': encrypted local settings updated; no values recorded')
        service.store.put(db, 'health', {'id': 'ai', 'status': 'NOT_TESTED', 'at': now(), 'detail': 'Connection settings changed. Run Test AI connection before relying on the new connection.'})
    apply(service)
    return status(path)


def apply(service):
    from belive.settings import load_settings
    current = load_settings(service.store.path)
    service.settings = current
    if hasattr(service.ai, 'settings'):
        service.ai.settings = current
